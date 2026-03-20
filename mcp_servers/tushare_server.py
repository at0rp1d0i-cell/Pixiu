"""
Pixiu Tushare Pro MCP Server
工具：股票列表、日线行情、财务指标、融资融券、新闻、公告
积分要求：2000积分（学生套餐已激活）
启动：python mcp_servers/tushare_server.py
"""
import asyncio
import json
import logging
import os
from datetime import date, timedelta
from functools import partial

import tushare as ts
from mcp.server.fastmcp import FastMCP

_LOG_LEVEL = os.getenv("PIXIU_MCP_LOG_LEVEL", "WARNING").upper()
logging.basicConfig(level=getattr(logging, _LOG_LEVEL, logging.WARNING), format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("tushare-mcp")

app = FastMCP("tushare-mcp")

_pro = None


def _get_pro():
    """延迟初始化 Tushare Pro API 实例。"""
    global _pro
    if _pro is None:
        token = os.getenv("TUSHARE_TOKEN")
        if not token:
            raise RuntimeError("TUSHARE_TOKEN 环境变量未设置")
        _pro = ts.pro_api(token)
    return _pro


async def _call(func, **kwargs):
    """在线程池中执行同步 tushare 调用（tushare 无原生 async）。"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(func, **kwargs))


def _df_to_json(df, limit: int = 500) -> str:
    """DataFrame → JSON 字符串，截断超长结果。"""
    if df is None or df.empty:
        return json.dumps({"data": [], "count": 0}, ensure_ascii=False)
    records = df.head(limit).to_dict(orient="records")
    return json.dumps({"data": records, "count": len(df)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 1：股票基本信息
# ─────────────────────────────────────────────
@app.tool()
async def get_stock_list(
    market: str = "",
    list_status: str = "L",
) -> str:
    """获取 A 股全量股票基本信息（名称、行业、上市日期等）。

    Args:
        market: 市场类型，可选：主板/中小板/创业板/科创板/北交所，空字符串=全部
        list_status: 上市状态，L=上市 D=退市 P=暂停上市，默认 L

    Returns:
        JSON，包含 ts_code, symbol, name, area, industry, market, list_date
    积分要求：120积分
    """
    try:
        pro = _get_pro()
        df = await _call(
            pro.stock_basic,
            list_status=list_status,
            market=market,
            fields="ts_code,symbol,name,area,industry,market,list_date,exchange",
        )
        return _df_to_json(df, limit=6000)
    except Exception as e:
        logger.error("[tushare] get_stock_list error: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 2：日线行情
# ─────────────────────────────────────────────
@app.tool()
async def get_daily_prices(
    ts_code: str = "",
    trade_date: str = "",
    start_date: str = "",
    end_date: str = "",
) -> str:
    """获取 A 股日线 OHLCV 行情数据。

    Args:
        ts_code: 股票代码，如 000001.SZ，支持逗号分隔多只；ts_code 和 trade_date 至少填一个
        trade_date: 交易日期，格式 YYYYMMDD；获取单日所有股票数据时填此项
        start_date: 起始日期，格式 YYYYMMDD
        end_date: 结束日期，格式 YYYYMMDD；默认今日

    Returns:
        JSON，包含 ts_code, trade_date, open, high, low, close, pct_chg, vol, amount
    频率：500次/分钟，每次最多6000行
    积分要求：120积分
    """
    try:
        if not ts_code and not trade_date:
            trade_date = date.today().strftime("%Y%m%d")
        if not end_date and ts_code and start_date:
            end_date = date.today().strftime("%Y%m%d")

        pro = _get_pro()
        df = await _call(
            pro.daily,
            ts_code=ts_code,
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date,
        )
        return _df_to_json(df, limit=6000)
    except Exception as e:
        logger.error("[tushare] get_daily_prices error: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 3：财务指标
# ─────────────────────────────────────────────
@app.tool()
async def get_financial_indicators(
    ts_code: str,
    start_date: str = "",
    end_date: str = "",
    period: str = "",
) -> str:
    """获取单只股票的财务指标历史数据（ROE/ROA/EPS/毛利率/杠杆率等）。

    Args:
        ts_code: 股票代码，如 000001.SZ（必填）
        start_date: 起始报告期，格式 YYYYMMDD
        end_date: 结束报告期，格式 YYYYMMDD
        period: 指定单个报告期，如 20231231

    Returns:
        JSON，包含 eps, roe, roa, netprofit_margin, debt_to_assets, current_ratio 等核心指标
    积分要求：2000积分
    """
    try:
        if not ts_code:
            return json.dumps({"error": "ts_code 必填"}, ensure_ascii=False)
        pro = _get_pro()
        df = await _call(
            pro.fina_indicator,
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
            period=period,
            fields=(
                "ts_code,ann_date,end_date,eps,dt_eps,roe,roe_waa,roe_dt,"
                "roa,netprofit_margin,gross_margin,current_ratio,quick_ratio,"
                "debt_to_assets,assets_turn,inv_turn,ar_turn,ebit,ebitda,"
                "fcff,fcfe,profit_dedt,extra_item"
            ),
        )
        return _df_to_json(df, limit=100)
    except Exception as e:
        logger.error("[tushare] get_financial_indicators error: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 4：融资融券市场汇总
# ─────────────────────────────────────────────
@app.tool()
async def get_margin_data(
    trade_date: str = "",
    start_date: str = "",
    end_date: str = "",
    exchange_id: str = "",
) -> str:
    """获取全市场融资融券汇总数据（融资余额、融券余量等，regime 信号）。

    Args:
        trade_date: 交易日期，格式 YYYYMMDD；不填则取近30天
        start_date: 起始日期，格式 YYYYMMDD
        end_date: 结束日期，格式 YYYYMMDD
        exchange_id: 交易所，SSE=上交所 SZSE=深交所，空=全部

    Returns:
        JSON，包含 trade_date, exchange_id, rzye（融资余额）, rqye（融券余额）, rzrqye（融资融券余额）
    积分要求：120积分（市场汇总级别）
    """
    try:
        if not trade_date and not start_date:
            end_date = end_date or date.today().strftime("%Y%m%d")
            start_date = (date.today() - timedelta(days=30)).strftime("%Y%m%d")
        pro = _get_pro()
        df = await _call(
            pro.margin,
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date,
            exchange_id=exchange_id,
        )
        return _df_to_json(df, limit=200)
    except Exception as e:
        logger.error("[tushare] get_margin_data error: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 5：财经新闻
# ─────────────────────────────────────────────
@app.tool()
async def get_news(
    src: str = "sina",
    start_date: str = "",
    end_date: str = "",
    limit: int = 100,
) -> str:
    """获取财经新闻（新浪、东方财富、华尔街见闻等），用于 NARRATIVE_MINING 子空间。

    Args:
        src: 新闻来源，sina=新浪财经, eastmoney=东方财富, wallstreetcn=华尔街见闻,
             ccstock=中国证券网, cctv=央视财经，默认 sina
        start_date: 起始时间，格式 YYYY-MM-DD HH:MM:SS，默认今日 09:00:00
        end_date: 结束时间，格式 YYYY-MM-DD HH:MM:SS，默认当前时间
        limit: 返回条数，最多 1000

    Returns:
        JSON，包含 datetime, title, content, channels
    积分要求：2000积分
    """
    try:
        today = date.today().strftime("%Y-%m-%d")
        if not start_date:
            start_date = f"{today} 09:00:00"
        if not end_date:
            end_date = f"{today} 23:59:59"
        pro = _get_pro()
        df = await _call(
            pro.news,
            src=src,
            start_date=start_date,
            end_date=end_date,
            limit=min(limit, 1000),
        )
        return _df_to_json(df, limit=limit)
    except Exception as e:
        logger.error("[tushare] get_news error: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# 工具 6：上市公司公告
# ─────────────────────────────────────────────
@app.tool()
async def get_announcements(
    ts_code: str = "",
    ann_date: str = "",
    start_date: str = "",
    end_date: str = "",
    ann_type: str = "",
) -> str:
    """获取上市公司公告（业绩预告、重大事项、定增等），用于 NARRATIVE_MINING 事件驱动分析。

    Args:
        ts_code: 股票代码，如 000001.SZ；ts_code 和 ann_date 至少填一个
        ann_date: 公告日期，格式 YYYYMMDD
        start_date: 起始日期，格式 YYYYMMDD
        end_date: 结束日期，格式 YYYYMMDD
        ann_type: 公告类别代码，空=全部

    Returns:
        JSON，包含 ts_code, ann_date, ann_type, title, content, pub_time, url
    积分要求：2000积分
    """
    try:
        if not ts_code and not ann_date:
            ann_date = date.today().strftime("%Y%m%d")
        pro = _get_pro()
        df = await _call(
            pro.anns,
            ts_code=ts_code,
            ann_date=ann_date,
            start_date=start_date,
            end_date=end_date,
            ann_type=ann_type,
        )
        return _df_to_json(df, limit=200)
    except Exception as e:
        logger.error("[tushare] get_announcements error: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


if __name__ == "__main__":
    logger.info("Tushare MCP Server starting... (6 tools)")
    app.run(transport="stdio")
