---
title: Z360 Candidate Screening Agent
emoji: 🤖
colorFrom: blue
colorTo: indigo
sdk: gradio
app_file: app.py
pinned: false
---

# Z360 Candidate Screening Deep Agent

A deep agent that screens candidate resumes against a job description — scoring
each candidate on job-relevant criteria, recommending shortlist/maybe/reject with
cited evidence, and drafting outreach emails for shortlisted candidates.

Built with **deepagents** (LangGraph harness) + **LangChain**, served over
**FastAPI**, using **Groq** (llama-3.3-70b-versatile) as the LLM and **Supabase**
(Postgres) for storage.

## Interfaces

- **Gradio UI** (`app.py`) — the live demo on this Space: paste a JD + resume, get
  a screening result.
- **FastAPI JSON API** (`server.py`) — the programmatic interface, kept in the repo:
  - `GET /health` → `{"ok": true}`
  - `POST /screen` with JSON body `{"message": "..."}` → screening result as JSON

## Configuration

Set these as **Secrets** in the Space settings (never commit them):

- `GROQ_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`
- `COMPANY_NAME` (optional; defaults to "Zikra Infotech")

Built as a take-home challenge for Zikra Infotech.
