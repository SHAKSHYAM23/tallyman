from app.agent import llm


class FakeStructured:
    def __init__(self, details):
        self.details = details

    async def ainvoke(self, messages):
        return self.details


class FakeLLM:
    def __init__(self, details):
        self.details = details

    def with_structured_output(self, schema):
        return FakeStructured(self.details)


def fake_model(monkeypatch, details):
    monkeypatch.setattr(llm, "get_llm", lambda: FakeLLM(details))


async def test_rate_goes_to_annual_rate_for_loan_affordability(monkeypatch):
    fake_model(monkeypatch, llm.ExtractedDetails(interest_rate=8.5, years=10))
    out = await llm.extract_fn("8.5% for 10 year", "loan_affordability", {})
    assert out["slots"] == {"years": 10, "annual_rate": 8.5}
    assert out["decision_type"] is None


async def test_rate_goes_to_loan_rate_for_prepay_vs_invest(monkeypatch):
    fake_model(monkeypatch, llm.ExtractedDetails(decision_type="prepay_vs_invest", interest_rate=9))
    out = await llm.extract_fn("my loan is at 9%", None, {})
    assert out["slots"] == {"loan_rate": 9}
    assert out["decision_type"] == "prepay_vs_invest"


async def test_rate_fills_both_when_the_decision_is_not_known_yet(monkeypatch):
    fake_model(monkeypatch, llm.ExtractedDetails(interest_rate=9))
    out = await llm.extract_fn("9%", None, {})
    assert out["slots"] == {"annual_rate": 9, "loan_rate": 9}


async def test_empty_fields_are_dropped_and_a_missing_result_is_safe(monkeypatch):
    fake_model(monkeypatch, llm.ExtractedDetails(principal=4_000_000, monthly_income=100_000))
    out = await llm.extract_fn("x", "loan_affordability", {})
    assert out["slots"] == {"principal": 4_000_000, "monthly_income": 100_000}

    fake_model(monkeypatch, None)
    assert await llm.extract_fn("x", None, {}) == {"decision_type": None, "slots": {}}
