# tools.py
import os, json
from typing import Union
from supabase import create_client
from langchain_core.tools import tool

# Connect to Supabase using the server-only service key
supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_KEY"],
)

def _resolve_job_id_for_pipeline(job_title: str = "") -> str:
    """Find a job_descriptions id to summarize, WITHOUT trusting a model-supplied
    UUID. The model was previously asked to thread the job_id UUID between tool
    calls and got it wrong three different ways (placeholder "1" -> 22P02; a
    copied example UUID -> 23503 FK violation; the literal string
    "returned_job_id"). So we no longer accept a raw id from the model at all.

    Here we resolve by a human-readable job_title if one is given (case-insensitive
    match on the most recent such job), otherwise fall back to the single most
    recently saved job. Returns None-safe: raises a clear error only if there is
    no job saved yet."""
    q = supabase.table("job_descriptions").select("id,title").order(
        "created_at", desc=True)
    if job_title:
        q = q.ilike("title", f"%{job_title}%")
    res = q.limit(1).execute()
    if res.data:
        return res.data[0]["id"]
    raise ValueError(
        "No saved job description to summarize yet. Screen at least one "
        "candidate first (which saves the job), then view the pipeline."
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

def _upsert_job_description(title: str, raw_text: str, parsed: dict) -> str:
    """Insert-or-update a job description, returning its id. Idempotent on
    (title, raw_text) so re-screening against the same JD doesn't pile up
    duplicate rows. Kept as a plain helper (not a @tool) because the model no
    longer calls it directly -- screen_candidate calls it in Python, so the
    returned uuid never has to pass through the model."""
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
def screen_candidate(job_title: str, job_raw_text: str, job_parsed_json: str,
                     name: str, resume_text: str, score: Union[int, str],
                     recommendation: str, analysis_json: str,
                     outreach_email: str) -> str:
    """Save a job description AND one screened candidate against it in a single
    atomic step. Returns the candidate_id.

    Pass the JOB fields and the CANDIDATE fields together:
      - job_title: a short title for the role (e.g. "Backend Engineer").
      - job_raw_text: the original job-description text.
      - job_parsed_json: JSON string with keys must_have (list), nice_to_have
        (list), min_years (number), domain (string).
      - name, resume_text: the candidate.
      - score (0-100), recommendation ('shortlist'|'maybe'|'reject').
      - analysis_json: JSON string with keys strengths (list), gaps (list),
        requirement_matches (list of {requirement, met, evidence}).
      - outreach_email: 2-3 sentence email, ONLY if recommendation is
        'shortlist', else empty string.

    WHY one tool instead of two: the job_id is a Postgres uuid. Earlier the
    model had to call one tool to save the JD, then copy the returned uuid into a
    second tool -- and it corrupted that uuid three different ways (a placeholder
    "1", a made-up uuid, and the literal text "returned_job_id"). Here the uuid
    is created and linked entirely in Python; the model never sees or handles it,
    so that whole class of bug is impossible.

    Idempotent on both sides: re-screening the same JD updates its row (matched
    on title+raw_text); re-screening the same candidate for that job updates the
    candidate row (matched on job_id+name) instead of inserting duplicates."""
    # 1. Save/get the job first, in Python -- this yields a real, existing uuid.
    parsed = json.loads(job_parsed_json)
    job_id = _upsert_job_description(job_title, job_raw_text, parsed)

    # 2. LLMs often serialize numbers as strings (e.g. "90"); accept either and
    # coerce so a well-reasoned screening isn't thrown away over a type mismatch.
    # int(float(...)) also strips a stray "90.0".
    score = int(float(score))

    # 3. Models habitually sign emails with a "[Your Name]" placeholder even when
    # told not to. Swap any leftover placeholder for the real company name so no
    # email is ever stored with an unfilled blank. Covers the common variants.
    if outreach_email:
        for placeholder in ("[Your Name]", "[Your name]", "[your name]",
                            "[Company Name]", "[Company]", "[Name]"):
            outreach_email = outreach_email.replace(placeholder, COMPANY_NAME)

    # 4. Upsert the candidate against the job_id we just created.
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
def list_pipeline(job_title: str = "") -> str:
    """Return all screened candidates for a job, ranked by score (highest
    first), as a JSON string. Use this to summarize the hiring pipeline.

    Pass job_title (a human-readable title like "Backend Engineer") to pick the
    job, or leave it empty to use the most recently screened job. Do NOT pass a
    uuid -- the tool resolves the job itself, so the model never handles ids."""
    job_id = _resolve_job_id_for_pipeline(job_title)
    res = (supabase.table("candidates")
           .select("name,score,recommendation")
           .eq("job_id", job_id)
           .order("score", desc=True)
           .execute())
    return json.dumps(res.data)