# diagnose.py — isolates WHERE a /screen request blocks.
# Run this OUTSIDE uvicorn so a Ctrl+C gives a real, useful traceback.
#   (venv) > python diagnose.py
#
# It times three layers independently:
#   1. Raw LLM call          -> is Groq itself reachable / rate-limited?
#   2. list_pipeline (no LLM)-> is the Supabase query fast? (it should be instant)
#   3. Full agent.invoke     -> does the agent LOOP or hang on the LLM?
# Whichever step is slow or errors is our culprit.

import time
from dotenv import load_dotenv
load_dotenv()

JOB_ID = "d1980ca3-c7b6-4ffd-987c-3b2508ca169d"

def timed(label, fn):
    print(f"\n=== {label} ===", flush=True)
    t0 = time.time()
    try:
        out = fn()
        dt = time.time() - t0
        print(f"OK in {dt:.1f}s", flush=True)
        print("result:", str(out)[:500], flush=True)
    except Exception as e:
        dt = time.time() - t0
        print(f"FAILED after {dt:.1f}s -> {type(e).__name__}: {e}", flush=True)

# --- Step 1: raw LLM call (tiny, ~10 tokens) ---
def step1():
    from agent import model
    return model.invoke("Reply with the single word: pong").content
timed("1. RAW LLM CALL", step1)

# --- Step 2: Supabase query directly, no LLM involved ---
def step2():
    from tools import list_pipeline
    return list_pipeline.invoke({"job_id": JOB_ID})
timed("2. list_pipeline DIRECT (no LLM)", step2)

# --- Step 3: the full agent (what /screen actually does) ---
def step3():
    from agent import agent
    result = agent.invoke(
        {"messages": [{"role": "user",
                       "content": f"Show me the candidate pipeline for job {JOB_ID}, ranked by score."}]},
        {"recursion_limit": 15},
    )
    return result["messages"][-1].content
timed("3. FULL agent.invoke", step3)

print("\nDone.", flush=True)
