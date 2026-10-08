from app.finance import invest, loan, tax


def calculate_emi(principal: float, annual_rate: float, years: float) -> dict:
    """Monthly EMI for a loan. annual_rate is a percent, e.g. 8.5."""
    return {"emi": round(loan.calculate_emi(principal, annual_rate, years), 2)}


def amortization_summary(principal: float, annual_rate: float, years: float) -> dict:
    """EMI, total interest and year-by-year balance for a loan."""
    return loan.amortization_summary(principal, annual_rate, years)


def affordability_check(monthly_income: float, existing_emis: float, new_emi: float) -> dict:
    """Share of monthly income going to EMIs and a comfortable/stretched/risky verdict."""
    return loan.affordability_check(monthly_income, existing_emis, new_emi)


def compare_tax_regimes(gross_income: float, deductions_old: float = 0.0, fy: str = tax.DEFAULT_FY) -> dict:
    """Old vs new income tax regime for a salaried person (annual figures, INR)."""
    return tax.compare_tax_regimes(gross_income, deductions_old, fy)


def prepay_vs_invest(principal: float, loan_rate: float, years: float, extra_monthly: float, expected_return: float) -> dict:
    """Compare prepaying a loan with investing the same extra money every month."""
    return invest.prepay_vs_invest(principal, loan_rate, years, extra_monthly, expected_return)


TOOL_FUNCS = {
    fn.__name__: fn
    for fn in (
        calculate_emi,
        amortization_summary,
        affordability_check,
        compare_tax_regimes,
        prepay_vs_invest,
    )
}