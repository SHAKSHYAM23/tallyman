import pytest

from app.agent.mcp_client import open_tool_runner


async def test_runner_returns_parsed_dicts():
    async with open_tool_runner() as run:
        out = await run("calculate_emi", {"principal": 4_000_000, "annual_rate": 8.5, "years": 20})
    assert out["emi"] == pytest.approx(34712.93, abs=0.01)


async def test_runner_raises_a_clean_error_for_bad_input():
    async with open_tool_runner() as run:
        with pytest.raises(RuntimeError, match="principal must be positive"):
            await run("calculate_emi", {"principal": -1, "annual_rate": 8.5, "years": 20})

        out = await run("calculate_emi", {"principal": 1_000_000, "annual_rate": 8, "years": 10})
        assert out["emi"] > 0
