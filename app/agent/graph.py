from langgraph.graph import END, START, StateGraph

from app.agent import nodes
from app.agent.state import AgentState


def build_graph(*, extract_fn, ask_fn, explain_fn, tool_runner, checkpointer=None, max_asks=3):
    builder = StateGraph(AgentState)

    builder.add_node("extract", nodes.make_extract(extract_fn))
    builder.add_node("check_missing", nodes.check_missing)
    builder.add_node("ask", nodes.make_ask(ask_fn))
    builder.add_node("wait_for_user", nodes.wait_for_user)
    builder.add_node("run_calcs", nodes.make_calc(tool_runner))
    builder.add_node("explain", nodes.make_explain(explain_fn))
    builder.add_node("confirm", nodes.confirm)
    builder.add_node("finish", nodes.finish)
    builder.add_node("give_up", nodes.give_up)

    builder.add_edge(START, "extract")
    builder.add_conditional_edges(
        "extract", nodes.route_after_extract,
        {"finish": "finish", "check": "check_missing"},
    )
    builder.add_conditional_edges(
        "check_missing", nodes.route_after_check(max_asks),
        {"ask": "ask", "calc": "run_calcs", "give_up": "give_up"},
    )
    builder.add_edge("ask", "wait_for_user")
    builder.add_edge("wait_for_user", "extract")
    builder.add_conditional_edges(
        "run_calcs", nodes.route_after_calc,
        {"explain": "explain", "stop": END},
    )
    builder.add_edge("explain", "confirm")
    builder.add_edge("confirm", "extract")
    builder.add_edge("finish", END)
    builder.add_edge("give_up", END)

    return builder.compile(checkpointer=checkpointer)