import pytest

from app.agent.grounding import inr, is_grounded, numbers_in, plain_summary
from app.finance.tools import TOOL_FUNCS


@pytest.mark.parametrize(
    "amount, expected",
    [
        (0, "₹0"),
        (999, "₹999"),
        (1000, "₹1,000"),
        (100000, "₹1,00,000"),
        (34712.93, "₹34,713"),
        (4000000, "₹40,00,000"),
        (12345678, "₹1,23,45,678"),
        (-2500, "-₹2,500"),
    ],
)
def test_inr_uses_indian_grouping(amount, expected):
    assert inr(amount) == expected


def test_numbers_in_handles_commas_decimals_and_symbols():
    assert numbers_in("EMI is ₹34,713 which is 34.7% of income") == [34713.0, 34.7]


SLOTS = {"principal": 4_000_000, "annual_rate": 8.5, "years": 20, "monthly_income": 100_000, "existing_emis": 0}
RESULTS = {
    "calculate_emi": {"emi": 34712.93},
    "affordability_check": {"ratio": 0.34713, "verdict": "comfortable"},
}


def test_accepts_numbers_that_come_from_the_tools():
    text = "A ₹40,00,000 loan at 8.5% for 20 years costs about ₹34,713 a month, or 34.7% of your income."
    assert is_grounded(text, SLOTS, RESULTS)


def test_accepts_lakh_and_percent_forms_of_real_numbers():
    assert is_grounded("That is a ₹40 lakh loan and your EMI takes 35% of income.", SLOTS, RESULTS)


def test_rejects_a_number_the_tools_never_produced():
    assert not is_grounded("Your EMI is about ₹41,000 a month.", SLOTS, RESULTS)
    assert not is_grounded("You will pay ₹90,00,000 in total interest.", SLOTS, RESULTS)


def test_ignores_tiny_whole_numbers():
    assert is_grounded("Here are 3 things to know. First, your EMI is ₹34,713.", SLOTS, RESULTS)


def test_plain_summary_is_grounded_for_every_decision_type():
    loan = {
        "calculate_emi": TOOL_FUNCS["calculate_emi"](4_000_000, 8.5, 20),
        "affordability_check": TOOL_FUNCS["affordability_check"](100_000, 0, 34_713),
    }
    tax = {"compare_tax_regimes": TOOL_FUNCS["compare_tax_regimes"](1_800_000, 150_000)}
    invest = {"prepay_vs_invest": TOOL_FUNCS["prepay_vs_invest"](4_000_000, 8.5, 20, 10_000, 12)}

    cases = [
        ("loan_affordability", SLOTS, loan),
        ("tax_regime", {"gross_income": 1_800_000, "deductions_old": 150_000}, tax),
        ("prepay_vs_invest", {"principal": 4_000_000, "loan_rate": 8.5, "years": 20,
                              "extra_monthly": 10_000, "expected_return": 12}, invest),
    ]
    for decision_type, slots, results in cases:
        text = plain_summary(decision_type, slots, results)
        assert is_grounded(text, slots, results), text
