# tools.py
import os, json, uuid
from typing import Union
from supabase import create_client
from langchain_core.tools import tool

# Connect to Supabase using the server-only service key
supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_KEY"],
)

def _resolve_job_id(job_id: str) -> str:
    """Return a valid job_descriptions UUID, self-healing a bad one.

    The id/job_id columns are Postgres `uuid`. The LLM is told to reuse the exact
    id returned by save_job_description, but models sometimes pass a placeholder
    like "1" instead of the real UUID. That makes Postgres reject the write with
    `invalid input syntax for type uuid`. Rather than fail the whole screening
    over the model's bookkeeping slip, we validate the id here: if it's already a
    well-formed UUID we trust it; if not, we fall back to the most recently saved
    job description (the one the agent almost certainly just created in this same
    run). Raises a clear error only if there is no job to fall back to."""
    try:
        uuid.UUID(str(job_id))
        return job_id  # already a valid UUID — use as-is
    except (ValueError, AttributeError, TypeError):
        pass
    recent = (supabase.table("job_descriptions")
              .select("id")
              .order("created_at", desc=True)
              .limit(1)
              .execute())
    if recent.data:
        return recent.data[0]["id"]
    raise ValueError(
        f"job_id {job_id!r} is not a valid UUID and no saved job description "
        "exists to fall back to. Call save_job_description first and reuse the "
        "id it returns."
    )

# The hiring company this agent screens for. Used to sign outreach emails so
# they never go out with a "[Your Name]" placeholder. Configurable via env var
# (COMPANY_NAME) so it can be changed without touching code; defaults to ours.
COMPANY_NAME = os.environ.get("COMPANY_NAME", "Zikra Infotech")

# ---- DOMAIN KNOWLEDGE: the scoring rubric the agent must follow ----
# This is injected into the agent's instructions so scoring is consistent.
SCORING_RUBRIC = """
Score each candidate 0-100 using these weighted dimensions:
- Must-have skills present (40 pts): each missing must-have is a heavy penalty.
- Relevant years of experience vs. what the JD asks (20 pts).
- Domain / industry match (15 pts).
- Nice-to-have skills (15 pts).
- Signals of impact: promotions, ownership, measurable results (10 pts).
Recommendation mapping: 75-100 = 'shortlist', 50-74 = 'maybe', 0-49 = 'reject'.
Always explain WHY, citing specific resume evidence. Never invent facts
that are not in the resume.
"""

@tool
def save_job_description(title: str, raw_text: str, parsed_json: str) -> str:
    """Save a job description and its parsed requirements. parsed_json is a
    JSON string with keys: must_have (list), nice_to_have (list),
    min_years (number), domain (string). Returns the new job_id.

    Idempotent: if a JD with the same title + raw_text already exists, the
    existing row is UPDATED and its id returned instead of inserting a
    duplicate. The deep-agent harness can call a tool more than once in a
    single run, and the same JD may be submitted across test runs; matching on
    (title, raw_text) keeps those from piling up duplicate rows."""
    parsed = json.loads(parsed_json)
    payload = {"title": title, "raw_text": raw_text, "parsed": parsed}

    existing = (supabase.table("job_descriptions")
                .select("id")
                .eq("title", title)
                .eq("raw_text", raw_text)
                .execute())

    if existing.data:
        row_id = existing.data[0]["id"]
        res = (supabase.table("job_descriptions")
               .update(payload)
               .eq("id", row_id)
               .execute())
    else:
        res = supabase.table("job_descriptions").insert(payload).execute()

    return res.data[0]["id"]

@tool
def save_candidate_result(job_id: str, name: str, resume_text: str,
                          score: Union[int, str], recommendation: str,
                          analysis_json: str, outreach_email: str) -> str:
    """Save one screened candidate's result. analysis_json is a JSON string
    with keys: strengths (list), gaps (list), requirement_matches (list of
    {requirement, met, evidence}). Returns the candidate_id.

    Idempotent: if this candidate (same job_id + name) was already screened,
    the existing row is UPDATED in place instead of inserting a duplicate.
    This keeps a retried/replayed agent step from creating multiple rows.
    NOTE: matching on name is fine for a demo; in production you'd match on a
    stable identifier (email or candidate id) to avoid same-name collisions."""
    # Guard the foreign key: if the model handed us a placeholder instead of the
    # real UUID from save_job_description, resolve it (see _resolve_job_id) so a
    # good screening isn't lost to a bad id.
    job_id = _resolve_job_id(job_id)

    # LLMs often serialize numbers as strings (e.g. "90" instead of 90). We
    # accept either and coerce to int here so a well-reasoned screening isn't
    # thrown away over a JSON type mismatch. int() also strips a stray "90.0".
    score = int(float(score))

    # Models habitually sign emails with a "[Your Name]" placeholder even when
    # told not to. Rather than trust the prompt alone, we swap any leftover
    # placeholder for the real company name here so no email is ever stored (or
    # sent) with an unfilled blank. Covers the common variants.
    if outreach_email:
        for placeholder in ("[Your Name]", "[Your name]", "[your name]",
                            "[Company Name]", "[Company]", "[Name]"):
            outreach_email = outreach_email.replace(placeholder, COMPANY_NAME)

    analysis = json.loads(analysis_json)
    payload = {
        "job_id": job_id, "name": name, "resume_text": resume_text,
        "score": score, "recommendation": recommendation,
        "analysis": analysis, "outreach_email": outreach_email,
    }

    existing = (supabase.table("candidates")
                .select("id")
                .eq("job_id", job_id)
                .eq("name", name)
                .execute())

    if existing.data:
        row_id = existing.data[0]["id"]
        res = (supabase.table("candidates")
               .update(payload)
               .eq("id", row_id)
               .execute())
    else:
        res = supabase.table("candidates").insert(payload).execute()

    return res.data[0]["id"]

@tool
def list_pipeline(job_id: str) -> str:
    """Return all screened candidates for a job, ranked by score (highest
    first), as a JSON string. Use this to summarize the hiring pipeline."""
    # Same UUID guard as save_candidate_result: tolerate a placeholder job_id.
    job_id = _resolve_job_id(job_id)
    res = (supabase.table("candidates")
           .select("name,score,recommendation")
           .eq("job_id", job_id)
           .order("score", desc=True)
           .execute())
    return json.dumps(res.data)