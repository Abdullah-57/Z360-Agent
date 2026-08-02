# agent.py
import os
from dotenv import load_dotenv
load_dotenv()  # reads your .env when running locally

from deepagents import create_deep_agent
from langchain_groq import ChatGroq
from tools import (screen_candidate, list_pipeline,
                   SCORING_RUBRIC, COMPANY_NAME)

# The LLM "brain". Both models below are free on Groq (no credit card).
#
# MODEL CHOICE — llama-3.1-8b-instant vs llama-3.3-70b-versatile:
# Earlier this agent used two save tools and made the model thread a Postgres
# uuid between them. That chaining was hard for a small model, so we ran on the
# 70b model. Once the two tools were merged into ONE atomic screen_candidate
# (the job id is now created and linked in Python — the model never handles it),
# the model's job got much simpler: extract fields, score, and make a single
# tool call. The 8b model handles that reliably, and — importantly for a free
# account — it draws on a SEPARATE, larger daily token budget than the 70b model,
# so it keeps working when the 70b daily cap is exhausted.
#
# To switch back to the higher-quality 70b (e.g. to record a polished demo when
# its daily budget is fresh), just change the model string below to
# "llama-3.3-70b-versatile". Nothing else needs to change.
#
# max_retries=1  -> when the per-minute token bucket is drained, fail fast with a
#                   clear error instead of a long internal backoff.
# request_timeout -> hard ceiling on any single LLM call so it can't block forever.
# Idempotency in screen_candidate (see tools.py) makes any retry safe:
# a replayed run updates the existing rows, never inserts a duplicate.
model = ChatGroq(
    model="llama-3.1-8b-instant",
    temperature=0,
    max_retries=1,
    request_timeout=30,
)

SYSTEM_PROMPT = f"""
You are a Candidate Screening Deep Agent for technical recruiters.
Your job: screen candidates against a job description fairly, consistently,
and with evidence. You reduce bias by scoring only on job-relevant criteria.

WORKFLOW you must follow:
1. When given a job description, extract structured requirements:
   must_have skills, nice_to_have skills, min_years, domain. Also pick a short
   job_title (e.g. "Backend Engineer") from the description.
2. For EACH resume provided, score it using the rubric below, decide a
   recommendation, and write a 2-3 sentence personalized outreach email ONLY if
   the recommendation is 'shortlist'. Then call screen_candidate ONCE, passing
   BOTH the job fields (job_title, job_raw_text, job_parsed_json) AND the
   candidate fields (name, resume_text, score, recommendation, analysis_json,
   outreach_email) together. This single tool saves the job and the candidate
   atomically and links them for you — you never handle a job id yourself.
   Sign every outreach email as "{COMPANY_NAME}" — never use a placeholder
   like "[Your Name]".
3. When asked for the pipeline, call list_pipeline. Pass the job_title to pick
   the role, or leave it empty for the most recent job. Never pass an id.

{SCORING_RUBRIC}

Rules:
- Be concise and structured in your final answer to the user.
- Cite specific resume evidence for every claim. Never fabricate.
- If information is missing, say so rather than guessing.
"""

# Build the deep agent (this is the LangGraph harness under the hood)
agent = create_deep_agent(
    model=model,
    tools=[screen_candidate, list_pipeline],
    system_prompt=SYSTEM_PROMPT,
)