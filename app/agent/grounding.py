import re

NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def inr(amount):
    n = int(round(amount))
    digits = str(abs(n))

    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups + [tail])

    return ("-" if n < 0 else "") + "₹" + digits


def numbers_in(text):
    found = []
    for raw in NUMBER.findall(text):
        try:
            found.append(float(raw.replace(",", "")))
        except ValueError:
            pass
    return found


def collect(value, out):
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        out.append(float(value))
    elif isinstance(value, str):
        out.extend(numbers_in(value))
    elif isinstance(value, dict):
        for item in value.values():
            collect(item, out)
    elif isinstance(value, list):
        for item in value:
            collect(item, out)


def allowed_numbers(slots, results):
    base = []
    collect(slots, base)
    collect(results, base)

    allowed = set(base)
    for v in base:
        allowed.add(v * 12)
        allowed.add(v / 12)
        if abs(v) >= 100000:
            allowed.add(v / 100000)
        if abs(v) >= 10000000:
            allowed.add(v / 10000000)
        if abs(v) <= 1.5:
            allowed.add(v * 100)
    return allowed


def is_grounded(text, slots, results):
    allowed = allowed_numbers(slots, results)

    for n in numbers_in(text):
        if n <= 10 and n == int(n):
            continue
        if not any(abs(n - a) <= max(0.5, 0.006 * abs(a)) for a in allowed):
            return False

    return True


def plain_summary(decision_type, slots, results):
    if decision_type == "loan_affordability":
        emi = results["calculate_emi"]["emi"]
        check = results["affordability_check"]
        return (
            f"A loan of {inr(slots['principal'])} at {slots['annual_rate']:g}% for {slots['years']:g} years "
            f"has an EMI of about {inr(emi)} a month. That takes {check['ratio'] * 100:.1f}% "
            f"of your monthly income, which looks {check['verdict']}."
        )

    if decision_type == "tax_regime":
        r = results["compare_tax_regimes"]
        text = (
            f"Under the old regime your tax would be about {inr(r['old']['tax'])} and under the "
            f"new regime about {inr(r['new']['tax'])}."
        )
        if r["savings"] == 0:
            return text + " Both regimes cost you the same."
        return text + f" The {r['better_regime']} regime is cheaper by about {inr(r['savings'])}."

    r = results["prepay_vs_invest"]
    winner = "Prepaying" if r["better_option"] == "prepay" else "Investing"
    return (
        f"After {slots['years']:g} years, prepaying would leave you with about {inr(r['prepay_final_wealth'])} "
        f"and investing the same money would leave you with about {inr(r['invest_final_wealth'])}. "
        f"{winner} comes out ahead by about {inr(r['difference'])}. "
        f"Prepaying would also close the loan {r['months_saved']} months early."
    )
