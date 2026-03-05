import asyncio
import logging
logging.basicConfig(level=logging.WARNING)
from src.agents.researcher import research_node
state = {
    "messages": [],
    "factor_proposal": "",
    "factor_hypothesis": None,
    "code_snippet": "",
    "backtest_result": "",
    "backtest_metrics": None,
    "error_message": "",
    "current_iteration": 0,
    "max_iterations": 3,
    "island_name": "momentum",
}
res = research_node(state)
content = res["messages"][-1].content
with open("llm_out.txt", "w") as f:
    f.write(content)
