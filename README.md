# Z360 Candidate Screening Deep Agent

A deep agent that screens candidate resumes against a job description — scoring
each candidate on job-relevant criteria, recommending shortlist/maybe/reject with
cited evidence, and drafting outreach emails for shortlisted candidates.

Built with **deepagents** (LangGraph harness) + **LangChain**, served over
**FastAPI**, using **Groq** (llama-3.3-70b-versatile) as the LLM and **Supabase**
(Postgres) for storage. Deployed on **FastAPI Cloud** (free Hobby tier).

## API

- `GET /health` → `{"ok": true}`
- `POST /screen` with JSON body `{"message": "..."}` → screening result as JSON
  `{"reply": "..."}`

## Run locally

```bash
python -m venv venv
# Windows: venv\Scripts\activate   |   macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --reload
```

Then open `http://localhost:8000/docs` for the interactive API, or POST to
`/screen`.

## Configuration

Set these as environment variables (locally via a `.env` file, on FastAPI Cloud as
service secrets — never commit them):

- `GROQ_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`
- `COMPANY_NAME` (optional; defaults to "Zikra Infotech")

## Deploy (FastAPI Cloud)

```bash
pip install fastapi-cloud-cli
fastapi login
fastapi deploy
```

The CLI reads `requirements.txt` and deploys `server.py` — no Dockerfile or config
needed. Set the environment variables above as secrets before deploying.

Built as a take-home challenge for Zikra Infotech.
