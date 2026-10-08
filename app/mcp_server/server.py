from mcp.server.fastmcp import FastMCP

from app.finance.tools import TOOL_FUNCS

mcp = FastMCP("tallyman-finance")

for tool_fn in TOOL_FUNCS.values():
    mcp.tool()(tool_fn)


if __name__ == "__main__":
    mcp.run(transport="stdio")