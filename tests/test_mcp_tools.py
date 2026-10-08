"""Tests for the MCP server, run end to end over stdio.

Each test spawns `python -m app.mcp_server.server` as a subprocess and talks
to it with a real MCP client, which is exactly how the agent (and Streamlit
Cloud) will use it. That also proves the stdio path works before you deploy.

Contracts
---------
app/finance/tools.py
    TOOL_FUNCS: dict[str, Callable[..., dict]]
    One entry per tool, every function returns a dict:
        calculate_emi(principal, annual_rate, years)            -> {"emi": float}
        amortization_summary(principal, annual_rate, years)     -> same dict as loan.amortization_summary
        affordability_check(monthly_income, existing_emis, new_emi) -> {"ratio", "verdict"}
        compare_tax_regimes(gross_income, deductions_old=0.0, fy="2025-26") -> same dict as tax.compare_tax_regimes
        prepay_vs_invest(principal, loan_rate, years, extra_monthly, expected_return)
                                                                -> same dict as invest.prepay_vs_invest

app/mcp_server/server.py
    Registers every function in TOOL_FUNCS on a FastMCP server and runs
    over stdio when executed as a module.
    Must not print anything to stdout (stdout is the protocol channel).
    Validation errors are plain ValueErrors whose message names the bad
    parameter, e.g. "principal must be positive".
"""

import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.finance import loan

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_TOOLS = {
    "calculate_emi",
    "amortization_summary",
    "affordability_check",
    "compare_tax_regimes",
    "prepay_vs_invest",
}


@asynccontextmanager
async def mcp_session():
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.mcp_server.server"],
        cwd=ROOT,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def parse(result) -> dict:
    """Tool results arrive as JSON text (or structuredContent on newer servers)."""
    assert not result.isError, result.content[0].text
    structured = getattr(result, "structuredContent", None)
    if structured:
        # FastMCP wraps non-object returns as {"result": ...}; our tools return dicts.
        return structured["result"] if set(structured) == {"result"} else structured
    return json.loads(result.content[0].text)


async def test_server_lists_exactly_the_expected_tools():
    async with mcp_session() as session:
        listed = await session.list_tools()
    assert {t.name for t in listed.tools} == EXPECTED_TOOLS


async def test_every_tool_has_a_description_and_required_params():
    async with mcp_session() as session:
        tools = {t.name: t for t in (await session.list_tools()).tools}

  
    for name, tool in tools.items():
        assert tool.description, f"{name} needs a docstring"

    assert set(tools["calculate_emi"].inputSchema["required"]) == {
        "principal",
        "annual_rate",
        "years",
    }
    assert "monthly_income" in tools["affordability_check"].inputSchema["required"]


async def test_tools_return_the_same_numbers_as_the_pure_functions():
    async with mcp_session() as session:
        emi = parse(
            await session.call_tool(
                "calculate_emi",
                {"principal": 4_000_000, "annual_rate": 8.5, "years": 20},
            )
        )
        verdict = parse(
            await session.call_tool(
                "affordability_check",
                {"monthly_income": 100_000, "existing_emis": 0, "new_emi": 34_713},
            )
        )
        summary = parse(
            await session.call_tool(
                "amortization_summary",
                {"principal": 1_200_000, "annual_rate": 12, "years": 1},
            )
        )
        regimes = parse(
            await session.call_tool(
                "compare_tax_regimes",
                {"gross_income": 1_800_000, "deductions_old": 150_000},
            )
        )
        invest_result = parse(
            await session.call_tool(
                "prepay_vs_invest",
                {
                    "principal": 4_000_000,
                    "loan_rate": 8.5,
                    "years": 20,
                    "extra_monthly": 10_000,
                    "expected_return": 12,
                },
            )
        )

    assert emi["emi"] == pytest.approx(loan.calculate_emi(4_000_000, 8.5, 20))
    assert verdict["verdict"] == "comfortable"
    assert summary["total_interest"] == pytest.approx(79_422.56, abs=0.05)
    assert set(regimes) >= {"old", "new", "better_regime", "savings"}
    assert invest_result["better_option"] in ("prepay", "invest")


async def test_invalid_input_comes_back_as_a_tool_error_not_a_crash():
    async with mcp_session() as session:
        bad = await session.call_tool(
            "calculate_emi", {"principal": -1, "annual_rate": 8, "years": 10}
        )
        assert bad.isError
        assert "principal" in bad.content[0].text.lower()

       
        good = parse(
            await session.call_tool(
                "calculate_emi", {"principal": 1_000_000, "annual_rate": 8, "years": 10}
            )
        )
        assert good["emi"] > 0


async def test_tool_registry_and_server_stay_in_sync():
    """TOOL_FUNCS is the single source of truth; the server must expose all of it."""
    from app.finance.tools import TOOL_FUNCS

    assert set(TOOL_FUNCS) == EXPECTED_TOOLS
    async with mcp_session() as session:
        listed = {t.name for t in (await session.list_tools()).tools}
    assert listed == set(TOOL_FUNCS)