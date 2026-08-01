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