"""Tests for the pure finance functions (no LLM, no MCP).

These tests are the SPEC for app/finance/*. Write the code to make them pass.

Contracts
---------
app.finance.loan
    calculate_emi(principal, annual_rate, years) -> float
        annual_rate is a percent (8.5 means 8.5%). Raises ValueError on
        principal <= 0, annual_rate < 0, years <= 0.
    amortization_summary(principal, annual_rate, years) -> dict
        keys: emi, total_payment, total_interest, yearly
        yearly: list of {year, interest_paid, principal_paid, closing_balance}
    affordability_check(monthly_income, existing_emis, new_emi) -> dict
        keys: ratio, verdict. ratio = (existing_emis + new_emi) / monthly_income
        verdict: "comfortable" (<= 0.40), "stretched" (<= 0.50), else "risky"

app.finance.tax
    compare_tax_regimes(gross_income, deductions_old=0.0, fy="2025-26") -> dict
        keys: old, new (each {taxable_income, tax}), better_regime, savings
        Salaried individual; standard deduction applied automatically.
        Slabs come from tax_slabs.yaml. Raises ValueError on unknown fy.

app.finance.invest
    prepay_vs_invest(principal, loan_rate, years, extra_monthly,
                     expected_return) -> dict
        Same monthly cash outflow in both options:
          prepay: pay EMI + extra; once the loan is gone, invest the whole
                  outflow until the original tenure ends.
          invest: pay EMI; invest `extra_monthly` every month for the tenure.
        Monthly compounding at expected_return / 12.
        keys: prepay_final_wealth, invest_final_wealth, difference (abs),
              better_option ("prepay" | "invest"), months_saved
"""

import pytest

from app.finance import invest, loan, tax



class TestCalculateEmi:
    def test_known_value_home_loan(self):
        # 40 lakh at 8.5% for 20 years
        assert loan.calculate_emi(4_000_000, 8.5, 20) == pytest.approx(34712.93, abs=0.01)

    def test_zero_interest_is_simple_division(self):
        assert loan.calculate_emi(1_000_000, 0, 10) == pytest.approx(8333.33, abs=0.01)

    def test_higher_rate_means_higher_emi(self):
        assert loan.calculate_emi(1_000_000, 10, 10) > loan.calculate_emi(1_000_000, 8, 10)

    def test_longer_tenure_means_lower_emi(self):
        assert loan.calculate_emi(1_000_000, 9, 20) < loan.calculate_emi(1_000_000, 9, 10)

    @pytest.mark.parametrize(
        "principal, rate, years",
        [(0, 8, 10), (-5, 8, 10), (1_000_000, -1, 10), (1_000_000, 8, 0), (1_000_000, 8, -3)],
    )
    def test_invalid_inputs_raise(self, principal, rate, years):
        with pytest.raises(ValueError):
            loan.calculate_emi(principal, rate, years)



class TestAmortizationSummary:
    def test_one_year_loan_known_values(self):
        s = loan.amortization_summary(1_200_000, 12, 1)
        assert s["emi"] == pytest.approx(106618.55, abs=0.01)
        assert s["total_payment"] == pytest.approx(1_279_422.56, abs=0.05)
        assert s["total_interest"] == pytest.approx(79_422.56, abs=0.05)
        assert len(s["yearly"]) == 1
        assert s["yearly"][0]["closing_balance"] == pytest.approx(0, abs=0.01)

    def test_long_loan_structure(self):
        s = loan.amortization_summary(4_000_000, 8.5, 20)
        yearly = s["yearly"]
        assert len(yearly) == 20
        assert [row["year"] for row in yearly] == list(range(1, 21))
        assert s["total_interest"] == pytest.approx(4_331_103.04, abs=1.0)

        balances = [row["closing_balance"] for row in yearly]
        assert all(a > b for a, b in zip(balances, balances[1:]))  # strictly falling
        assert balances[-1] == pytest.approx(0, abs=0.5)

    def test_principal_paid_adds_up_to_principal(self):
        s = loan.amortization_summary(4_000_000, 8.5, 20)
        assert sum(r["principal_paid"] for r in s["yearly"]) == pytest.approx(4_000_000, abs=1.0)

    def test_interest_share_falls_over_time(self):
        yearly = loan.amortization_summary(4_000_000, 8.5, 20)["yearly"]
        assert yearly[0]["interest_paid"] > yearly[-1]["interest_paid"]



class TestAffordabilityCheck:
    def test_comfortable(self):
        r = loan.affordability_check(100_000, 0, 34_713)
        assert r["ratio"] == pytest.approx(0.34713)
        assert r["verdict"] == "comfortable"

    def test_stretched(self):
        assert loan.affordability_check(100_000, 20_000, 25_000)["verdict"] == "stretched"

    def test_risky(self):
        assert loan.affordability_check(100_000, 30_000, 30_000)["verdict"] == "risky"

    def test_boundaries_are_inclusive(self):
        assert loan.affordability_check(100_000, 0, 40_000)["verdict"] == "comfortable"
        assert loan.affordability_check(100_000, 0, 50_000)["verdict"] == "stretched"

    @pytest.mark.parametrize("income", [0, -1])
    def test_non_positive_income_raises(self, income):
        with pytest.raises(ValueError):
            loan.affordability_check(income, 0, 10_000)



