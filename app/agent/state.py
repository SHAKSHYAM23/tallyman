from typing import TypedDict

REQUIRED_SLOTS = {
    "loan_affordability": ["principal", "annual_rate", "years", "monthly_income"],
    "tax_regime": ["gross_income"],
    "prepay_vs_invest": ["principal", "loan_rate", "years", "extra_monthly", "expected_return"],
}

DEFAULTS = {
    "loan_affordability": {"existing_emis": 0},
    "tax_regime": {"deductions_old": 0},
}


class AgentState(TypedDict, total=False):
    user_input: str
    decision_type: str | None
    slots: dict
    missing: list
    question: str
    ask_count: int
    changed: bool
    confirming: bool
    results: dict
    explanation: str
    status: str