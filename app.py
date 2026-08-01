# app.py — Hugging Face Spaces entrypoint (free Gradio SDK).
#
# WHY this file exists and what it does NOT change:
# The task requires a Next.js/Vercel frontend that calls the agent's FastAPI
# endpoints (/screen, /health) over HTTP. Those endpoints live in server.py and
# are UNCHANGED. But free hosts that run raw uvicorn now want a credit card, and
# HF's Docker SDK is paid — only HF's *Gradio* SDK is free. Gradio runs on
# Starlette (same base as FastAPI), so we can MOUNT our existing FastAPI app onto
# the Gradio server. Result: the free Gradio Space serves BOTH:
#   - your real FastAPI JSON API  ->  https://<user>-z360-agent.hf.space/screen
#                                     https://<user>-z360-agent.hf.space/health
#   - a small Gradio debug UI     ->  https://<user>-z360-agent.hf.space/ui
# server.py, agent.py, tools.py are all imported as-is. Nothing in them changes.
import os
from dotenv import load_dotenv
load_dotenv()  # local .env; on HF Spaces the Secrets are injected as env vars

import gradio as gr

# Import the EXISTING FastAPI app (with /health and /screen) unchanged, plus the
# same agent it uses so the debug UI runs the identical screening path.
from server import app as fastapi_app
from agent import agent
from groq import RateLimitError
from langgraph.errors import GraphRecursionError


def _run_agent(message: str) -> str:
    """Debug-UI helper: same invoke + error handling as server.py's /screen,
    returned as text. This is only for the optional Gradio UI at /ui; the real
    frontend uses the JSON /screen endpoint from server.py."""
    if not message or not message.strip():
        return "Please enter a job description and/or a candidate resume to screen."
    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": message}]},
            config={"recursion_limit": 15},
        )
    except RateLimitError as e:
        groq_msg = getattr(e, "message", None) or str(e)
        return f"⚠️ Groq rate limit hit — {groq_msg}"
    except GraphRecursionError:
        return ("⚠️ The agent hit the step limit without finishing "
                "(looped). Try rephrasing or a more capable model.")
    except Exception as e:
        return f"⚠️ Agent error: {e}"
    return result["messages"][-1].content


with gr.Blocks(title="Z360 Candidate Screening Agent — debug UI") as demo:
    gr.Markdown(
        "# 🤖 Candidate Screening Deep Agent — debug UI\n"
        "This is a lightweight built-in UI for sanity-checking the agent. The "
        "real product frontend is the Next.js app on Vercel, which calls this "
        "same service's `POST /screen` JSON endpoint."
    )
    inp = gr.Textbox(label="Instruction (JD + resume, or 'show the pipeline')",
                     lines=10)
    btn = gr.Button("Screen", variant="primary")
    out = gr.Markdown(label="Result")
    btn.click(fn=_run_agent, inputs=inp, outputs=out)

# Mount the Gradio debug UI onto the FastAPI app at /ui, then expose the FastAPI
# app as the ASGI application HF runs. This keeps /health and /screen at the root
# (where the frontend expects them) and puts the optional UI at /ui.
app = gr.mount_gradio_app(fastapi_app, demo, path="/ui")

# HF's Gradio SDK looks for a launchable `demo`; mounting above already wires the
# UI into FastAPI. Running this file directly (locally) serves everything on 7860.
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 7860)))
