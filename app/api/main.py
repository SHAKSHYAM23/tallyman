import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from app.agent.graph import build_graph
from app.agent.llm import ask_fn, explain_fn, extract_fn
from app.agent.mcp_client import open_tool_runner
from app.api.schemas import ChatRequest, ChatResponse
from app.core import config

log = logging.getLogger("tallyman")

CONFIRM_HINT = "\n\nWant to change anything, like the rate or the amount? Tell me, or say no thanks."


def fresh_run(message):
    return {
        "user_input": message,
        "decision_type": None,
        "slots": {},
        "missing": [],
        "question": "",
        "ask_count": 0,
        "changed": False,
        "confirming": False,
        "results": {},
        "explanation": "",
        "status": "running",
    }


def pending_interrupt(snapshot):
    for task in snapshot.tasks:
        if task.interrupts:
            return task.interrupts[0].value
    return None


def build_response(snapshot):
    pending = pending_interrupt(snapshot)

    if pending and pending["type"] == "ask":
        return ChatResponse(reply=pending["question"], status="awaiting_input")

    if pending:
        return ChatResponse(
            reply=pending["explanation"] + CONFIRM_HINT,
            status="awaiting_input",
            tool_results=pending["results"],
        )

    values = snapshot.values
    status = values.get("status", "done")

    if status == "done":
        return ChatResponse(
            reply="Sounds good. Describe another money decision whenever you like.",
            status="done",
        )

    return ChatResponse(reply=values.get("explanation", "Something went wrong."), status=status)


def create_app(graph=None):
    @asynccontextmanager
    async def lifespan(app):
        if graph is not None:
            app.state.graph = graph
            yield
            return

        async with open_tool_runner() as tool_runner:
            app.state.graph = build_graph(
                extract_fn=extract_fn,
                ask_fn=ask_fn,
                explain_fn=explain_fn,
                tool_runner=tool_runner,
                checkpointer=MemorySaver(),
                max_asks=config.MAX_ASKS,
            )
            yield

    app = FastAPI(title="Tallyman", lifespan=lifespan)

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.post("/chat", response_model=ChatResponse)
    async def chat(body: ChatRequest, request: Request):
        graph = request.app.state.graph
        run_config = {"configurable": {"thread_id": body.session_id}}

        try:
            snapshot = await graph.aget_state(run_config)
            if pending_interrupt(snapshot) is not None:
                await graph.ainvoke(Command(resume=body.message), run_config)
            else:
                await graph.ainvoke(fresh_run(body.message), run_config)
            snapshot = await graph.aget_state(run_config)
        except Exception:
            log.exception("chat request failed")
            raise HTTPException(
                status_code=502,
                detail="The assistant had trouble reaching the language model. Please try again in a moment.",
            )

        return build_response(snapshot)

    @app.get("/session/{session_id}")
    async def session_state(session_id: str, request: Request):
        snapshot = await request.app.state.graph.aget_state(
            {"configurable": {"thread_id": session_id}}
        )
        return {
            "decision_type": snapshot.values.get("decision_type"),
            "slots": snapshot.values.get("slots", {}),
            "status": snapshot.values.get("status"),
        }

    return app


app = create_app()