class TestCompareTaxRegimes:
    def test_result_shape(self):
        r = tax.compare_tax_regimes(1_800_000, deductions_old=150_000)
        assert set(r) >= {"old", "new", "better_regime", "savings"}
        for regime in ("old", "new"):
            assert set(r[regime]) >= {"taxable_income", "tax"}
        assert r["better_regime"] in ("old", "new")

    def test_low_income_pays_no_tax_in_either_regime(self):
        r = tax.compare_tax_regimes(400_000)
        assert r["old"]["tax"] == 0
        assert r["new"]["tax"] == 0
        assert r["savings"] == 0

    def test_high_income_pays_tax_in_both_regimes(self):
        r = tax.compare_tax_regimes(3_000_000)
        assert r["old"]["tax"] > 0
        assert r["new"]["tax"] > 0

    def test_better_regime_is_the_cheaper_one(self):
        r = tax.compare_tax_regimes(3_000_000, deductions_old=200_000)
        other = "old" if r["better_regime"] == "new" else "new"
        assert r[r["better_regime"]]["tax"] <= r[other]["tax"]
        assert r["savings"] == pytest.approx(abs(r["old"]["tax"] - r["new"]["tax"]))

    def test_new_regime_tax_never_falls_as_income_rises(self):
        incomes = [500_000, 800_000, 1_200_000, 1_800_000, 2_500_000, 4_000_000, 10_000_000]
        taxes = [tax.compare_tax_regimes(i)["new"]["tax"] for i in incomes]
        assert taxes == sorted(taxes)

    def test_more_deductions_never_raise_old_tax_and_do_not_touch_new(self):
        low = tax.compare_tax_regimes(2_000_000, deductions_old=0)
        high = tax.compare_tax_regimes(2_000_000, deductions_old=250_000)
        assert high["old"]["tax"] <= low["old"]["tax"]
        assert high["new"]["tax"] == low["new"]["tax"]

    def test_negative_income_raises(self):
        with pytest.raises(ValueError):
            tax.compare_tax_regimes(-1)

    def test_unknown_financial_year_raises(self):
        with pytest.raises(ValueError):
            tax.compare_tax_regimes(1_000_000, fy="1999-00")



class TestPrepayVsInvest:
    ARGS = dict(principal=4_000_000, loan_rate=8.5, years=20, extra_monthly=10_000)

    def test_zero_return_prepay_wins(self):
        r = invest.prepay_vs_invest(**self.ARGS, expected_return=0)
        assert r["better_option"] == "prepay"
        assert r["prepay_final_wealth"] == pytest.approx(4_369_555, rel=1e-3)
        assert r["invest_final_wealth"] == pytest.approx(2_400_000, rel=1e-6)

    def test_high_return_invest_wins(self):
        r = invest.prepay_vs_invest(**self.ARGS, expected_return=15)
        assert r["better_option"] == "invest"
        assert r["prepay_final_wealth"] == pytest.approx(8_466_595, rel=1e-3)
        assert r["invest_final_wealth"] == pytest.approx(14_972_395, rel=1e-3)
        assert r["difference"] == pytest.approx(
            r["invest_final_wealth"] - r["prepay_final_wealth"], rel=1e-9
        )

    def test_break_even_when_return_equals_loan_rate(self):
        r = invest.prepay_vs_invest(**self.ARGS, expected_return=8.5)
        assert r["prepay_final_wealth"] == pytest.approx(r["invest_final_wealth"], rel=1e-6)

    def test_months_saved(self):
        r = invest.prepay_vs_invest(**self.ARGS, expected_return=10)
        assert r["months_saved"] == 97

    def test_no_extra_money_means_no_difference(self):
        r = invest.prepay_vs_invest(
            principal=4_000_000, loan_rate=8.5, years=20, extra_monthly=0, expected_return=12
        )
        assert r["months_saved"] == 0
        assert r["difference"] == pytest.approx(0, abs=1.0)

    @pytest.mark.parametrize(
        "kwargs",
        [
            dict(principal=0, loan_rate=8, years=10, extra_monthly=1000, expected_return=10),
            dict(principal=1_000_000, loan_rate=-1, years=10, extra_monthly=1000, expected_return=10),
            dict(principal=1_000_000, loan_rate=8, years=0, extra_monthly=1000, expected_return=10),
            dict(principal=1_000_000, loan_rate=8, years=10, extra_monthly=-1, expected_return=10),
            dict(principal=1_000_000, loan_rate=8, years=10, extra_monthly=1000, expected_return=-5),
        ],
    )
    def test_invalid_inputs_raise(self, kwargs):
        with pytest.raises(ValueError):
            invest.prepay_vs_invest(**kwargs)