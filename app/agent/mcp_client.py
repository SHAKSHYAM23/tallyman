import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[2]


@asynccontextmanager
async def open_tool_runner():
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.mcp_server.server"],
        cwd=ROOT,
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            async def run(tool_name, args):
                result = await session.call_tool(tool_name, args)
                text = result.content[0].text
                if result.isError:
                    raise RuntimeError(text.split(": ", 1)[-1])
                return json.loads(text)

            yield run