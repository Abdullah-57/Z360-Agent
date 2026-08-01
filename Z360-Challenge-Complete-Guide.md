# Z360 Take-Home Challenge — Complete Build & Submit Guide

**Your project:** A **Candidate Screening Deep Agent** (based on the "Hiring Screener Agent" from your list)
**For:** Jr. Software Engineer role at Zikra Infotech LLC
**Written for:** someone building this kind of full-stack + AI project for the first time
**Deadline:** within one week of receiving the email

---

## 0. Read this first — the big picture

You are going to build a small web app where a recruiter can:

1. Paste a **job description** (JD).
2. Upload or paste one or more **candidate resumes**.
3. Click a button and get back, for each candidate: a **match score (0–100)**, a breakdown of which requirements they meet, **strengths & gaps**, a **recommendation** (shortlist / maybe / reject), and a **draft outreach email** for the strong ones.

Everything gets **saved** so the recruiter can come back and see a ranked pipeline.

The clever part (what makes it a "Deep Agent" and not a chatbot) is that the AI doesn't just reply with text. It **plans**, **calls custom tools** you wrote (parse the JD, score a resume against a rubric, save results to the database, draft outreach), and follows a **workflow**. That is exactly what the challenge rewards.

### The architecture (how the pieces fit)

```
   ┌─────────────────────────┐         ┌──────────────────────────┐
   │  Browser (the recruiter)│         │  Supabase (cloud)        │
   │                         │         │  - Postgres database     │
   │  Next.js + Tailwind +   │◄───────►│  - stores JDs,           │
   │  shadcn/ui  (on Vercel) │         │    candidates, scores    │
   └───────────┬─────────────┘         └──────────────┬───────────┘
               │  HTTP (JSON)                          ▲
               ▼                                       │ writes results
   ┌─────────────────────────────────────┐            │
   │  Agent server (Python, FastAPI Cloud) │────────────┘
   │  - FastAPI web wrapper               │
   │  - LangGraph "Deep Agent" (deepagents)│
   │  - custom tools + domain knowledge   │
   └─────────────────────────────────────┘
```

Three deployed pieces:
- **Frontend** = the website the recruiter sees. Built with Next.js + Tailwind + shadcn, deployed to **Vercel** (free).
- **Agent server** = a small Python program that holds the AI agent. Deployed to **FastAPI Cloud** (free Hobby tier). We use Python because LangChain's official *Deep Agents* harness (`deepagents`) is Python-first, and the challenge's own scoring table treats the "agent server" as its own component.
- **Supabase** = the database in the cloud that remembers everything (free tier).

Don't worry if this feels like a lot. We do it one piece at a time, and each piece is testable on its own before we connect them.

### Why this agent choice (say this in your interview)

The reviewers at Zikra screen candidates for a living — this challenge is itself a candidate screen. Building the exact tool they'd use shows product empathy, and the challenge PDF lists *"Recruiting: screen candidates, draft outreach, organize a hiring pipeline"* as its very first example domain. It's also a natural fit for a real harness: clear domain knowledge (a scoring rubric), several genuine custom tools, and an obvious end-to-end workflow.

---

## 1. Accounts and tools to set up (all free)

Create these accounts before writing any code. Use the **same email** (ideally a GitHub-linked one) everywhere to keep logins simple.

| Thing | What it's for | Link |
|---|---|---|
| **GitHub** | stores your code; Vercel deploys from it | github.com |
| **Supabase** | cloud database | supabase.com |
| **Vercel** | hosts the frontend website | vercel.com |
| **FastAPI Cloud** | hosts the Python agent server | fastapicloud.com |
| **Groq** | the LLM brain of the agent — free tier, **no credit card**, works everywhere | console.groq.com |
| **Tavily** (optional) | lets the agent do web lookups; free tier | tavily.com |

Software to install on your computer:
- **Node.js** (v20 or newer) — runs the frontend. Download the "LTS" version from nodejs.org.
- **Python** (v3.11 or newer) — runs the agent. Download from python.org.
- **Git** — version control. git-scm.com.
- **VS Code** — a free code editor. code.visualstudio.com.

To check they installed, open a terminal (Command Prompt / PowerShell on Windows, Terminal on Mac) and run each line; you should see version numbers:

```bash
node -v
python --version
git --version
```

> First-timer tip: a "terminal" is the black text window where you type commands. On Windows search for "PowerShell"; on Mac search for "Terminal". When the guide says "run this," you paste the line and press Enter.

### Get your Groq API key (free, no card)
1. Go to console.groq.com → sign in (Google/GitHub/email — no credit card).
2. Open **API Keys** in the left menu → **Create API Key** → name it (e.g. `z360-agent`) → copy it somewhere safe. You only see it once.

No billing and no credit card are required, and Groq's free tier works globally (including the Middle East), which is why this guide uses it instead of Google Gemini. The free tier is generous and very fast — plenty for this challenge.

