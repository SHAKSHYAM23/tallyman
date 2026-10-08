import json
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

from app.agent.grounding import is_grounded, plain_summary
from app.agent.prompts import EXPLAIN_SYSTEM, FIELD_HELP, ask_system, extract_system
from app.core import config

_llm = None


class ExtractedDetails(BaseModel):
    decision_type: Literal["loan_affordability", "tax_regime", "prepay_vs_invest"] | None = None
    principal: float | None = Field(None, description="loan amount in rupees")
    interest_rate: float | None = Field(None, description="loan interest rate, percent per year")
    years: float | None = Field(None, description="loan length in years")
    monthly_income: float | None = Field(None, description="monthly in-hand income in rupees")
    existing_emis: float | None = Field(None, description="EMIs already being paid each month, in rupees")
    gross_income: float | None = Field(None, description="yearly gross salary in rupees")
    deductions_old: float | None = Field(None, description="yearly tax deductions in rupees, old regime")
    extra_monthly: float | None = Field(None, description="extra money available each month, in rupees")
    expected_return: float | None = Field(None, description="expected yearly investment return, percent")


def get_llm():
    global _llm
    if _llm is None:
        if not config.GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is not set")
        options = {}
        if config.GROQ_REASONING_EFFORT:
            options["reasoning_effort"] = config.GROQ_REASONING_EFFORT
        _llm = ChatGroq(
            model=config.GROQ_MODEL,
            api_key=config.GROQ_API_KEY,
            temperature=0,
            max_retries=2,
            request_timeout=30,
            **options,
        )
    return _llm


def rate_slots(rate, decision_type):
    targets = {
        "loan_affordability": ["annual_rate"],
        "prepay_vs_invest": ["loan_rate"],
    }.get(decision_type, ["annual_rate", "loan_rate"])
    return {name: rate for name in targets}


async def extract_fn(user_text, decision_type, slots):
    structured = get_llm().with_structured_output(ExtractedDetails)
    messages = [
        SystemMessage(content=extract_system(decision_type, slots)),
        HumanMessage(content=user_text),
    ]

    result = None
    error = None
    for _ in range(2):
        try:
            result = await structured.ainvoke(messages)
            error = None
            break
        except Exception as exc:
            error = exc

    if error is not None:
        raise error
    if result is None:
        return {"decision_type": None, "slots": {}}

    data = result.model_dump()
    new_type = data.pop("decision_type")
    rate = data.pop("interest_rate")

    found = {k: v for k, v in data.items() if v is not None}
    if rate is not None:
        found.update(rate_slots(rate, new_type or decision_type))

    if config.DEBUG_LLM:
        print(f"[extract] {user_text!r} -> type={new_type} slots={found}", flush=True)

    return {"decision_type": new_type, "slots": found}


async def ask_fn(decision_type, missing):
    wanted = "; ".join(FIELD_HELP[name] for name in missing)
    reply = await get_llm().ainvoke([
        SystemMessage(content=ask_system(decision_type)),
        HumanMessage(content=f"Missing details: {wanted}"),
    ])
    return reply.content.strip()


async def explain_fn(decision_type, slots, results):
    payload = json.dumps(
        {"decision": decision_type, "user_inputs": slots, "results": results},
        indent=2,
    )
    messages = [SystemMessage(content=EXPLAIN_SYSTEM), HumanMessage(content=payload)]

    for _ in range(2):
        reply = await get_llm().ainvoke(messages)
        text = reply.content.strip()
        if text and is_grounded(text, slots, results):
            return text

    return plain_summary(decision_type, slots, results)
