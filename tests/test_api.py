import re

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver

from app.agent.graph import build_graph
from app.api.main import create_app
from app.finance.tools import TOOL_FUNCS


async def fake_extract(user_text, decision_type, slots):
    t = user_text.lower()
    if "boom" in t:
        raise RuntimeError("llm is down")
    found = {}
    if m := re.search(r"(\d+(?:\.\d+)?)\s*lakh\s+loan", t):
        found["principal"] = float(m.group(1)) * 100_000
    if m := re.search(r"(\d+(?:\.\d+)?)\s*%", t):
        found["annual_rate"] = float(m.group(1))
    if m := re.search(r"(\d+(?:\.\d+)?)\s*years?", t):
        found["years"] = float(m.group(1))
    if m := re.search(r"earn\s+(\d+(?:\.\d+)?)\s*lakh", t):
        found["monthly_income"] = float(m.group(1)) * 100_000
    return {"decision_type": "loan_affordability" if "loan" in t else None, "slots": found}


async def fake_ask(decision_type, missing):
    return "Please tell me: " + ", ".join(missing)


async def fake_explain(decision_type, slots, results):
    return f"Your EMI is about {results['calculate_emi']['emi']:.0f} a month."


async def local_runner(name, args):
    return TOOL_FUNCS[name](**args)


@pytest.fixture
def client():
    graph = build_graph(
        extract_fn=fake_extract,
        ask_fn=fake_ask,
        explain_fn=fake_explain,
        tool_runner=local_runner,
        checkpointer=MemorySaver(),
    )
    with TestClient(create_app(graph)) as c:
        yield c


def chat(client, session, message):
    return client.post("/chat", json={"session_id": session, "message": message})


def test_health(client):
    assert client.get("/health").json() == {"ok": True}


def test_full_conversation_over_http(client):
    r = chat(client, "s1", "Can I afford a 40 lakh loan?").json()
    assert r["status"] == "awaiting_input"
    assert "annual_rate" in r["reply"]
    assert r["tool_results"] == {}

    r = chat(client, "s1", "8.5% for 20 years, I earn 1 lakh a month").json()
    assert r["status"] == "awaiting_input"
    assert "34713" in r["reply"]
    assert r["tool_results"]["affordability_check"]["verdict"] == "comfortable"

    r = chat(client, "s1", "no thanks").json()
    assert r["status"] == "done"

    r = chat(client, "s1", "Can I afford a loan?").json()
    assert r["status"] == "awaiting_input"
    assert "principal" in r["reply"]


def test_sessions_are_separate(client):
    chat(client, "a", "Can I afford a 40 lakh loan?")
    r = chat(client, "b", "Can I afford a loan?").json()
    assert "principal" in r["reply"]
    assert client.get("/session/a").json()["slots"]["principal"] == 4_000_000
    assert client.get("/session/b").json()["slots"] == {}


def test_gives_up_status_is_returned(client):
    chat(client, "g", "hello about a loan")
    for _ in range(3):
        r = chat(client, "g", "blah").json()
    assert r["status"] == "gave_up"


@pytest.mark.parametrize("body", [
    {"session_id": "x", "message": ""},
    {"session_id": "", "message": "hi"},
    {"message": "hi"},
])
def test_bad_requests_are_rejected(client, body):
    assert client.post("/chat", json=body).status_code == 422


def test_llm_failure_becomes_a_clean_502(client):
    r = chat(client, "e", "boom")
    assert r.status_code == 502
    assert "try again" in r.json()["detail"].lower()
    assert "llm is down" not in r.text
