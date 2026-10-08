import json

FIELD_HELP = {
    "decision_type": "what they want help deciding (can they afford a loan, old vs new tax regime, or prepay a loan vs invest)",
    "principal": "the loan amount (for example 25 lakh)",
    "annual_rate": "the yearly interest rate on the loan (for example 9%)",
    "years": "how many years the loan runs for (for example 15)",
    "monthly_income": "their monthly in-hand income",
    "gross_income": "their yearly gross salary (for example 12 LPA)",
    "loan_rate": "the yearly interest rate on their loan (for example 9%)",
    "extra_monthly": "how much extra money they can put in every month",
    "expected_return": "the yearly return they expect from investing (for example 12%)",
}

TOPICS = {
    None: "not decided yet, so first find out what they want help with (loan affordability, old vs new tax regime, or prepaying a loan vs investing)",
    "loan_affordability": "whether they can afford a loan",
    "tax_regime": "choosing between the old and the new income tax regime",
    "prepay_vs_invest": "whether to prepay a loan or invest the extra money",
}

EXPLAIN_SYSTEM = """You explain the result of a money decision to an ordinary person in 4 to 6 short sentences.

Rules:
- Use only the numbers that appear in the data you are given. Never calculate, estimate or add a number of your own.
- Write amounts in rupees with the ₹ sign and commas, rounded to whole rupees.
- Say what the numbers mean in plain words and give a clear take, for example whether the EMI looks comfortable.
- No headings, no bullet points, no disclaimers."""


def extract_system(decision_type, slots):
    known = json.dumps(slots) if slots else "nothing yet"
    current = decision_type or "not known yet"

    return f"""You read a message about a money decision from a user in India and fill in a form.

Rules:
- Only fill a field if the user clearly said it. Otherwise leave it null. Never guess.
- Fill EVERY field the message gives you, not just the first one.
- Money is in rupees as a plain number. 1 lakh (also written L, lac, lakhs) = 100000. 1 crore (Cr) = 10000000. k = 1000. "12 LPA" means 1200000 per year.
- monthly_income, existing_emis and extra_monthly are per month. gross_income and deductions_old are per year.
- If the user gives a yearly salary for a loan or prepay question, divide it by 12 for monthly_income.
- interest_rate is the loan interest rate as a percentage per year, so 8.5% is 8.5.
- years is the length of the loan in years, so 18 months is 1.5.
- decision_type is loan_affordability (can I afford a loan, EMI), tax_regime (old vs new tax regime) or prepay_vs_invest (prepay a loan or invest extra money). Leave it null if this message does not change it.
- Text like (you asked: ...) at the start shows the question the user is answering. Use it to decide which field a short answer such as "8.5" or "20" belongs to.

Examples:
Message: I earn 12 LPA. Can I afford a 40 lakh home loan?
Fill: decision_type=loan_affordability, monthly_income=100000, principal=4000000
Message: (you asked: the interest rate and the loan length) 8.5% for 10 year
Fill: interest_rate=8.5, years=10
Message: (you asked: the loan amount) 40L
Fill: principal=4000000
Message: Old vs new regime, I make 18 LPA and invest 1.5 lakh under 80C
Fill: decision_type=tax_regime, gross_income=1800000, deductions_old=150000

Current decision: {current}
Details already known: {known}
Return only details that are new or changed in this message."""


def ask_system(decision_type):
    topic = TOPICS.get(decision_type, TOPICS[None])

    return f"""You are Tallyman, a friendly assistant that helps people in India with money decisions. The topic right now: {topic}.

You are in the middle of a conversation, so do not greet the user and do not say hi.
Ask ONE short question, one or two sentences, that collects the missing details you are given. Use simple words and give a quick example for each detail. Do not mention field names, do not give advice and do not make up any numbers."""
