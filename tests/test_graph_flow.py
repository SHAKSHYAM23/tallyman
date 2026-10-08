"""Tests for the LangGraph conversation flow. No real LLM, no network.

The graph's four "outside world" dependencies are injected, so tests swap in
fakes while production wires in Groq (via LangChain) and the MCP client:

    build_graph(*, extract_fn, ask_fn, explain_fn, tool_runner,
                checkpointer=None, max_asks=3) -> compiled graph

    extract_fn(user_text, decision_type, slots) -> {"decision_type": str | None,
                                                    "slots": dict}
        Returns ONLY newly found fields. decision_type=None means "unchanged".
    ask_fn(decision_type, missing) -> str
        One natural follow-up question covering the missing fields.
    explain_fn(decision_type, slots, results) -> str
        Plain-language explanation built only from `results`.
    tool_runner(tool_name, args) -> dict
        Production: MCP tool call. Tests: app.finance.tools.TOOL_FUNCS.

Graph behaviour these tests pin down
------------------------------------
Input to start a run:      {"user_input": "<text>"}
Resume after an interrupt: Command(resume="<user reply>")

Interrupt payloads:
    {"type": "ask",     "question": str}
    {"type": "confirm", "explanation": str, "results": dict}

Flow: extract -> check_missing -> (ask_user <-> extract)* -> run_calcs
      -> explain -> confirm. At confirm, a reply that changes any slot
      re-runs the calculations; a reply that changes nothing finishes the run.
      After `max_asks` unanswered questions the run ends with status "gave_up".

Final state values: status ("done" | "gave_up"), decision_type, slots,
results ({tool_name: output}), explanation.

loan_affordability needs: principal, annual_rate, years, monthly_income
(existing_emis is optional and defaults to 0) and runs, in order,
calculate_emi then affordability_check.
"""

import re

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from app.agent.graph import build_graph
from app.finance.tools import TOOL_FUNCS

LOAN = "loan_affordability"



async def fake_extract(user_text, decision_type, slots):
    """Tiny regex stand-in for the LLM extractor."""
    t = user_text.lower()
    found = {}
    if m := re.search(r"(\d+(?:\.\d+)?)\s*lakh\s+loan", t):
        found["principal"] = float(m.group(1)) * 100_000
    if m := re.search(r"(\d+(?:\.\d+)?)\s*%", t):
        found["annual_rate"] = float(m.group(1))
    if m := re.search(r"(\d+(?:\.\d+)?)\s*years?", t):
        found["years"] = float(m.group(1))
    if m := re.search(r"earn\s+(\d+(?:\.\d+)?)\s*lakh", t):
        found["monthly_income"] = float(m.group(1)) * 100_000
    return {"decision_type": LOAN if "loan" in t else None, "slots": found}


async def extract_nothing(user_text, decision_type, slots):
    return {"decision_type": LOAN, "slots": {}}


async def fake_ask(decision_type, missing):
    return "Please tell me: " + ", ".join(missing)


async def fake_explain(decision_type, slots, results):
    emi = results["calculate_emi"]["emi"]
    verdict = results["affordability_check"]["verdict"]
    return f"Your EMI is about {emi:.0f} per month ({verdict})."


async def local_tool_runner(tool_name, args):
    return TOOL_FUNCS[tool_name](**args)



def make_graph(extract_fn=fake_extract, max_asks=3):
    return build_graph(
        extract_fn=extract_fn,
        ask_fn=fake_ask,  
         explain_fn=fake_explain,
        tool_runner=local_tool_runner,
        checkpointer=MemorySaver(),
        max_asks=max_asks,
    )


def cfg(thread_id):
    return {"configurable": {"thread_id": thread_id}}


async def start(graph, text, thread_id):
    return await graph.ainvoke({"user_input": text}, cfg(thread_id))


async def reply(graph, text, thread_id):
    return await graph.ainvoke(Command(resume=text), cfg(thread_id))


async def pending(graph, thread_id):
    """The payload of the interrupt the graph is currently paused on, or None."""
    snapshot = await graph.aget_state(cfg(thread_id))
    for task in snapshot.tasks:
        if task.interrupts:
            return task.interrupts[0].value
    return None


async def values(graph, thread_id):
    return (await graph.aget_state(cfg(thread_id))).values



async def test_asks_for_missing_details_then_computes_and_finishes():
    g, t = make_graph(), "happy"

    await start(g, "Can I afford a 40 lakh loan?", t)
    ask = await pending(g, t)
    assert ask["type"] == "ask"
    for field in ("annual_rate", "years", "monthly_income"):
        assert field in ask["question"]
    assert "principal" not in ask["question"] 

    await reply(g, "8.5% for 20 years, I earn 1 lakh a month", t)
    confirm = await pending(g, t)
    assert confirm["type"] == "confirm"
    assert "34713" in confirm["explanation"]
    assert confirm["results"]["affordability_check"]["verdict"] == "comfortable"

    await reply(g, "no thanks", t)  # changes nothing -> run finishes
    assert await pending(g, t) is None
    final = await values(g, t)
    assert final["status"] == "done"
    assert final["decision_type"] == LOAN
    assert final["results"]["calculate_emi"]["emi"] == pytest.approx(34712.93, abs=0.01)


async def test_everything_in_one_message_skips_the_questions():
    g, t = make_graph(), "oneshot"

    await start(
        g, "Can I afford a 40 lakh loan at 8.5% for 20 years? I earn 1 lakh a month", t
    )
    payload = await pending(g, t)
    assert payload["type"] == "confirm"  # went straight to results


async def test_user_can_tweak_an_assumption_and_get_new_numbers():
    g, t = make_graph(), "tweak"

    await start(g, "Can I afford a 40 lakh loan at 8.5% for 20 years? I earn 1 lakh a month", t)
    first = await pending(g, t)

    await reply(g, "what if the rate is 9%", t)
    second = await pending(g, t)

    assert second["type"] == "confirm"
    new_emi = TOOL_FUNCS["calculate_emi"](principal=4_000_000, annual_rate=9, years=20)["emi"]
    assert f"{new_emi:.0f}" in second["explanation"]
    assert second["explanation"] != first["explanation"]
    assert (await values(g, t))["slots"]["annual_rate"] == 9


async def test_gives_up_after_max_asks_instead_of_looping_forever():
    g, t = make_graph(extract_fn=extract_nothing, max_asks=3), "stuck"

    await start(g, "help me with a loan", t)
    for _ in range(3):
        assert (await pending(g, t))["type"] == "ask"
        await reply(g, "blah", t)

    assert await pending(g, t) is None
    final = await values(g, t)
    assert final["status"] == "gave_up"
    assert not final.get("results")


async def test_sessions_do_not_leak_into_each_other():
    g = make_graph()

    await start(g, "Can I afford a 40 lakh loan?", "alice")
    await start(g, "Can I afford a loan?", "bob")

    alice = await pending(g, "alice")
    bob = await pending(g, "bob")
    assert "principal" not in alice["question"] 
    assert "principal" in bob["question"]  
    assert "principal" not in (await values(g, "bob"))["slots"]