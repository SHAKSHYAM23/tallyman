from pathlib import Path

import yaml

DEFAULT_FY = "2026-27"
SLAB_FILE = Path(__file__).with_name("tax_slabs.yaml")

_slabs = None


def load_slabs():
    global _slabs
    if _slabs is None:
        with open(SLAB_FILE, encoding="utf-8") as f:
            _slabs = yaml.safe_load(f)
    return _slabs


def slab_tax(income, slabs):
    tax = 0.0
    lower = 0

    for limit, rate in slabs:
        if income <= lower:
            break
        top = income if limit is None else min(income, limit)
        tax += (top - lower) * rate
        if limit is None:
            break
        lower = limit

    return tax


def regime_tax(taxable, rules, cess):
    tax = slab_tax(taxable, rules["slabs"])
    limit = rules["rebate_limit"]

    if taxable <= limit:
        tax = max(0, tax - rules["rebate_max"])
    elif rules["marginal_relief"]:
        tax = min(tax, taxable - limit)

    return round(tax * (1 + cess), 2)


def compare_tax_regimes(gross_income, deductions_old=0.0, fy=DEFAULT_FY):
    if gross_income < 0:
        raise ValueError("gross_income cannot be negative")
    if deductions_old < 0:
        raise ValueError("deductions_old cannot be negative")

    data = load_slabs().get(fy)
    if data is None:
        raise ValueError(f"no tax data for financial year {fy}")

    cess = data["cess"]
    new_rules = data["new"]
    old_rules = data["old"]

    new_taxable = max(0, gross_income - new_rules["standard_deduction"])
    old_taxable = max(0, gross_income - old_rules["standard_deduction"] - deductions_old)

    old_tax = regime_tax(old_taxable, old_rules, cess)
    new_tax = regime_tax(new_taxable, new_rules, cess)

    return {
        "fy": fy,
        "old": {"taxable_income": old_taxable, "tax": old_tax},
        "new": {"taxable_income": new_taxable, "tax": new_tax},
        "better_regime": "old" if old_tax < new_tax else "new",
        "savings": round(abs(old_tax - new_tax), 2),
    }