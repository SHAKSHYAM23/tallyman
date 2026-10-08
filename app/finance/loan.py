EMI_COMFORTABLE = 0.40
EMI_STRETCHED = 0.50


def check_loan_inputs(principal, annual_rate, years):
    if principal <= 0:
        raise ValueError("principal must be positive")
    if annual_rate < 0:
        raise ValueError("annual_rate cannot be negative")
    if years <= 0:
        raise ValueError("years must be positive")


def month_count(years):
    months = round(years * 12)
    if months < 1:
        raise ValueError("years is too small, need at least one month")
    return months


def calculate_emi(principal, annual_rate, years):
    check_loan_inputs(principal, annual_rate, years)
    n = month_count(years)
    r = annual_rate / 1200

    if r == 0:
        return principal / n

    growth = (1 + r) ** n
    return principal * r * growth / (growth - 1)



def amortization_summary(principal, annual_rate, years):
    emi = calculate_emi(principal, annual_rate, years)
    months = month_count(years)
    r = annual_rate / 1200

    balance = principal
    yearly = []
    interest_so_far = 0.0
    principal_so_far = 0.0

    for m in range(1, months + 1):
        interest = balance * r
        repaid = emi - interest
        balance -= repaid
        interest_so_far += interest
        principal_so_far += repaid

        if m % 12 == 0 or m == months:
            yearly.append({
                "year": len(yearly) + 1,
                "interest_paid": round(interest_so_far, 2),
                "principal_paid": round(principal_so_far, 2),
                "closing_balance": round(max(balance, 0), 2),
            })
            interest_so_far = 0.0
            principal_so_far = 0.0

    total_payment = emi * months
    return {
        "emi": round(emi, 2),
        "total_payment": round(total_payment, 2),
        "total_interest": round(total_payment - principal, 2),
        "yearly": yearly,
    }


def affordability_check(monthly_income, existing_emis, new_emi):
    if monthly_income <= 0:
        raise ValueError("monthly_income must be positive")
    if existing_emis < 0:
        raise ValueError("existing_emis cannot be negative")
    if new_emi < 0:
        raise ValueError("new_emi cannot be negative")

    ratio = (existing_emis + new_emi) / monthly_income

    if ratio <= EMI_COMFORTABLE:
        verdict = "comfortable"
    elif ratio <= EMI_STRETCHED:
        verdict = "stretched"
    else:
        verdict = "risky"

    return {"ratio": round(ratio, 5), "verdict": verdict}