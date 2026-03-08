"""
Pixiu: Researcher Agent（MCP 增强版）
Role: 调用 AKShare MCP 工具获取实时市场数据，结合因子字典提出量化因子假设。
"""
import asyncio
import logging
import os

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

from .state import AgentState
from .schemas import FactorHypothesis
from src.skills.loader import SkillLoader

_SKILL_LOADER = SkillLoader()  # 模块级单例

def load_dotenv_if_available():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

load_dotenv_if_available()
logger = logging.getLogger(__name__)

# ── 知识库路径 ──────────────────────────────────────────────────
_BASE = os.path.dirname(__file__)
DICTIONARY_PATH = os.path.abspath(os.path.join(_BASE, "..", "..", "knowledge", "factors", "quant_factors_dictionary.md"))
SKILL_PATH = os.path.abspath(os.path.join(_BASE, "..", "..", "knowledge", "agent_skills", "researcher_alpha_generation.md"))
MCP_SERVER_PATH = os.path.abspath(os.path.join(_BASE, "..", "..", "mcp_servers", "akshare_server.py"))

# ── MCP Client（模块级单例，跨 epoch 复用）─────────────────────
_CHROMADB_SERVER_PATH = os.path.abspath(
    os.path.join(_BASE, "..", "..", "mcp_servers", "chromadb_server.py")
)

_MCP_CLIENT = MultiServerMCPClient(
    {
        "akshare": {
            "command": "python3",
            "args": [MCP_SERVER_PATH],
            "transport": "stdio",
        },
        "chromadb": {
            "command": "python3",
            "args": [_CHROMADB_SERVER_PATH],
            "transport": "stdio",
        },
    }
)

# ── LLM ────────────────────────────────────────────────────────
def _build_llm(tools):
    # 读取环境变量中的 Researcher 专属配置，或者 fallback
    model_name = os.environ.get("RESEARCHER_MODEL", "deepseek-reasoner")
    api_key = os.environ.get("RESEARCHER_API_KEY", os.environ.get("ANTHROPIC_API_KEY", "sk-746322967ed04448b49e5a9273b1fdfd"))
    base_url = os.environ.get("RESEARCHER_BASE_URL", "https://api.deepseek.com")
    
    # 根据模型名称动态派发 Client。因为 DeepSeek 官方 API 走的是 OpenAI 兼容易协议
    if "deepseek" in model_name.lower() or "api.deepseek.com" in base_url:
        # 深蓝官方 / 代理协议：兼容 OpenAI
        # 这里需要注意的是：deepseek-reasoner (思考模式) 在官方 API 层面目前可能不支持 Function Calling
        # 如果调用失败，可在后续切换为 deepseek-chat 测试
        # 我们使用 base_url + "/v1" 因为 LangChain 通常需要这个后缀或者在 BaseURL 中自带
        actual_url = base_url if base_url.endswith("/v1") else base_url + "/v1" if "deepseek.com" in base_url else base_url
        from langchain_deepseek import ChatDeepSeek
        return ChatDeepSeek(
            model=model_name,
            api_key=api_key,
            api_base=actual_url,
            temperature=0.7 if "reasoner" not in model_name else None,
        ).bind_tools(tools)
    else:
        # 兜底：Claude 系列走 Anthropic 协议
        return ChatAnthropic(
            model=model_name,
            api_key=api_key,
            base_url=base_url if base_url else None,
            temperature=0.7,
        ).bind_tools(tools)





def research_node(state: AgentState) -> dict:
    """同步入口（LangGraph 节点），内部运行异步逻辑。"""
    return asyncio.run(_research_node_async(state))


