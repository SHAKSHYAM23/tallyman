from langgraph.types import interrupt

from app.agent.state import DEFAULTS, REQUIRED_SLOTS


def full_slots(state):
    return {**DEFAULTS.get(state.get("decision_type"), {}), **state.get("slots", {})}


def make_extract(extract_fn):
    async def extract(state):
        slots = dict(state.get("slots", {}))
        decision_type = state.get("decision_type")
        found = await extract_fn(state["user_input"], decision_type, slots)

        changed = False
        new_type = found.get("decision_type")
        if new_type in REQUIRED_SLOTS and new_type != decision_type:
            decision_type = new_type
            changed = True

        for key, value in found.get("slots", {}).items():
            if value is not None and slots.get(key) != value:
                slots[key] = value
                changed = True

        return {
            "decision_type": decision_type,
            "slots": slots,
            "changed": changed,
            "confirming": state.get("confirming", False) and not changed,
        }

    return extract


async def check_missing(state):
    decision_type = state.get("decision_type")

    if decision_type is None:
        missing = ["decision_type"]
    else:
        slots = state.get("slots", {})
        missing = [f for f in REQUIRED_SLOTS[decision_type] if f not in slots]

    return {"missing": missing}


def make_ask(ask_fn):
    async def ask(state):
        question = await ask_fn(state.get("decision_type"), state["missing"])
        return {"question": question, "ask_count": state.get("ask_count", 0) + 1}

    return ask


async def wait_for_user(state):
    reply = interrupt({"type": "ask", "question": state["question"]})
    return {"user_input": reply}


async def run_plan(decision_type, s, tool_runner):
    if decision_type == "loan_affordability":
        emi = await tool_runner("calculate_emi", {
            "principal": s["principal"],
            "annual_rate": s["annual_rate"],
            "years": s["years"],
        })
        check = await tool_runner("affordability_check", {
            "monthly_income": s["monthly_income"],
            "existing_emis": s["existing_emis"],
            "new_emi": emi["emi"],
        })
        return {"calculate_emi": emi, "affordability_check": check}

    if decision_type == "tax_regime":
        out = await tool_runner("compare_tax_regimes", {
            "gross_income": s["gross_income"],
            "deductions_old": s["deductions_old"],
        })
        return {"compare_tax_regimes": out}

    if decision_type == "prepay_vs_invest":
        keys = ["principal", "loan_rate", "years", "extra_monthly", "expected_return"]
        out = await tool_runner("prepay_vs_invest", {k: s[k] for k in keys})
        return {"prepay_vs_invest": out}

    raise ValueError(f"unknown decision type {decision_type}")


def make_calc(tool_runner):
    async def run_calcs(state):
        try:
            results = await run_plan(state["decision_type"], full_slots(state), tool_runner)
        except Exception as exc:
            return {
                "status": "error",
                "explanation": f"I could not run that calculation: {exc}",
            }

        return {"results": results, "ask_count": 0, "status": "running"}

    return run_calcs


def make_explain(explain_fn):
    async def explain(state):
        text = await explain_fn(state["decision_type"], full_slots(state), state["results"])
        return {"explanation": text}

    return explain


async def confirm(state):
    reply = interrupt({
        "type": "confirm",
        "explanation": state["explanation"],
        "results": state["results"],
    })
    return {"user_input": reply, "confirming": True}


async def finish(state):
    return {"status": "done"}


async def give_up(state):
    return {
        "status": "gave_up",
        "explanation": "I could not collect enough details to run the numbers.",
    }


def route_after_extract(state):
    if state.get("confirming"):
        return "finish"
    return "check"


def route_after_check(max_asks):
    def route(state):
        if not state["missing"]:
            return "calc"
        if state.get("ask_count", 0) >= max_asks:
            return "give_up"
        return "ask"

    return route


def route_after_calc(state):
    if state.get("status") == "error":
        return "stop"
    return "explain"