> Why Groq (interview talking point): because the agent is built on LangChain, the LLM provider is swappable in ~two lines (the import + the model constructor). This guide originally targeted Google Gemini, but Gemini's free tier isn't provisioned in every region; moving to Groq was a two-line change with zero impact on the tools, prompt, or database logic. That provider-agnostic design is worth mentioning to the hiring team.

This key is a password. Never put it in your code or push it to GitHub. We'll store it as an "environment variable" (explained later).

---

## 2. Set up the database (Supabase)

1. Go to supabase.com → **Start your project** → sign in with GitHub.
2. **New project**. Name it `z360-screener`. Choose a region near you. Set a database password (save it in your notes). Wait ~2 minutes while it provisions.
3. In the left sidebar open the **SQL Editor** → **New query**. Paste the block below and click **Run**. This creates the two tables we need.

```sql
-- Table 1: one row per job description
create table job_descriptions (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  raw_text text not null,
  parsed jsonb,               -- structured requirements the agent extracts
  created_at timestamptz default now()
);

-- Table 2: one row per screened candidate
create table candidates (
  id uuid primary key default gen_random_uuid(),
  job_id uuid references job_descriptions(id) on delete cascade,
  name text,
  resume_text text not null,
  score int,                  -- 0..100
  recommendation text,        -- 'shortlist' | 'maybe' | 'reject'
  analysis jsonb,             -- strengths, gaps, requirement-by-requirement
  outreach_email text,
  created_at timestamptz default now()
);
```

4. Get your connection keys: left sidebar → **Project Settings** (gear icon) → **API**. Copy and save two values:
   - **Project URL** (looks like `https://abcdxyz.supabase.co`)
   - **`service_role` secret key** (a long string). The agent server uses this to write results.

> Security note for the interview: the `service_role` key bypasses row-level security, so it must live **only** on the server (FastAPI Cloud secrets/environment variables), never in the frontend. The frontend never talks to the database directly in this design — it goes through the agent server. This keeps the key safe and is a deliberate architecture choice worth mentioning.

> About "RLS": Supabase may warn that Row Level Security is disabled on your tables. For a weekend demo using only the server-side `service_role` key that's fine — but *say out loud in your video* that in production you'd enable RLS and add auth. Naming the tradeoff scores "engineering ownership" points.

---

## 3. Build the agent server (Python + deepagents + FastAPI)

This is the heart of the project. Take your time here.

### 3.1 Create the project folder

Pick a folder for all your work, then:

```bash
mkdir z360-agent
cd z360-agent
python -m venv venv
```

Activate the virtual environment (this isolates your Python packages):
- **Windows (PowerShell):** `venv\Scripts\Activate`
- **Mac/Linux:** `source venv/bin/activate`

You'll see `(venv)` appear at the start of your terminal line. Now install the libraries:

```bash
pip install deepagents langchain langchain-groq fastapi "uvicorn[standard]" supabase python-dotenv pydantic
```