async def _research_node_async(state: AgentState) -> dict:
    logger.info("[Researcher] 正在思考新的量化因子假设（第 %d/%d 轮）...",
                state["current_iteration"], state["max_iterations"])

    # 1. 获取 MCP 工具（正确的 0.1.0 用法：不用 async with）
    try:
        tools = await _MCP_CLIENT.get_tools()
        logger.info("[Researcher] 成功加载 %d 个 AKShare MCP 工具", len(tools))
    except Exception as e:
        logger.warning("[Researcher] MCP 工具加载失败，降级为无工具模式: %s", e)
        tools = []

    # 2. 构建 LLM（带工具绑定）
    llm = _build_llm(tools)

    # 3. 加载 Skills（按状态条件动态组合）
    skill_context = _SKILL_LOADER.load_for_researcher(state)

    # 同时加载因子字典（Layer 1 知识库，独立于 Skills）
    factor_dict = ""
    try:
        with open(DICTIONARY_PATH, "r", encoding="utf-8") as f:
            factor_dict = f.read()
    except Exception as e:
        logger.warning("因子字典加载失败: %s", e)

    # 4. 构建 System Prompt（结构清晰：角色 + Skills + 工具列表）
    island_name = state.get("island_name", "momentum")
    from src.factor_pool.islands import ISLANDS
    island_info = ISLANDS.get(island_name, {})

    system_prompt = f"""你是一名顶尖的量化研究员，专注于 A 股市场 Alpha 因子发现。

## 当前研究 Island
- 代号：{island_name}（{island_info.get('name', '')}）
- 方向：{island_info.get('description', '')}

## 行为规范与约束
{skill_context}

## 因子参考字典
{factor_dict}

## 可用实时数据工具
- get_northbound_flow_today()：今日北向资金
- get_northbound_flow_history(days)：北向历史序列
- get_market_fund_flow(days)：全市场主力资金
- get_northbound_top_holdings(market, top_n)：北向持股变化
- get_research_reports(symbol, limit)：券商研报
- get_industry_pe(classification, query_date)：行业 PE
- get_individual_fund_flow_rank(period, top_n)：个股资金排行
- get_island_best_factors(island_name, top_k)：本 Island 历史最优 ← 必须调用
- get_similar_failures(formula, top_k)：相似失败案例
- get_island_leaderboard()：所有 Island 排行
- get_pool_stats()：全局实验统计

当前迭代：{state['current_iteration']}/{state['max_iterations']}
"""
    # 5. 构建用户上下文（根据历史反馈调整）
    user_prompt_suffix = "\n\n【重要！你必须最终输出经过深思熟虑的一个JSON数据结果，格式必须严格为：\n```json\n{\n  \"name\": \"因子名(如 ROE_Growth)\",\n  \"formula\": \"合法的Qlib公式\",\n  \"hypothesis\": \"简短假设说明\",\n  \"market_observation\": \"最新行情和数据观察\",\n  \"rationale\": \"量化大模型推理出的交易逻辑\"\n}\n```\n】"

    if state.get("error_message"):
        user_msg = f"上一次回测遇到了错误：\n{state['error_message']}\n请修正假设或公式，并先获取实时数据辅助判断。" + user_prompt_suffix
    elif state.get("backtest_result"):
        user_msg = f"上一次回测结果：\n{state['backtest_result']}\n请基于此结果优化因子，调用工具检查当前市场环境是否适合这个方向。" + user_prompt_suffix
    else:
        user_msg = "请先调用 1-2 个实时数据工具观察今日市场，然后提出一个有潜力的 Alpha 因子假设。" + user_prompt_suffix

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_msg),
    ]

    # 6. 支持工具调用的 agentic loop（最多 7 轮工具调用）
    for _ in range(7):
        response = await llm.ainvoke(messages)
        messages.append(response)

        # 检查是否还要调用工具
        if not getattr(response, "tool_calls", None):
            break

        # 执行工具调用
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call.get("args", {})
            matched_tool = next((t for t in tools if t.name == tool_name), None)
            if matched_tool:
                try:
                    tool_result = await matched_tool.ainvoke(tool_args)
                    logger.info("[Researcher] 工具 %s 返回 %d 字节", tool_name, len(str(tool_result)))
                except Exception as e:
                    tool_result = f"工具调用失败: {e}"

                from langchain_core.messages import ToolMessage
                messages.append(
                    ToolMessage(content=str(tool_result), tool_call_id=tool_call["id"])
                )

    logger.info("[Researcher] 因子假设生成完毕")

    # 解析结构化输出
    factor_hypothesis, factor_proposal_str = _parse_factor_hypothesis(response.content)

    return {
        "factor_hypothesis": factor_hypothesis,
        "factor_proposal": factor_proposal_str,   # Coder 仍然读这个字段
        "messages": [response],
    }

def _parse_factor_hypothesis(content: str):
    """从 LLM 输出中提取结构化 FactorHypothesis。

    优先解析 JSON；失败则降级为纯文本模式（保持兼容性）。
    返回 (FactorHypothesis | None, str)
    """
    import json, re

    # 尝试提取 JSON 块
    json_match = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
    if not json_match:
        # 也尝试不带 ``` 的裸 JSON
        json_match = re.search(r"(\{[^{}]*\"name\"[^{}]*\"formula\"[^{}]*\})", content, re.DOTALL)

    if json_match:
        try:
            data = json.loads(json_match.group(1))
            hypothesis = FactorHypothesis(**data)
            # 生成供 Coder 使用的字符串（公式是最关键的部分）
            proposal_str = (
                f"【因子名称】{hypothesis.name}\n"
                f"【Qlib 公式】{hypothesis.formula}\n"
                f"【假设描述】{hypothesis.hypothesis}\n"
                f"【市场观察】{hypothesis.market_observation}\n"
                f"【预期逻辑】{hypothesis.rationale}"
            )
            logger.info("[Researcher] 结构化解析成功：%s", hypothesis.name)
            return hypothesis, proposal_str
        except Exception as e:
            logger.warning("[Researcher] JSON 解析失败，降级为文本模式: %s", e)

    # 降级：返回原始文本，factor_hypothesis 为 None
    logger.warning("[Researcher] 未能提取结构化输出，使用原始文本")
    return None, content
