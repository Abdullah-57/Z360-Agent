# agent.py
import os
from dotenv import load_dotenv
load_dotenv()  # reads your .env when running locally

from deepagents import create_deep_agent
from langchain_groq import ChatGroq
from tools import (save_job_description, save_candidate_result,
                   list_pipeline, SCORING_RUBRIC, COMPANY_NAME)

# The LLM "brain". Both models below are free on Groq (no credit card).
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