Then create a `requirements.txt` (FastAPI Cloud reads this file to build your
server). **Do NOT use `pip freeze`** — that dumps every package in your venv,
including unused leftovers from earlier experiments, and their transitive pins
can conflict on a clean cloud build (this bit us once: a leftover Google/Gradio
package pinned `grpcio-status` in a way the cloud resolver couldn't satisfy).
Instead, list only what the app actually imports and let the installer resolve
the rest. Create `requirements.txt` with exactly this:

```
fastapi[standard]==0.141.1
pydantic==2.13.4
python-dotenv==1.2.2
groq==0.37.1
deepagents==0.7.0
langchain-groq==1.1.3
langchain-core==1.5.2
langgraph==1.2.10
supabase==2.31.0
```

(Use `fastapi[standard]`, not bare `fastapi` — the `[standard]` extra ships the
`fastapi run` CLI and `uvicorn[standard]` that FastAPI Cloud uses to start your
app. Plain `fastapi` installs but won't launch on the platform.)

### 3.2 Create a `.env` file (your secrets, kept off GitHub)

In the `z360-agent` folder create a file named `.env` with this content (paste your real keys):

```
GROQ_API_KEY=your-groq-api-key
SUPABASE_URL=https://yourproject.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key
```

Also create a file named `.gitignore` so these secrets never get uploaded:

```
venv/
.env
__pycache__/
*.pyc
```

### 3.3 The domain knowledge + tools (`tools.py`)

Create a file `tools.py`. This holds the **custom tools** the agent can call and the **domain knowledge** (the scoring rubric). This is what elevates it from a chatbot to a harness — read the comments so you can explain each piece.

```python
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
    res = (supabase.table("candidates")
           .select("name,score,recommendation")
           .eq("job_id", job_id)
           .order("score", desc=True)
           .execute())
    return json.dumps(res.data)
```

> These three tools (`save_job_description`, `save_candidate_result`, `list_pipeline`) plus the rubric are your "domain knowledge + at least a couple of custom tools" requirement — comfortably met.

### 3.4 The Deep Agent itself (`agent.py`)

Create `agent.py`. This assembles the deep agent: it gives it the tools, the rubric, and a **system prompt** that defines the workflow.

```python
# agent.py
import os
from dotenv import load_dotenv
load_dotenv()  # reads your .env when running locally

from deepagents import create_deep_agent
from langchain_groq import ChatGroq
from tools import (save_job_description, save_candidate_result,
                   list_pipeline, SCORING_RUBRIC, COMPANY_NAME)

# The LLM "brain". Both llama models on Groq are free (no credit card).
#
# WHY llama-3.3-70b-versatile and NOT the smaller 8b-instant:
# The deep-agent harness (planning tool, virtual filesystem, sub-agents, long
# system prompt) needs a capable model to reason its way to a STOP condition.
# The 8b model was too weak: it looped, re-calling tools without ever finishing,
# and hit the graph recursion limit (~25 steps, minutes long). Counterintuitively
# the loop made 8b burn ~15x MORE tokens than one clean 70b run -- so the bigger
# model is both more reliable AND more token-efficient for this workload.
#
# max_retries=1  -> when the per-minute token bucket is drained, fail fast with a
#                   clear error instead of a long internal backoff.
# request_timeout -> hard ceiling on any single LLM call so it can't block forever.
# Idempotency in save_candidate_result (see tools.py) makes any retry safe:
# a replayed run updates the existing row, never inserts a duplicate.
model = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0,
    max_retries=1,
    request_timeout=30,
)

SYSTEM_PROMPT = f"""
You are a Candidate Screening Deep Agent for technical recruiters.
Your job: screen candidates against a job description fairly, consistently,
and with evidence. You reduce bias by scoring only on job-relevant criteria.

WORKFLOW you must follow:
1. When given a job description, extract structured requirements
   (must_have skills, nice_to_have skills, min_years, domain), then call
   save_job_description to persist it. Keep the returned job_id.
2. For EACH resume provided, score it using the rubric below, decide a
   recommendation, write a 2-3 sentence personalized outreach email ONLY if
   the recommendation is 'shortlist', and call save_candidate_result.
   Sign every outreach email as "{COMPANY_NAME}" — never use a placeholder
   like "[Your Name]".
3. When asked, call list_pipeline to give a ranked summary of all candidates.

{SCORING_RUBRIC}

Rules:
- Be concise and structured in your final answer to the user.
- Cite specific resume evidence for every claim. Never fabricate.
- If information is missing, say so rather than guessing.
"""

# Build the deep agent (this is the LangGraph harness under the hood)
agent = create_deep_agent(
    model=model,
    tools=[save_job_description, save_candidate_result, list_pipeline],
    system_prompt=SYSTEM_PROMPT,
)
```

> Note: `create_deep_agent` returns a LangGraph graph. It comes with built-in planning, a virtual file system for scratch notes, and the ability to spawn sub-agents — that's what makes it a "deep" agent. You get all of that for free just by using the library.

### 3.5 Wrap it in a web server (`server.py`)

The frontend needs an address to send requests to. FastAPI gives the agent a URL.

```python
# server.py
import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import RateLimitError
from langgraph.errors import GraphRecursionError
from agent import agent

app = FastAPI(title="Z360 Candidate Screening Agent")

# Allow the browser frontend to call this server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten to your Vercel URL for production
    allow_methods=["*"],
    allow_headers=["*"],
)

class ScreenRequest(BaseModel):
    message: str                  # free-text instruction from the UI

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/screen")
def screen(req: ScreenRequest):
    try:
        # recursion_limit caps how many steps the agent loop may take. A small
        # model can get stuck calling tools in a loop; this stops it after a
        # bounded number of steps instead of running (and billing tokens) forever.
        result = agent.invoke(
            {"messages": [{"role": "user", "content": req.message}]},
            config={"recursion_limit": 15},
        )
    except RateLimitError as e:
        # Groq's free tier enforces TWO token budgets: per-minute (TPM) and
        # per-day (TPD). Waiting a minute only clears the per-minute bucket; if
        # the DAILY budget is exhausted you must wait for the daily reset. We
        # surface Groq's own message so the caller can tell WHICH limit was hit
        # instead of guessing.
        groq_msg = getattr(e, "message", None) or str(e)
        raise HTTPException(
            status_code=429,
            detail=f"Groq rate limit hit — {groq_msg} "
                   "(Free tier has both a per-minute and a per-day token cap. "
                   "If waiting a minute doesn't help, the daily cap is likely "
                   "exhausted; wait for the daily reset or use a lighter model.)",
        )
    except GraphRecursionError:
        # The agent looped without reaching a stop condition and hit the step
        # cap. This usually means the model is too weak for the deep-agent
        # harness. Return a clear 422 instead of an opaque 500.
        raise HTTPException(
            status_code=422,
            detail="The agent could not complete this request within the step "
                   "limit (it looped without finishing). Try rephrasing the "
                   "instruction, or use a more capable model.",
        )
    except Exception as e:
        # Any other unexpected failure -> a clean 500 with a short message.
        raise HTTPException(status_code=500, detail=f"Agent error: {e}")

    # The agent's final reply is the last message
    final = result["messages"][-1].content
    return {"reply": final}
```

> **Why the `try/except` and `recursion_limit`?** These aren't decoration — they came out of a real bug during the build. The deep-agent harness runs a loop: think → call a tool → think again. If the model is too weak, it never decides it's *done* and loops forever. `recursion_limit=15` caps that loop, and LangGraph then raises `GraphRecursionError`, which we turn into a clear 422 instead of a request that hangs for minutes. `RateLimitError` → 429 handles the free tier running out of tokens gracefully. See the "Troubleshooting & engineering decisions" section near the end for the full story — it's worth mentioning in your demo.

### 3.6 Test the agent locally

Start the server:

```bash
uvicorn server:app --reload --port 8000
```

Open a **second** terminal and send it a test (or use the auto-generated docs page at `http://localhost:8000/docs` in your browser — click `/screen` → "Try it out"). A quick curl test:

```bash
curl -X POST http://localhost:8000/screen -H "Content-Type: application/json" -d "{\"message\": \"Job: Junior Python Developer. Must have Python and SQL, 1+ years. Candidate resume: Ali, 2 years Python and Django, built a SQL reporting tool. Screen this candidate.\"}"
```

You should get JSON back with a score and analysis, and a new row should appear in your Supabase **candidates** table (check Table Editor). If it works locally, the hard part is done.

> If you see an auth error: your Groq key or Supabase key in `.env` is wrong. If you see a table error: re-check the SQL from step 2 ran successfully.

### 3.7 Push the agent to GitHub

From inside `z360-agent`:

```bash
git init
git add .
git commit -m "Candidate screening deep agent"
```

Now create an **empty** repo on GitHub named `z360-agent` (github.com → New repository, don't add a README). GitHub shows you two lines to run — they look like:

```bash
git remote add origin https://github.com/YOUR-USERNAME/z360-agent.git
git branch -M main
git push -u origin main
```

Double-check on GitHub that `.env` is **NOT** there (your `.gitignore` should have excluded it). If you see it, delete it from the repo immediately and rotate your keys.

### 3.8 Deploy the agent to FastAPI Cloud (free, no card)

> **Why FastAPI Cloud?** The free-hosting landscape got rough in 2026: Render now
> asks for a credit card even on its free plan, Hugging Face's free CPU tier now
> requires paid PRO to run a Space, and Koyeb closed its free tier to new signups
> after being acquired by Mistral AI. **FastAPI Cloud** is the official cloud
> platform built by the FastAPI team itself. Its **Hobby plan is free with no
> credit card** (3 apps, custom domain), and because it's purpose-built for
> FastAPI, it deploys your **unchanged `server.py`** with a single command — no
> Dockerfile, no wrapper, no config files. `server.py`, `agent.py`, and `tools.py`
> all deploy exactly as they are.
>
> **This host serves your backend, not your frontend.** The task requires a real
> Next.js + Tailwind + shadcn frontend on Vercel (section 4). FastAPI Cloud just
> gives that frontend a live `/screen` endpoint to call.

> **Entrypoint (`main.py`):** FastAPI Cloud's launcher auto-discovers your app by
> looking for `main.py` (then `app.py`) and running the first FastAPI instance it
> finds. Your real app lives in `server.py` and stays **unchanged**, so we add a
> tiny `main.py` that just re-exports it — `from server import app`. That's the
> conventional entrypoint the platform expects, so no `--app` flag or config is
> needed. (The old Hugging Face `app.py` and `Dockerfile` were deleted — they were
> Gradio/HF-only leftovers that would confuse the launcher.)

**How FastAPI Cloud works:** you install its command-line tool, log in (it opens
your browser to authenticate — no card), and run one deploy command from inside
your project folder. It reads your `requirements.txt`, builds your app, and gives
you a live HTTPS URL.

Now deploy. Do all of this in **Windows PowerShell**, from inside your `z360-agent`
folder, with your virtual environment activated:

1. **Install the FastAPI Cloud CLI:**

   ```powershell
   pip install fastapi-cloud-cli
   ```

2. **Log in** (opens a browser window to authenticate your account — sign up here,
   free, no card):

   ```powershell
   fastapi login
   ```

3. **Set your environment variables as secrets.** Your app needs the same three
   keys and `COMPANY_NAME` that are in your local `.env`. FastAPI Cloud injects
   secrets as environment variables at runtime, so `server.py` reads them exactly
   like it reads your local `.env`. Set each one (the CLI will prompt for the value,
   or check `fastapi deploy --help` for the exact secret syntax your installed
   version uses):

   - `GROQ_API_KEY`
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_KEY`
   - `COMPANY_NAME` → `Zikra Infotech` (optional; the code defaults to this)

   > These stay server-side and never touch the frontend or the public repo — the
   > same rule as your local `.env`. The Supabase **service** key in particular must
   > live only here, never in the Next.js app.

4. **Deploy:**

   ```powershell
   fastapi deploy
   ```

   The CLI detects your FastAPI app (via `main.py`), installs `requirements.txt`,
   builds, and deploys. When it finishes it prints your live URL (something like
   `https://z360-agent-XXXX.fastapicloud.app`).

5. **Confirm the backend is live:**
   - Open `https://<your-fastapi-cloud-url>/health` → should return `{"ok": true}`.
     This is the endpoint your Vercel frontend will call.
   - This URL is your **backend base URL** — you'll point the Next.js frontend at it
     in section 4. It is **not** your submission link; the submission link is the
     **Vercel** URL from section 4.

   > You can also test a real screening now with a quick curl (only if your Groq
   > daily token limit hasn't been exhausted):
   > ```powershell
   > curl -X POST https://<your-fastapi-cloud-url>/screen -H "Content-Type: application/json" -d "{\"message\": \"Job: Backend Engineer. Must have Python, FastAPI, PostgreSQL. Please save this job description.\"}"
   > ```

> To redeploy later after code changes, just run `fastapi deploy` again from the
> project folder.

> If the deploy or health check fails: read the CLI's output — the usual culprits
> are a missing/mis-typed secret (e.g. `GROQ_API_KEY`), or the app not being found
> (point it at `server:app` as in step 4). Paste the error and debug from there.

---

## 4. Build the frontend (Next.js + Tailwind + shadcn) — REQUIRED

> **This is a required part of the task.** The challenge explicitly asks for a
> Next.js + Tailwind + shadcn frontend deployed to a **live Vercel link**, and
> that Vercel URL is your submission link. The good news: the hard part is done.
> Your backend is already live on FastAPI Cloud from section 3.8, serving the JSON
> API at `https://<your-fastapi-cloud-url>/screen`. This frontend is a
> separate, small Next.js app that calls that endpoint over HTTP — no backend work
> left, just the UI.

Go back to your top-level folder (not inside `z360-agent`) for this separate project.

### 4.1 Create the Next.js app

```bash
npx create-next-app@latest z360-frontend
```

Answer the prompts like this (arrow keys + Enter):
- TypeScript → **Yes**
- ESLint → **Yes**
- **Tailwind CSS → Yes**
- `src/` directory → **Yes**
- **App Router → Yes**
- Turbopack → Yes
- customize import alias → **No**

Then:

```bash
cd z360-frontend
```

### 4.2 Add shadcn/ui

```bash
npx shadcn@latest init
```

Accept the defaults (base color: Neutral is fine). Then add the components we'll use:

```bash
npx shadcn@latest add button textarea card input badge tabs
```

### 4.3 Point the frontend at your agent

Create a file `.env.local` in `z360-frontend`:

```
NEXT_PUBLIC_AGENT_URL=https://<your-fastapi-cloud-url>
```

Use *your* FastAPI Cloud service URL from step 3.8, with no trailing slash. `NEXT_PUBLIC_` makes it readable in the browser (this URL isn't secret; your keys stay in the FastAPI Cloud secrets, server-side).

### 4.4 Build the screening page

Replace the contents of `src/app/page.tsx` with the code below. This is a simple, polished single-screen interface: paste a JD, paste a resume, click **Screen candidate**, see the agent's result.

```tsx
"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function Home() {
  const [jd, setJd] = useState("");
  const [resume, setResume] = useState("");
  const [reply, setReply] = useState("");
  const [loading, setLoading] = useState(false);

  async function screen() {
    setLoading(true);
    setReply("");
    const message =
      `Job description:\n${jd}\n\n` +
      `Candidate resume:\n${resume}\n\n` +
      `Screen this candidate: save the job if new, score the candidate, ` +
      `and give me the result.`;
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_AGENT_URL}/screen`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      const data = await res.json();
      setReply(data.reply ?? "No response.");
    } catch (e) {
      setReply("Error reaching the agent. It may be waking up — try again in a moment.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Candidate Screening Agent</h1>
        <p className="text-muted-foreground">
          Paste a job description and a resume. The agent scores fit, explains
          why, and drafts outreach for strong matches.
        </p>
      </div>

      <Card>
        <CardHeader><CardTitle>Job description</CardTitle></CardHeader>
        <CardContent>
          <Textarea rows={5} value={jd} onChange={(e) => setJd(e.target.value)}
            placeholder="Paste the job description..." />
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Candidate resume</CardTitle></CardHeader>
        <CardContent>
          <Textarea rows={7} value={resume} onChange={(e) => setResume(e.target.value)}
            placeholder="Paste the candidate's resume..." />
        </CardContent>
      </Card>

      <Button onClick={screen} disabled={loading || !jd || !resume}>
        {loading ? "Screening..." : "Screen candidate"}
      </Button>

      {reply && (
        <Card>
          <CardHeader><CardTitle>Result</CardTitle></CardHeader>
          <CardContent>
            <pre className="whitespace-pre-wrap text-sm">{reply}</pre>
          </CardContent>
        </Card>
      )}
    </main>
  );
}
```

### 4.5 Test the frontend locally

```bash
npm run dev
```

Open `http://localhost:3000`. Paste a short JD and a resume, click **Screen candidate**. If your FastAPI Cloud service is up, you'll get a scored result back in a few seconds. Check Supabase — a new candidate row should appear.

> If nothing happens: open the browser console (F12 → Console) for errors. The usual causes are a wrong `NEXT_PUBLIC_AGENT_URL` (trailing slash, typo) or the backend still waking from a cold start (wait ~30s and retry).

### 4.6 Deploy the frontend to Vercel

1. Push the frontend to its own GitHub repo (same pattern as the agent):

```bash
git init
git add .
git commit -m "Screening frontend"
git remote add origin https://github.com/YOUR-USERNAME/z360-frontend.git
git branch -M main
git push -u origin main
```

2. Go to vercel.com → sign in with GitHub → **Add New → Project** → import `z360-frontend`.
3. Before deploying, expand **Environment Variables** and add:
   - Name: `NEXT_PUBLIC_AGENT_URL`  Value: your FastAPI Cloud service URL (e.g. `https://z360-agent-XXXX.fastapicloud.app`)
4. Click **Deploy**. After ~1 minute you get a live URL like `https://z360-frontend.vercel.app`.
5. Open it and run one real screening end to end. **This URL is what you submit.**

> If it deploys but calls fail: you probably forgot the env var, or added it after deploying. Add it, then Vercel → your project → **Deployments** → **Redeploy**.

---

## 5. Go beyond the spec (to impress, not just pass)

You now meet every requirement. If you have extra hours, add one or two of these — each is small but signals product judgment. Do NOT add all of them; the brief explicitly rewards tight scope. Pick the pipeline view plus one more.

1. **Pipeline view (highest value, low effort).** Add a second tab that lets the user type a job title/ID and calls the agent with "Show me the ranked pipeline for this job." The agent uses your `list_pipeline` tool. Now you can screen 3–4 candidates on camera and show them ranked — a great demo moment that proves the workflow, not just single-shot chat.

2. **Show the score visually.** Parse a score out of the reply and render a shadcn `Badge` (green shortlist / amber maybe / red reject) and a simple progress bar. Small touch, looks polished on video.

3. **Bias-safe framing.** Add one line to the system prompt: "Ignore name, gender, age, and photos; score only job-relevant evidence." Then say in your video that you deliberately designed the agent to reduce screening bias. Reviewers who hire for a living notice this.

4. **Resume file upload.** Accept a `.txt`/`.pdf` upload instead of paste. (PDF parsing adds complexity — only if time allows.)

5. **Streaming responses.** Stream the agent's output token-by-token for a snappier feel. Nice-to-have, not essential.

> Interview-ready framing: when you add a feature, be ready to say *why you stopped where you did*. "I scoped to single-JD screening with a pipeline view because the brief rewards one workflow done well; multi-role support was my next step." That sentence is worth real points under "engineering ownership."

---

## 6. Record the demo video (3–5 minutes)

Record your screen with audio. Free tools: Loom (loom.com), or OBS Studio, or on Mac QuickTime. Upload to Loom/YouTube (unlisted) or Google Drive set to "Anyone with the link can view."

Follow this exact structure and timing — reviewers scan for these beats:

- **0:00–0:30 — The problem.** "Recruiters waste hours manually screening resumes against a JD, and it's inconsistent and biased. I built a Candidate Screening Deep Agent that does it in seconds with an auditable rubric."
- **0:30–2:00 — Live demo.** Open your Vercel URL. Paste a real JD. Screen two contrasting candidates (one strong, one weak). Read out the score, the evidence-based reasoning, and the drafted outreach for the strong one. Then show the ranked pipeline view.
- **2:00–3:30 — Harness design.** Show `agent.py` and `tools.py` in your editor. Explain: "It's a LangGraph deep agent from the `deepagents` library. It has domain knowledge — this scoring rubric — and three custom tools that parse the JD, persist scored candidates to Supabase, and rank the pipeline. The system prompt enforces a fixed workflow, so it's a real harness, not a chatbot." Show a row appearing in Supabase.
- **3:30–4:30 — Architecture & tradeoffs.** Show the diagram (from section 0). "Frontend on Vercel, Python agent on FastAPI Cloud, Supabase for persistence. I kept the DB key server-side only. Known limitations: free-tier cold starts, no auth/RLS yet. With more time I'd add authentication, RLS, and multi-role pipelines."

Speak clearly, keep it moving, and make sure the live product is actually working before you hit record (wake the backend first by hitting `/health`).

---

## 7. Write the short written note

Create a `README.md` in your frontend repo (and/or a shared doc). Keep it to about one page. Use these headings — they map directly to the challenge's evaluation table:

```markdown
# Candidate Screening Deep Agent

**Live app:** https://your-app.vercel.app
**Frontend repo:** https://github.com/you/z360-frontend
**Agent repo:** https://github.com/you/z360-agent
**Demo video:** https://your-video-link

## The problem
Recruiters screen many resumes against a job description manually. It's slow,
inconsistent, and prone to bias. This agent screens a candidate against a JD in
seconds, scores fit against a transparent rubric with cited evidence, recommends
shortlist/maybe/reject, and drafts outreach for strong matches — then ranks the
whole pipeline.

## How the harness is designed
A LangGraph Deep Agent (LangChain `deepagents`) with:
- **Domain knowledge:** a weighted scoring rubric baked into the system prompt.
- **Custom tools:** save_job_description, save_candidate_result, list_pipeline.
- **Workflow:** parse JD → score each resume → persist → rank pipeline.
The agent plans and calls tools autonomously rather than just replying in text.

## Architecture
Next.js + Tailwind + shadcn on Vercel → FastAPI + deepagents on FastAPI Cloud →
Supabase (Postgres) for persistence. DB service key lives only on the server.

## What it does well / scope
One workflow — screening against a single JD — done end to end. Scoped tightly
on purpose per the brief.

## How long it took
~[X] hours over the weekend. [Breakdown: agent Y hrs, frontend Z hrs, deploy.]

## What I'd build next
Auth + Supabase RLS; multi-role pipelines; resume PDF parsing; interview-question
generation per candidate; eval set to measure scoring consistency.

## Known limitations
Free-tier cold starts (first request after idle); no auth yet; single-JD at a time.
```

Be honest about time and limitations — the reviewers explicitly value candidates who can explain tradeoffs and next steps.

---

## 8. Submit

Email **talent@zikrainfotech.com**. Before you send, verify every link opens in an incognito/private browser window (this catches "works on my machine" permission mistakes).

Submission email template:

```
Subject: Take-Home Challenge Submission — Abdullah Daoud (Jr. Software Engineer)

Hi Zikra team,

Thank you for the opportunity. My completed challenge is a Candidate Screening
Deep Agent — a tool that screens candidate resumes against a job description,
scores fit against a transparent rubric, and drafts outreach for strong matches.

- Live app: https://your-app.vercel.app
- Frontend repo: https://github.com/you/z360-frontend
- Agent repo: https://github.com/you/z360-agent
- Demo video (3–5 min): https://your-video-link
- Written note: included in the repo README (and linked above)

All links are set to "anyone with the link can view." The agent server is on a
free tier, so the first request after idle may take ~40 seconds to wake.

Happy to walk through the code and decisions in a follow-up call.

Best regards,
Abdullah Daoud
```

### Final submission checklist
- [ ] Live Vercel URL opens and screens a candidate successfully (tested in incognito)
- [ ] Both GitHub repos are public (or shared) and contain no secrets / no `.env`
- [ ] Demo video is 3–5 min, link viewable by anyone
- [ ] Written note covers: problem, harness design, what it does, time taken, what's next
- [ ] FastAPI Cloud secrets set; `/health` returns ok
- [ ] Supabase tables receive rows when you screen
- [ ] You woke the backend right before recording and right before submitting

---

## 8.5 Troubleshooting & engineering decisions (read this — it's your best interview material)

During the real build, one bug taught more than the rest of the project combined. Understanding it is what separates "I pasted a tutorial" from "I engineer systems." Here is the whole story, so you can tell it confidently.

### The symptom: `/screen` hangs forever

With the model set to Groq's small `llama-3.1-8b-instant`, a normal request to `/screen` — for example *"Show me the candidate pipeline for job &lt;id&gt;, ranked by score"* — never came back. No error, no response. Pressing **Ctrl+C** in the uvicorn terminal didn't reveal anything useful either.

**Why Ctrl+C was useless (worth knowing):** FastAPI runs a synchronous `def` endpoint in a worker thread from a threadpool. `Ctrl+C` interrupts the *main* thread and dumps *its* traceback — but the code was blocked inside `agent.invoke` on a *worker* thread. So the traceback never pointed at the real culprit. This is a genuinely confusing gotcha and a great thing to be able to explain.

### The diagnosis: isolate each moving part

Instead of guessing, I wrote a throwaway script (`diagnose.py`) that timed each layer independently, *outside* uvicorn:

1. **Raw LLM call** (`model.invoke`) — came back in ~5.6s. ✅ Groq and the API key are fine.
2. **Supabase query** (`list_pipeline.invoke`) — ~1.2s. ✅ The DB and tool are fine.
3. **Full agent** (`agent.invoke`) — ran for **253 seconds** and then failed with `GraphRecursionError`. ❌ Found it.

The lesson: when something hangs, don't stare at the whole system — split it into pieces and time each one. The slowest/failing piece is your answer.

### The root cause: the model was too weak for the harness

A deep agent isn't a single LLM call. `create_deep_agent` wraps the model in a LangGraph loop with a planning/todo tool, a virtual filesystem, sub-agent scaffolding, and a long system prompt. That loop runs *think → act → think* until the model decides it is **done**.

The 8b model wasn't capable enough to reliably reach that "done" state on this harness. It kept calling tools and re-planning in circles, never stopping — until it hit LangGraph's recursion ceiling and threw `GraphRecursionError`.

### The fix and the counter-intuitive lesson

Switching to the larger `llama-3.3-70b-versatile` (also free, no credit card on Groq) fixed it: the agent converges and returns in a few seconds.

The counter-intuitive part — and the best line for your interview: **the bigger model was both more reliable *and* cheaper in tokens.** The 8b model's endless loop burned roughly **15× more tokens** than a single clean 70b run. "Use the smaller model to save money" was exactly backwards here. For an agentic harness, a model that finishes in one pass beats a cheap model that loops. Capability *is* efficiency.

### The guardrails I added so it fails loud, not silent

A hang is the worst failure mode — you can't tell if it's working. So I made failures fast and legible:

- `recursion_limit=15` on `agent.invoke` — caps the loop so a bad run ends in seconds, not minutes.
- `request_timeout=30` and `max_retries=1` on `ChatGroq` — no single call can block forever, and a drained rate limit fails fast instead of silently backing off.
- `try/except` in `/screen` mapping `RateLimitError` → **429** and `GraphRecursionError` → **422**, so the caller gets an actionable status code instead of a hung socket or an opaque 500.
- Idempotency in `save_candidate_result` (match on `job_id + name`, then UPDATE-or-INSERT) — so a retried or replayed run never creates duplicate rows.

> If you only remember one thing for the interview: *"I had a silent hang. I isolated each layer with a timing script, found the deep-agent loop was the culprit, root-caused it to an under-powered model hitting the recursion limit, and fixed it by moving to a stronger model — which was actually cheaper in tokens because it stopped looping. Then I added a recursion cap, timeouts, and typed error responses so the failure mode is loud instead of silent."* That single paragraph demonstrates debugging methodology, systems understanding, and production instincts all at once.

---

## 9. Prep for the follow-up interview

They will ask about your decisions. Have crisp answers ready:

- **"Why this problem?"** It's your reviewers' own domain; the brief lists recruiting first; it's a clean fit for a real workflow.
- **"What makes it a deep agent, not a chatbot?"** It plans, calls custom tools, follows an enforced workflow, and persists state — versus a chatbot that just returns text.
- **"Walk me through the architecture."** Use the diagram; explain why the DB key is server-side only.
- **"What are the failure modes?"** LLM could hallucinate resume facts (mitigated by "cite evidence, never fabricate" instruction); cold starts; no auth yet; scoring could drift without an eval set. **Also mention the real one you hit:** an under-powered model looping in the agent harness until it hit the recursion limit — see section 8.5 for the full debugging story, which is your strongest talking point.
- **"What would you do with more time?"** Auth + RLS, multi-role pipelines, an evaluation set to measure scoring consistency, PDF parsing.
- **"Where did you use AI tools?"** Be honest — they expect it. Say you used AI to scaffold code and speed up boilerplate, and that you understand and can defend every part (which is why you're reading this guide, not just pasting it).

> The single biggest differentiator: **understand your own code.** Read through `agent.py`, `tools.py`, and `page.tsx` until you can explain each line in your own words. That is what turns a good submission into an offer.

---

## Quick reference: the whole thing in order

1. Create accounts (GitHub, Supabase, Vercel, FastAPI Cloud, Groq). Install Node, Python, Git, VS Code.
2. Supabase: new project → run the SQL → copy URL + service key.
3. Agent: `z360-agent` folder → venv → install libs → `.env` → `tools.py`, `agent.py`, `server.py` → test locally.
4. Push agent to GitHub → deploy to FastAPI Cloud (`fastapi deploy`) with secrets → test `/health`.
5. Frontend: `create-next-app` → shadcn init + components → `.env.local` → `page.tsx` → test locally.
6. Push frontend to GitHub → deploy to Vercel with `NEXT_PUBLIC_AGENT_URL` → test live.
7. (Optional) Add pipeline view + one polish feature.
8. Record 3–5 min video. Write the note/README.
9. Verify all links in incognito → email talent@zikrainfotech.com.
10. Study your own code for the interview.

You've got a week — this is comfortably a two-day build. Go one section at a time, test each piece before moving on, and don't skip the local tests. Good luck.

---

### Sources
- [deepagents · PyPI](https://pypi.org/project/deepagents/0.2.5)
- [Deep Agents Quickstart — LangChain docs](https://docs.langchain.com/oss/python/deepagents/quickstart)


