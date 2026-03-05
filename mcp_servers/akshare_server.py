"""
EvoQuant AKShare MCP Server
工具：北向资金、全市场资金流、北向持股、券商研报、行业估值
启动：python mcp_servers/akshare_server.py
"""
import json
import logging
from datetime import date, timedelta

import akshare as ak
import pandas as pd
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("akshare-mcp")

app = FastMCP("akshare-mcp")


# ─────────────────────────────────────────────
# 工具 1：北向资金当日摘要
# ─────────────────────────────────────────────
@app.tool()
async def get_northbound_flow_today() -> str:
    """获取今日沪深港通北向/南向资金实时净流入摘要（亿元）。

    返回字段：交易日、类型(沪港通/深港通)、板块、资金方向、
    成交净买额、资金净流入、上涨数、下跌数、相关指数涨跌幅。
    用途：判断当日外资情绪，是市场情绪的高频强信号。
    """
    try:
        df = ak.stock_hsgt_fund_flow_summary_em()
        # 只保留北向资金（外资流入A股方向）
        north = df[df["资金方向"] == "北向"].copy()
        if north.empty:
            north = df  # 若过滤后为空则返回全量
        result = north.to_dict(orient="records")
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_northbound_flow_today failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 2：北向资金历史序列
# ─────────────────────────────────────────────
@app.tool()
async def get_northbound_flow_history(days: int = 20) -> str:
    """获取北向资金最近 N 个交易日的净买入历史（默认20天）。

    Args:
        days: 返回最近多少个交易日的数据，默认 20，最大 60。

    返回字段：日期、北向资金净买入（亿元）、累计净买入。
    用途：构建北向资金 N 日动量/反转因子，研究外资趋势性行为。
    """
    try:
        days = min(max(days, 1), 60)  # 限制在 [1, 60] 范围
        df = ak.stock_hsgt_hist_em(symbol="北向资金")
        df = df.tail(days)
        result = df.to_dict(orient="records")
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_northbound_flow_history failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 3：全市场主力资金流向
# ─────────────────────────────────────────────
@app.tool()
async def get_market_fund_flow(days: int = 10) -> str:
    """获取全市场主力/超大单/大单净流入历史（默认10天）。

    Args:
        days: 返回最近多少个交易日，默认 10，最大 30。

    返回字段：日期、上证收盘价、主力净流入净额、主力净流入净占比、
    超大单净流入、大单净流入、中单净流入、小单净流入。
    用途：判断市场整体资金面情绪，区分主力/散户行为。
    """
    try:
        days = min(max(days, 1), 30)
        df = ak.stock_market_fund_flow()
        df = df.tail(days)
        result = df.to_dict(orient="records")
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_market_fund_flow failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 4：北向持股排行（个股级别）
# ─────────────────────────────────────────────
@app.tool()
async def get_northbound_top_holdings(market: str = "沪股通", top_n: int = 20) -> str:
    """获取北向资金持股排行（5日增减仓排行）。

    Args:
        market: 市场类型，可选 '沪股通' 或 '深股通'，默认 '沪股通'。
        top_n: 返回前 N 只股票，默认 20，最大 50。

    返回字段：股票代码、股票名称、今日持股量、今日持股市值、
    持股变化量、持股变化比例。
    用途：识别外资重点加仓/减仓标的，个股层面外资情绪信号。
    """
    try:
        top_n = min(max(top_n, 1), 50)
        if market not in ("沪股通", "深股通"):
            market = "沪股通"
        df = ak.stock_hsgt_hold_stock_em(market=market, indicator="5日排行")
        df = df.head(top_n)
        result = df.to_dict(orient="records")
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_northbound_top_holdings failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 5：券商研报（个股）
# ─────────────────────────────────────────────
@app.tool()
async def get_research_reports(symbol: str, limit: int = 5) -> str:
    """获取指定股票最近的券商研报元数据。

    Args:
        symbol: 股票代码，如 '000001'（平安银行）或 '600519'（贵州茅台）。
        limit: 返回最近几篇研报，默认 5，最大 20。

    返回字段：研报标题、发布机构、评级、目标价、发布日期。
    注意：只返回元数据，不返回研报全文（版权限制）。
    用途：聚合分析师共识，用评级/目标价构建情绪因子。
    """
    try:
        limit = min(max(limit, 1), 20)
        df = ak.stock_research_report_em(symbol=symbol)
        if df.empty:
            return json.dumps([], ensure_ascii=False)
        # 选取关键字段（不同版本字段名可能不同，做兼容处理）
        possible_cols = {
            "title": ["title", "标题", "研报标题"],
            "org": ["org", "机构", "发布机构"],
            "rating": ["rating", "评级"],
            "target_price": ["target_price", "目标价"],
            "date": ["date", "发布时间", "日期"],
        }
        selected = {}
        for key, candidates in possible_cols.items():
            for col in candidates:
                if col in df.columns:
                    selected[key] = col
                    break

        if selected:
            result_df = df[[v for v in selected.values()]].head(limit)
            result_df.columns = list(selected.keys())
        else:
            result_df = df.head(limit)

        result = result_df.to_dict(orient="records")
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_research_reports failed for %s: %s", symbol, e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 6：行业 PE 估值
# ─────────────────────────────────────────────
@app.tool()
async def get_industry_pe(
    classification: str = "证监会行业分类",
    query_date: str = "",
) -> str:
    """获取行业 PE-TTM 估值数据。

    Args:
        classification: 行业分类标准，可选 '证监会行业分类' 或 '申万行业分类'，
                        默认 '证监会行业分类'。
        query_date: 查询日期，格式 'YYYYMMDD'，默认为昨日。

    返回字段：行业名称、行业代码、样本数、市盈率PE（加权/中位/等权）。
    用途：行业估值分位因子，判断行业是否被高估/低估。
    """
    try:
        if not query_date:
            yesterday = date.today() - timedelta(days=1)
            query_date = yesterday.strftime("%Y%m%d")

        if classification not in ("证监会行业分类", "申万行业分类"):
            classification = "证监会行业分类"

        df = ak.stock_industry_pe_ratio_cninfo(
            symbol=classification, date=query_date
        )
        if df.empty:
            return json.dumps({"error": f"No data for date {query_date}"}, ensure_ascii=False)

        result = df.to_dict(orient="records")
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_industry_pe failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 7：个股资金流向排行
# ─────────────────────────────────────────────
@app.tool()
async def get_individual_fund_flow_rank(period: str = "今日", top_n: int = 20) -> str:
    """获取个股资金流入排行榜。

    Args:
        period: 统计周期，可选 '今日'、'3日'、'5日'、'10日'，默认 '今日'。
        top_n: 返回前 N 只股票，默认 20，最大 50。

    返回字段：股票名称、最新价、涨跌幅、主力净流入净额、主力净流入净占比等。
    用途：识别单日/多日主力资金重点流入标的，构建个股资金面因子。
    """
    try:
        valid_periods = ("今日", "3日", "5日", "10日")
        if period not in valid_periods:
            period = "今日"
        top_n = min(max(top_n, 1), 50)

        df = ak.stock_individual_fund_flow_rank(indicator=period)
        df = df.head(top_n)
        result = df.to_dict(orient="records")
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_individual_fund_flow_rank failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# Server 启动入口
# ─────────────────────────────────────────────
if __name__ == "__main__":
    logger.info("AKShare MCP Server starting...")
    app.run(transport='stdio')
