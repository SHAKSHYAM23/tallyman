from app.finance.loan import calculate_emi, month_count


def prepay_vs_invest(principal, loan_rate, years, extra_monthly, expected_return):
    if extra_monthly < 0:
        raise ValueError("extra_monthly cannot be negative")
    if expected_return < 0:
        raise ValueError("expected_return cannot be negative")

    emi = calculate_emi(principal, loan_rate, years)
    n = month_count(years)
    r = loan_rate / 1200
    g = expected_return / 1200
    outflow = emi + extra_monthly


    balance = principal
    prepay_wealth = 0.0
    payoff_month = n

    for month in range(1, n + 1):
        if balance > 0:
            interest = balance * r
            payment = min(balance + interest, outflow)
            balance = balance + interest - payment
            if balance < 0.01:
                balance = 0
                payoff_month = min(payoff_month, month)
            spare = outflow - payment
        else:
            spare = outflow
        prepay_wealth = prepay_wealth * (1 + g) + spare

    invest_wealth = 0.0
    for month in range(n):
        invest_wealth = invest_wealth * (1 + g) + extra_monthly

    prepay_wealth = round(prepay_wealth, 2)
    invest_wealth = round(invest_wealth, 2)

    return {
        "prepay_final_wealth": prepay_wealth,
        "invest_final_wealth": invest_wealth,
        "difference": round(abs(prepay_wealth - invest_wealth), 2),
        "better_option": "prepay" if prepay_wealth >= invest_wealth else "invest",
        "months_saved": n - payoff_month,
    }