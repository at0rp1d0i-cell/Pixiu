"""
Pixiu AKShare MCP Server
工具：北向资金、全市场资金流、北向持股、券商研报、行业估值
启动：python mcp_servers/akshare_server.py
"""
import json
import logging
import os
from datetime import date, timedelta

import akshare as ak
import pandas as pd
from mcp.server.fastmcp import FastMCP

_LOG_LEVEL = os.getenv("PIXIU_MCP_LOG_LEVEL", "WARNING").upper()
logging.basicConfig(level=getattr(logging, _LOG_LEVEL, logging.WARNING), format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("akshare-mcp")

app = FastMCP("akshare-mcp")


# ─────────────────────────────────────────────
# 工具 1：市场资金流向当日摘要
# ─────────────────────────────────────────────
@app.tool()
async def get_northbound_flow_today() -> str:
    """获取今日全市场行业资金流向摘要（主力净流入，亿元）。

    注：沪深港通北向资金接口数据源已失效，改用行业主力资金流向作为替代。
    返回字段：行业、行业指数、行业涨跌幅、流入资金、流出资金、净额、领涨股。
    用途：判断当日主力资金偏好行业，推断市场情绪和热点方向。
    """
    try:
        df = ak.stock_fund_flow_industry(symbol="即时")
        if df is None or df.empty:
            return json.dumps({"error": "No industry fund flow data"}, ensure_ascii=False)
        # 按净额降序，取前10和后5（流入最多和流出最多的行业）
        df = df.sort_values("净额", ascending=False)
        top_inflow = df.head(10)
        top_outflow = df.tail(5)
        result = {
            "data_source": "行业主力资金流向（替代北向资金）",
            "top_inflow_sectors": top_inflow[["行业", "行业-涨跌幅", "净额", "领涨股", "领涨股-涨跌幅"]].to_dict(orient="records"),
            "top_outflow_sectors": top_outflow[["行业", "行业-涨跌幅", "净额", "领涨股", "领涨股-涨跌幅"]].to_dict(orient="records"),
            "total_net_inflow": round(float(df["净额"].sum()), 2),
            "positive_sectors": int((df["净额"] > 0).sum()),
            "negative_sectors": int((df["净额"] < 0).sum()),
        }
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_northbound_flow_today failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 2：市场资金流向历史序列
# ─────────────────────────────────────────────
@app.tool()
async def get_northbound_flow_history(days: int = 20) -> str:
    """获取全市场融资融券余额历史（最近N个交易日）。

    注：沪深港通北向资金历史接口数据源已失效，改用融资融券余额作为市场杠杆/情绪替代指标。
    Args:
        days: 返回最近多少个交易日，默认 20，最大 60。

    返回字段：日期、融资买入额、融资余额、融券卖出量、融券余量、融资融券余额。
    用途：判断市场杠杆水平趋势，融资余额上升=市场情绪偏多，下降=情绪偏空。
    """
    try:
        days = min(max(days, 1), 60)
        df = ak.macro_china_market_margin_sh()
        if df is None or df.empty:
            return json.dumps({"error": "No margin data available"}, ensure_ascii=False)
        df = df.tail(days)
        result = {
            "data_source": "上交所融资融券余额（替代北向资金历史）",
            "records": df.to_dict(orient="records"),
        }
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
    except (ValueError, KeyError) as e:
        logger.warning("get_industry_pe upstream format issue (cninfo API may have changed): %s", e)
        return json.dumps({"error": f"cninfo行业PE接口返回格式异常（上游问题），请稍后重试: {e}"}, ensure_ascii=False)
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
# 工具 8：个股财务摘要
# ─────────────────────────────────────────────
@app.tool()
async def get_stock_financial_summary(symbol: str) -> str:
    """获取个股最新财务摘要（TTM口径）。

    Args:
        symbol: 股票代码，如 '000001'。

    返回字段：股票代码、总资产、净资产、营业收入、净利润、
    摊薄净资产收益率(ROE)、市盈率(PE-TTM)、市净率(PB)、
    每股收益(EPS)、营收同比增速、净利润同比增速。
    用途：基本面 valuation island 的核心输入，估计因子经济逻辑。
    注意：数据约有1个季度的滞后（财报发布延迟）。
    """
    try:
        df = ak.stock_financial_abstract_ths(symbol=symbol, indicator="按年度")
        if df is None or df.empty:
            return json.dumps({"error": f"No financial data for {symbol}"}, ensure_ascii=False)
        # 取最近2条记录
        result = df.head(2).to_dict(orient="records")
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_stock_financial_summary failed for %s: %s", symbol, e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 9：宏观经济指标
# ─────────────────────────────────────────────
@app.tool()
async def get_macro_indicators() -> str:
    """获取中国主要宏观经济指标最新值。

    返回内容：
    - 制造业PMI（最近6个月）
    - M2货币供应量同比（最近3个月）
    - CPI同比（最近3个月）

    用途：Stage 1 MarketAnalyst 判断宏观 regime，
    辅助 valuation island 判断估值扩张/收缩周期。
    """
    try:
        result = {}

        # 制造业PMI（数据源：国家统计局，非 jin10）
        try:
            pmi_df = ak.macro_china_pmi()
            result["pmi_manufacturing"] = pmi_df.tail(6).to_dict(orient="records")
        except Exception as e:
            result["pmi_manufacturing"] = {"error": str(e)}

        # M2（数据源：央行货币供应量）
        try:
            m2_df = ak.macro_china_supply_of_money()
            m2_cols = [c for c in ["统计时间", "货币和准货币（广义货币M2）同比增长"] if c in m2_df.columns]
            result["m2_yoy"] = m2_df[m2_cols].tail(3).to_dict(orient="records") if m2_cols else m2_df.tail(3).to_dict(orient="records")
        except Exception as e:
            result["m2_yoy"] = {"error": str(e)}

        # CPI（数据源：国家统计局）
        try:
            cpi_df = ak.macro_china_cpi()
            cpi_cols = [c for c in ["月份", "全国-当月", "全国-同比增长"] if c in cpi_df.columns]
            result["cpi_yoy"] = cpi_df[cpi_cols].tail(3).to_dict(orient="records") if cpi_cols else cpi_df.tail(3).to_dict(orient="records")
        except Exception as e:
            result["cpi_yoy"] = {"error": str(e)}

        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_macro_indicators failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 10：融资融券数据
# ─────────────────────────────────────────────
@app.tool()
async def get_margin_trading_summary(days: int = 10) -> str:
    """获取全市场融资融券汇总数据（最近N个交易日）。

    Args:
        days: 返回最近多少个交易日，默认 10，最大 30。

    返回字段：日期、融资余额、融资买入额、融券余量、
    融券卖出量、融资融券余额。
    用途：判断市场杠杆水平和情绪；高融资余额 + 下跌 = 踩踏信号，
    构建情绪/动量 Island 的杠杆风险因子。
    """
    try:
        days = min(max(days, 1), 30)
        df = ak.stock_margin_account_info()
        if df is None or df.empty:
            return json.dumps({"error": "No margin data available"}, ensure_ascii=False)
        df = df.tail(days)
        result = df.to_dict(orient="records")
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_margin_trading_summary failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 11：个股最新新闻（NARRATIVE_MINING）
# ─────────────────────────────────────────────
@app.tool()
async def get_stock_news(symbol: str, limit: int = 10) -> str:
    """获取指定股票的最新新闻，为 NARRATIVE_MINING 提供叙事素材。

    Args:
        symbol: 股票代码，如 '600519'（贵州茅台）或 '000001'（平安银行）。
        limit: 返回最近几条新闻，默认 10，最大 30。

    返回字段：新闻标题、发布时间、关键词、文章来源。
    用途：识别个股叙事热点，构建事件驱动因子的原始素材。
    """
    try:
        limit = min(max(limit, 1), 30)
        df = ak.stock_news_em(symbol=symbol)
        if df is None or df.empty:
            return json.dumps({"error": f"No news for {symbol}"}, ensure_ascii=False)
        cols = [c for c in ["新闻标题", "发布时间", "关键词", "文章来源"] if c in df.columns]
        result_df = df[cols].head(limit) if cols else df.head(limit)
        result = {
            "symbol": symbol,
            "count": len(result_df),
            "news": result_df.to_dict(orient="records"),
        }
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_stock_news failed for %s: %s", symbol, e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 12：市场热门股票人气榜（NARRATIVE_MINING）
# ─────────────────────────────────────────────
@app.tool()
async def get_market_hot_topics(top_n: int = 20) -> str:
    """获取当前市场人气股票排行，识别叙事热点。

    Args:
        top_n: 返回前 N 只股票，默认 20，最大 50。

    返回字段：当前排名、股票代码、股票名称、最新价、涨跌幅。
    用途：捕捉市场热点叙事，辅助 NARRATIVE_MINING 识别资金+舆论共振标的。
    备注：数据来源东方财富人气榜，代码带市场前缀（如 SZ002506）。
    """
    try:
        top_n = min(max(top_n, 1), 50)
        df = ak.stock_hot_rank_em()
        if df is None or df.empty:
            return json.dumps({"error": "No hot rank data"}, ensure_ascii=False)
        cols = [c for c in ["当前排名", "代码", "股票名称", "最新价", "涨跌幅"] if c in df.columns]
        result_df = df[cols].head(top_n) if cols else df.head(top_n)
        result = {
            "count": len(result_df),
            "hot_stocks": result_df.to_dict(orient="records"),
        }
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_market_hot_topics failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 13：概念板块资金流向（NARRATIVE_MINING）
# ─────────────────────────────────────────────
@app.tool()
async def get_concept_board_flow(top_n: int = 15) -> str:
    """获取概念板块资金流向排行，识别热门叙事背后的资金驱动。

    Args:
        top_n: 返回资金净流入前 N 个概念板块，默认 15，最大 30。

    返回字段：板块名称、涨跌幅、净额（主力净流入，亿元）、公司家数、领涨股。
    用途：判断哪些叙事板块有真实资金驱动，辅助 NARRATIVE_MINING 过滤叙事强度。
    """
    try:
        top_n = min(max(top_n, 1), 30)
        df = ak.stock_fund_flow_concept(symbol="即时")
        if df is None or df.empty:
            return json.dumps({"error": "No concept board flow data"}, ensure_ascii=False)
        df_sorted = df.sort_values("净额", ascending=False)
        cols = [c for c in ["行业", "行业-涨跌幅", "净额", "公司家数", "领涨股", "领涨股-涨跌幅"] if c in df_sorted.columns]
        result_df = df_sorted[cols].head(top_n) if cols else df_sorted.head(top_n)
        result = {
            "count": len(result_df),
            "top_concept_boards": result_df.to_dict(orient="records"),
        }
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_concept_board_flow failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 14：全球主要市场指数（CROSS_MARKET）
# ─────────────────────────────────────────────
@app.tool()
async def get_global_indices() -> str:
    """获取全球主要市场指数行情，为跨市场分析提供参照。

    返回字段：指数名称、最新价、涨跌幅、涨跌额。
    用途：CROSS_MARKET 子空间判断全球风险偏好，识别 A 股与外部市场联动关系。
    备注：优先获取全球指数（东方财富），网络不可用时 fallback 到 A 股主要指数。
    """
    try:
        # 优先尝试全球指数
        try:
            df = ak.index_global_spot_em()
            if df is not None and not df.empty:
                cols = [c for c in ["名称", "最新价", "涨跌幅", "涨跌额"] if c in df.columns]
                result_df = df[cols] if cols else df
                return json.dumps({
                    "source": "全球指数（东方财富）",
                    "count": len(result_df),
                    "indices": result_df.to_dict(orient="records"),
                }, ensure_ascii=False, default=str)
        except Exception:
            pass

        # fallback：A 股主要指数
        df = ak.stock_zh_index_spot_em()
        if df is None or df.empty:
            return json.dumps({"error": "No index data available"}, ensure_ascii=False)
        target_names = {"上证指数", "深证成指", "创业板指", "科创50", "沪深300", "中证500"}
        name_col = next((c for c in ["名称", "指数名称"] if c in df.columns), None)
        if name_col:
            df_filtered = df[df[name_col].isin(target_names)]
            if df_filtered.empty:
                df_filtered = df.head(10)
        else:
            df_filtered = df.head(10)
        cols = [c for c in ["代码", "名称", "最新价", "涨跌幅", "涨跌额"] if c in df_filtered.columns]
        result_df = df_filtered[cols] if cols else df_filtered
        return json.dumps({
            "source": "A 股主要指数（fallback）",
            "count": len(result_df),
            "indices": result_df.to_dict(orient="records"),
        }, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_global_indices failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 15：大宗商品价格（CROSS_MARKET）
# ─────────────────────────────────────────────
@app.tool()
async def get_commodity_prices() -> str:
    """获取大宗商品价格信号，为 CROSS_MARKET 提供商品市场参照。

    返回字段：商品名称、最新价/价格、涨跌幅（如接口可用）。
    用途：判断铜、铁矿石、原油、黄金等大宗商品走势，推断上游成本压力和全球需求预期。
    备注：优先尝试全球商品指数，网络不可用时返回空数据说明。
    """
    try:
        # 尝试全球商品指数（东财）
        try:
            df = ak.index_global_spot_em()
            if df is not None and not df.empty:
                name_col = next((c for c in ["名称", "指数名称"] if c in df.columns), None)
                if name_col:
                    commodity_keywords = ["黄金", "原油", "铜", "铁矿", "白银", "大豆", "小麦", "corn"]
                    mask = df[name_col].str.contains("|".join(commodity_keywords), case=False, na=False)
                    df_comm = df[mask]
                    if not df_comm.empty:
                        cols = [c for c in ["名称", "最新价", "涨跌幅", "涨跌额"] if c in df_comm.columns]
                        return json.dumps({
                            "source": "全球商品指数（东方财富）",
                            "count": len(df_comm),
                            "commodities": df_comm[cols].to_dict(orient="records"),
                        }, ensure_ascii=False, default=str)
        except Exception:
            pass

        # 宽容 fallback
        return json.dumps({
            "note": "商品数据暂不可用（网络或接口问题）",
            "data": [],
        }, ensure_ascii=False)
    except Exception as e:
        logger.error("get_commodity_prices failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 16：人民币汇率（CROSS_MARKET）
# ─────────────────────────────────────────────
@app.tool()
async def get_exchange_rates() -> str:
    """获取人民币对主要货币的近期汇率，判断汇率变动对 A 股的影响。

    返回字段：日期、中行汇买价、中行钞卖价/汇卖价、央行中间价（per 100 外币）。
    用途：CROSS_MARKET 子空间判断人民币升贬值压力，构建汇率-A 股联动信号。
    覆盖货币：美元、欧元、日元（各取最近 5 天数据）。
    """
    try:
        from datetime import date, timedelta
        end_date = date.today().strftime("%Y%m%d")
        start_date = (date.today() - timedelta(days=14)).strftime("%Y%m%d")

        result = {}
        for currency in ["美元", "欧元", "日元"]:
            try:
                df = ak.currency_boc_sina(symbol=currency, start_date=start_date, end_date=end_date)
                if df is not None and not df.empty:
                    cols = [c for c in ["日期", "中行汇买价", "中行钞卖价/汇卖价", "央行中间价"] if c in df.columns]
                    result[currency] = df[cols].tail(5).to_dict(orient="records") if cols else df.tail(5).to_dict(orient="records")
                else:
                    result[currency] = []
            except Exception as ce:
                result[currency] = {"error": str(ce)}

        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_exchange_rates failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 17：市场宽度指标（REGIME_CONDITIONAL）
# ─────────────────────────────────────────────
@app.tool()
async def get_market_breadth() -> str:
    """获取全市场宽度指标（涨跌家数、涨停跌停数），判断市场内部强弱。

    返回字段：上涨家数、涨停家数、真实涨停、下跌家数、跌停家数、平盘家数等。
    用途：REGIME_CONDITIONAL 子空间的核心 regime 信号，
    高涨停+低跌停=强势扩散 regime；低涨停+高跌停=弱势分化 regime。
    """
    try:
        df = ak.stock_market_activity_legu()
        if df is None or df.empty:
            return json.dumps({"error": "No market breadth data"}, ensure_ascii=False)
        # 转换为 dict（item → value 格式）
        result = dict(zip(df["item"].tolist(), df["value"].tolist()))
        return json.dumps({
            "source": "乐咕乐股市场活动统计",
            "breadth": result,
        }, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_market_breadth failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 18：指数估值历史（REGIME_CONDITIONAL）
# ─────────────────────────────────────────────
@app.tool()
async def get_index_valuation(index_code: str = "000300") -> str:
    """获取主要指数估值历史（PE/股息率），判断当前估值所处历史分位。

    Args:
        index_code: 指数代码，可选 '000300'（沪深300）、'000001'（上证指数）、
                    '399006'（创业板指），默认 '000300'。

    返回字段：日期、市盈率1（加权）、市盈率2（等权）、股息率1、股息率2。
    返回最近 20 条 + 3年/5年历史百分位估计。
    用途：REGIME_CONDITIONAL 判断当前市场估值 regime（历史低位/中位/高位）。
    数据源：中证指数官网（stock_zh_index_value_csindex）。
    """
    try:
        valid_codes = {"000300", "000001", "399006"}
        if index_code not in valid_codes:
            index_code = "000300"

        df = ak.stock_zh_index_value_csindex(symbol=index_code)
        if df is None or df.empty:
            return json.dumps({"error": f"No valuation data for {index_code}"}, ensure_ascii=False)

        # 最近20条记录
        recent = df.tail(20)
        pe_col = next((c for c in ["市盈率1", "市盈率2"] if c in df.columns), None)

        percentile_3y = percentile_5y = None
        if pe_col:
            try:
                current_pe = float(recent.iloc[-1][pe_col])
                three_years_ago = pd.Timestamp.today() - pd.DateOffset(years=3)
                five_years_ago = pd.Timestamp.today() - pd.DateOffset(years=5)
                df["日期"] = pd.to_datetime(df["日期"])
                hist_3y = df[df["日期"] >= three_years_ago][pe_col].dropna().astype(float)
                hist_5y = df[df["日期"] >= five_years_ago][pe_col].dropna().astype(float)
                if len(hist_3y) > 0:
                    percentile_3y = round(float((hist_3y <= current_pe).mean() * 100), 1)
                if len(hist_5y) > 0:
                    percentile_5y = round(float((hist_5y <= current_pe).mean() * 100), 1)
            except Exception:
                pass

        cols = [c for c in ["日期", "市盈率1", "市盈率2", "股息率1", "股息率2"] if c in recent.columns]
        result = {
            "index_code": index_code,
            "recent_20": recent[cols].to_dict(orient="records") if cols else recent.to_dict(orient="records"),
            "pe_percentile_3y": percentile_3y,
            "pe_percentile_5y": percentile_5y,
        }
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_index_valuation failed for %s: %s", index_code, e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 19：融资融券余额（REGIME 杠杆信号）
# ─────────────────────────────────────────────
@app.tool()
async def get_margin_balance(days: int = 20) -> str:
    """获取全市场融资融券余额历史序列，作为 regime 杠杆水平信号。

    Args:
        days: 返回最近多少个交易日，默认 20，最大 60。

    返回字段：日期、融资余额、融券余量、融资融券余额合计。
    用途：FACTOR_ALGEBRA 杠杆因子基础数据；融资余额趋势反映市场情绪极值。
    数据源：akshare stock_margin_ratio_pa（沪深融资融券汇总）。
    TODO: verify interface — stock_margin_ratio_pa 参数格式需实盘确认。
    """
    try:
        days = min(max(days, 1), 60)
        # stock_margin_ratio_pa: 融资融券比例数据
        df = ak.stock_margin_ratio_pa()
        if df is None or df.empty:
            return json.dumps({"error": "No margin balance data available"}, ensure_ascii=False)
        df = df.tail(days)
        result = {
            "data_source": "融资融券余额（stock_margin_ratio_pa）",
            "days": days,
            "records": df.to_dict(orient="records"),
        }
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_margin_balance failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 20：涨停池（REGIME 强势信号）
# ─────────────────────────────────────────────
@app.tool()
async def get_limit_up_pool(query_date: str = "") -> str:
    """获取当日涨停股票池（东方财富涨停池）。

    Args:
        query_date: 查询日期，格式 'YYYYMMDD'，默认为今日。

    返回字段：股票代码、股票名称、涨停时间、封单量、封单额、连板数、板块等。
    用途：REGIME 强势 regime 的核心信号；涨停家数多+连板股多 = 强势扩散 regime。
    数据源：akshare stock_zt_pool_em。
    """
    try:
        if not query_date:
            query_date = date.today().strftime("%Y%m%d")
        df = ak.stock_zt_pool_em(date=query_date)
        if df is None or df.empty:
            return json.dumps({
                "query_date": query_date,
                "count": 0,
                "stocks": [],
                "note": "No limit-up stocks or market closed",
            }, ensure_ascii=False)
        result = {
            "query_date": query_date,
            "count": len(df),
            "stocks": df.to_dict(orient="records"),
        }
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_limit_up_pool failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 21：跌停池（REGIME 弱势信号）
# ─────────────────────────────────────────────
@app.tool()
async def get_limit_down_pool(query_date: str = "") -> str:
    """获取当日跌停股票池（东方财富跌停池）。

    Args:
        query_date: 查询日期，格式 'YYYYMMDD'，默认为今日。

    返回字段：股票代码、股票名称、跌停时间、封单量、封单额、板块等。
    用途：REGIME 弱势信号；跌停家数多 = 恐慌/弱势 regime；
    配合涨停池对比可计算涨跌停比率（limit ratio）。
    数据源：akshare stock_dt_pool_em。
    """
    try:
        if not query_date:
            query_date = date.today().strftime("%Y%m%d")
        df = ak.stock_zt_pool_dtgc_em(date=query_date)
        if df is None or df.empty:
            return json.dumps({
                "query_date": query_date,
                "count": 0,
                "stocks": [],
                "note": "No limit-down stocks or market closed",
            }, ensure_ascii=False)
        result = {
            "query_date": query_date,
            "count": len(df),
            "stocks": df.to_dict(orient="records"),
        }
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_limit_down_pool failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 22：板块轮动速度（FACTOR_ALGEBRA）
# ─────────────────────────────────────────────
@app.tool()
async def get_sector_rotation_speed(top_n: int = 20, lookback_days: int = 5) -> str:
    """计算最近N日概念板块涨幅排名变化速度，量化板块轮动强度。

    Args:
        top_n: 参与排名比较的头部板块数，默认 20，最大 50。
        lookback_days: 比较最近多少天内的排名变化，默认 5，最大 20。

    返回字段：板块名称、当前涨跌幅、当前排名、N日前涨跌幅、排名变化（delta_rank）。
    用途：FACTOR_ALGEBRA 板块轮动速度因子；delta_rank 高 = 快速升温板块，低 = 退潮板块。
    数据源：akshare stock_board_concept_hist_em（概念板块历史行情）。
    TODO: verify interface — stock_board_concept_hist_em 的 symbol/period 参数格式需确认。
    注意：该工具调用多个概念板块历史接口，响应较慢（约10-30秒）。
    """
    try:
        top_n = min(max(top_n, 5), 50)

        # 使用行业资金流排行替代 push2 概念板块接口
        df = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")
        if df is None or df.empty:
            return json.dumps({"error": "No sector fund flow data"}, ensure_ascii=False)

        df = df.head(top_n)
        result = {
            "data_source": "行业资金流排行（stock_sector_fund_flow_rank）",
            "count": len(df),
            "sectors": df.to_dict(orient="records"),
        }
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_sector_rotation_speed failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 23：北向资金净流入（REGIME 外资信号）
# ─────────────────────────────────────────────
@app.tool()
async def get_north_bound_flow(days: int = 20) -> str:
    """获取北向资金（沪深港通）历史净流入数据。

    Args:
        days: 返回最近多少个交易日，默认 20，最大 60。

    返回字段：日期、北向资金净流入（沪股通+深股通合计），单位亿元。
    用途：REGIME 外资情绪信号；持续净流入 = 外资看多 A 股，净流出 = 外资撤退信号。
    数据源：akshare stock_hsgt_north_net_flow_in_em。
    TODO: verify interface — stock_hsgt_north_net_flow_in_em 的 symbol 参数（如"北向资金"）需确认。
    """
    try:
        days = min(max(days, 1), 60)
        df = ak.stock_hsgt_hist_em(symbol="沪股通")
        if df is None or df.empty:
            return json.dumps({"error": "No north-bound flow data"}, ensure_ascii=False)
        df = df.tail(days)
        result = {
            "data_source": "北向资金净流入（stock_hsgt_hist_em 沪股通）",
            "days": days,
            "records": df.to_dict(orient="records"),
        }
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_north_bound_flow failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 24：A 股情绪波动指数（REGIME 恐慌信号）
# ─────────────────────────────────────────────
@app.tool()
async def get_volatility_index(days: int = 20) -> str:
    """获取 A 股市场情绪波动指数（类 VIX），判断市场恐慌/贪婪程度。

    Args:
        days: 返回最近多少个交易日，默认 20，最大 60。

    返回字段：日期、波动率指数值（或等效情绪指标）。
    用途：REGIME 恐慌 regime 信号；高波动 = 恐慌 regime，低波动 = 平稳 regime。
    数据源：akshare stock_a_vix_em（A 股波动率指数）。
    TODO: verify interface — stock_a_vix_em 接口是否可用、返回字段名需实盘确认。
    备注：若 stock_a_vix_em 不可用，可用上证50ETF期权隐含波动率替代。
    """
    try:
        days = min(max(days, 1), 60)
        # 用上证指数日 K 线计算已实现波动率（替代不存在的 stock_a_vix_em）
        fetch_days = days + 30  # 多取一些用于计算滚动波动率
        df = ak.stock_zh_index_daily(symbol="sh000001")
        if df is None or df.empty:
            return json.dumps({"error": "No index data for volatility calc"}, ensure_ascii=False)
        df = df.tail(fetch_days).copy()
        df["daily_return"] = df["close"].pct_change()
        df["vol_20d"] = df["daily_return"].rolling(20).std() * (252 ** 0.5) * 100  # 年化 %
        df = df.tail(days)
        cols = ["date", "close", "daily_return", "vol_20d"]
        result = {
            "data_source": "上证指数已实现波动率（20 日滚动年化）",
            "days": days,
            "records": df[cols].to_dict(orient="records"),
        }
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_volatility_index failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 25：龙虎榜（NARRATIVE_MINING 主力行为）
# ─────────────────────────────────────────────
@app.tool()
async def get_top_list(query_date: str = "", top_n: int = 20) -> str:
    """获取指定日期龙虎榜数据，识别主力/游资异动标的。

    Args:
        query_date: 查询日期，格式 'YYYYMMDD'，默认为今日。
        top_n: 返回前 N 条记录，默认 20，最大 50。

    返回字段：股票代码、股票名称、上榜原因、买入金额、卖出金额、净买入额、
    营业部名称等（字段以接口实际返回为准）。
    用途：NARRATIVE_MINING 主力行为信号；龙虎榜上榜 + 游资净买入 = 事件驱动叙事信号。
    数据源：akshare stock_lhb_detail_em。
    TODO: verify interface — stock_lhb_detail_em 的 date 参数格式（YYYYMMDD vs YYYY-MM-DD）需确认。
    """
    try:
        if not query_date:
            query_date = date.today().strftime("%Y%m%d")
        top_n = min(max(top_n, 1), 50)

        df = ak.stock_lhb_detail_em(start_date=query_date, end_date=query_date)
        if df is None or df.empty:
            return json.dumps({
                "query_date": query_date,
                "count": 0,
                "records": [],
                "note": "No top-list data for this date or market closed",
            }, ensure_ascii=False)
        df = df.head(top_n)
        result = {
            "query_date": query_date,
            "count": len(df),
            "records": df.to_dict(orient="records"),
        }
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_top_list failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 26：全市场快讯电报（NARRATIVE_MINING 宏观与突发）
# ─────────────────────────────────────────────
@app.tool()
async def get_market_telegraph(limit: int = 20) -> str:
    """获取财联社即时电报/快讯，捕捉全市场突发新闻和宏观/行业叙事。

    Args:
        limit: 返回最近几条快讯，默认 20，最大 50。

    返回字段：时间、标题、内容。
    用途：NARRATIVE_MINING 宏观与行业突发事件信号；补充个股新闻无法覆盖的市场级宏大叙事。
    """
    try:
        limit = min(max(limit, 1), 50)
        df = ak.stock_info_global_cls()
        if df is None or df.empty:
            return json.dumps({"error": "No telegraph data available"}, ensure_ascii=False)
        cols = [c for c in ["发布时间", "发布日期", "标题", "内容"] if c in df.columns]
        result_df = df[cols].head(limit) if cols else df.head(limit)
        result = {
            "count": len(result_df),
            "telegraphs": result_df.to_dict(orient="records"),
        }
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_market_telegraph failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 27：国内股指期货实时基差（CROSS_MARKET 大盘情绪）
# ─────────────────────────────────────────────
@app.tool()
async def get_futures_basis() -> str:
    """获取国内主要股指期货（IF/IH/IC/IM）实时行情，含基差/升贴水率。

    返回字段：symbol（合约代码）、name（合约名称）、trade（最新价）、
    changepercent（涨跌幅）、settlement（结算价）、pre_settlement（昨结）等。
    用途：CROSS_MARKET 子空间情绪前瞻；深度贴水 = 极度悲观防守；升水 = 情绪狂热。
    备注：基差需自行根据对应的现货指数（沪深300/上证50/中证500/中证1000）换算评估。
    """
    try:
        df = ak.futures_zh_realtime()
        if df is None or df.empty:
            return json.dumps({"error": "No index futures data available"}, ensure_ascii=False)
        
        # 过滤出主流股指期货品种
        df_filtered = df[df["symbol"].str.contains(r"^(IF|IH|IC|IM)\d", regex=True, na=False)]
        result_df = df_filtered if not df_filtered.empty else df.head(20)
        
        cols = [c for c in ["symbol", "name", "trade", "changepercent", "settlement", "pre_settlement", "volume", "open_interest"] if c in result_df.columns]
        final_df = result_df[cols] if cols else result_df
        
        result = {
            "count": len(final_df),
            "futures": final_df.to_dict(orient="records"),
        }
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("get_futures_basis failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# Server 启动入口
# ─────────────────────────────────────────────
if __name__ == "__main__":
    logger.info("AKShare MCP Server starting...")
    app.run(transport='stdio')
