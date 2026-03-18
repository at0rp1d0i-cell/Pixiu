"""
Cross-Market MCP Server — FRED + yfinance + Jina Reader
Provides global macro signals and cross-market data for Stage 1 regime detection.

Tools: US treasury yields, USD/CNY rate, VIX/credit spreads, global equity indices,
       commodity prices, USD index, cross-market snapshot, article content extraction.
Start: python mcp_servers/cross_market_server.py

跨市场数据 MCP 服务器，集成 FRED 宏观数据、yfinance 全球市场行情和 Jina 文章提取。
为 Stage 1 市场制度检测提供美债收益率、汇率、VIX、全球指数、大宗商品等跨市场信号。
"""

import json
import logging
import os

import httpx
import pandas as pd
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("cross-market-mcp")

app = FastMCP("cross-market-mcp")

_FRED_API_KEY = os.getenv("FRED_API_KEY", "")


def _fred_client():
    """Return a Fred client, or None if API key is missing.

    返回 FRED API 客户端，若未配置 FRED_API_KEY 则返回 None。
    """
    if not _FRED_API_KEY:
        return None
    from fredapi import Fred
    return Fred(api_key=_FRED_API_KEY)


# ─────────────────────────────────────────────
# FRED Tool 1: US Treasury Yields
# ─────────────────────────────────────────────
@app.tool()
async def get_us_treasury_yields(start_date: str = "2024-01-01", end_date: str = "") -> str:
    """Fetch US Treasury yield series: 2Y (DGS2), 10Y (DGS10), and 10Y-2Y spread (T10Y2Y).

    获取美国国债收益率时间序列：2年期、10年期及期限利差。
    期限利差（T10Y2Y）是美股/全球风险资产的重要领先指标，也影响北向资金流向A股。

    Args:
        start_date: Start date in YYYY-MM-DD format (default: 2024-01-01).
                    开始日期，格式 YYYY-MM-DD。
        end_date: End date in YYYY-MM-DD format (default: today).
                  结束日期，默认今日。
    """
    fred = _fred_client()
    if fred is None:
        return json.dumps({"error": "FRED_API_KEY not set. Get a free key at fred.stlouisfed.org"}, ensure_ascii=False)
    try:
        kwargs = {"observation_start": start_date}
        if end_date:
            kwargs["observation_end"] = end_date
        dgs2 = fred.get_series("DGS2", **kwargs)
        dgs10 = fred.get_series("DGS10", **kwargs)
        spread = fred.get_series("T10Y2Y", **kwargs)
        df = pd.DataFrame({"DGS2": dgs2, "DGS10": dgs10, "T10Y2Y": spread}).dropna(how="all")
        return json.dumps({
            "series": ["DGS2 (2Y yield)", "DGS10 (10Y yield)", "T10Y2Y (10Y-2Y spread)"],
            "unit": "percent",
            "data": df.tail(60).round(4).reset_index().rename(columns={"index": "date"}).assign(
                date=lambda x: x["date"].astype(str)
            ).to_dict(orient="records"),
        }, ensure_ascii=False)
    except Exception as e:
        logger.error("get_us_treasury_yields failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# FRED Tool 2: USD/CNY Exchange Rate
# ─────────────────────────────────────────────
@app.tool()
async def get_usd_cny_rate(start_date: str = "2024-01-01", end_date: str = "") -> str:
    """Fetch the daily USD/CNY exchange rate series (DEXCHUS) from FRED.

    获取美元/人民币每日汇率历史序列（DEXCHUS）。
    人民币汇率是 A 股的核心宏观变量：贬值压力下北向资金往往流出，升值则反之。

    Args:
        start_date: Start date in YYYY-MM-DD format. / 开始日期。
        end_date: End date in YYYY-MM-DD format (default: today). / 结束日期，默认今日。
    """
    fred = _fred_client()
    if fred is None:
        return json.dumps({"error": "FRED_API_KEY not set"}, ensure_ascii=False)
    try:
        kwargs = {"observation_start": start_date}
        if end_date:
            kwargs["observation_end"] = end_date
        series = fred.get_series("DEXCHUS", **kwargs)
        df = series.dropna().reset_index()
        df.columns = ["date", "usd_cny"]
        df["date"] = df["date"].astype(str)
        return json.dumps({
            "series": "DEXCHUS (USD/CNY daily rate)",
            "unit": "CNY per USD",
            "data": df.tail(120).round(4).to_dict(orient="records"),
        }, ensure_ascii=False)
    except Exception as e:
        logger.error("get_usd_cny_rate failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# FRED Tool 3: Global Risk Indicators
# ─────────────────────────────────────────────
@app.tool()
async def get_global_risk_indicators(start_date: str = "2024-01-01", end_date: str = "") -> str:
    """Fetch VIX (VIXCLS) and US High-Yield credit spread (BAMLH0A0HYM2) from FRED.

    获取 VIX 恐慌指数和美国高收益债信用利差。
    VIX > 25 通常触发全球 risk-off，A 股外资流出加速；信用利差扩大是流动性收紧的先行信号。

    Args:
        start_date: Start date in YYYY-MM-DD format. / 开始日期。
        end_date: End date in YYYY-MM-DD format (default: today). / 结束日期，默认今日。
    """
    fred = _fred_client()
    if fred is None:
        return json.dumps({"error": "FRED_API_KEY not set"}, ensure_ascii=False)
    try:
        kwargs = {"observation_start": start_date}
        if end_date:
            kwargs["observation_end"] = end_date
        vix = fred.get_series("VIXCLS", **kwargs)
        hy_spread = fred.get_series("BAMLH0A0HYM2", **kwargs)
        df = pd.DataFrame({"VIX": vix, "HY_spread": hy_spread}).dropna(how="all")
        return json.dumps({
            "series": ["VIX (CBOE Volatility Index)", "HY_spread (US HY OAS, bps)"],
            "note": "VIX>25 = elevated risk-off; HY_spread widening = liquidity stress",
            "data": df.tail(60).round(2).reset_index().rename(columns={"index": "date"}).assign(
                date=lambda x: x["date"].astype(str)
            ).to_dict(orient="records"),
        }, ensure_ascii=False)
    except Exception as e:
        logger.error("get_global_risk_indicators failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# yfinance Tool 4: Global Equity Indices
# ─────────────────────────────────────────────
@app.tool()
async def get_global_equity_indices(period: str = "1mo") -> str:
    """Fetch OHLCV data for S&P 500 (^GSPC), Hang Seng (^HSI), and Nasdaq (^IXIC).

    获取标普500、恒生指数、纳斯达克指数的历史行情。
    港股与 A 股共享北向资金通道，港股走势对 A 股有较强的传导效应。

    Args:
        period: Time period string (1d, 5d, 1mo, 3mo, 6mo, 1y). Default: 1mo.
                时间周期，如 1mo = 最近一个月。
    """
    try:
        import yfinance as yf
        tickers = {"SP500": "^GSPC", "HangSeng": "^HSI", "Nasdaq": "^IXIC"}
        result = {}
        for name, symbol in tickers.items():
            hist = yf.Ticker(symbol).history(period=period)
            if hist.empty:
                result[name] = {"error": "no data"}
                continue
            idx = pd.to_datetime(hist.index).strftime("%Y-%m-%d")
            hist = hist.copy()
            hist.index = idx
            result[name] = {
                "symbol": symbol,
                "latest_close": round(float(hist["Close"].iloc[-1]), 2),
                "change_pct_5d": round(float((hist["Close"].iloc[-1] / hist["Close"].iloc[-5] - 1) * 100), 2) if len(hist) >= 5 else None,
                "data": hist["Close"].round(2).to_dict(),
            }
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        logger.error("get_global_equity_indices failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# yfinance Tool 5: Commodity Prices
# ─────────────────────────────────────────────
@app.tool()
async def get_commodity_prices(period: str = "1mo") -> str:
    """Fetch futures prices for WTI Crude (CL=F), Gold (GC=F), and Copper (HG=F).

    获取原油、黄金、铜期货价格。
    铜价是全球工业需求的领先指标，与 A 股周期股高度相关；原油影响通胀预期和能源板块。

    Args:
        period: Time period string (1d, 5d, 1mo, 3mo, 6mo, 1y). Default: 1mo.
                时间周期。
    """
    try:
        import yfinance as yf
        tickers = {"WTI_Crude": "CL=F", "Gold": "GC=F", "Copper": "HG=F"}
        result = {}
        for name, symbol in tickers.items():
            hist = yf.Ticker(symbol).history(period=period)
            if hist.empty:
                result[name] = {"error": "no data"}
                continue
            hist = hist.copy(); hist.index = pd.to_datetime(hist.index).strftime("%Y-%m-%d")
            result[name] = {
                "symbol": symbol,
                "latest_close": round(float(hist["Close"].iloc[-1]), 4),
                "change_pct_5d": round(float((hist["Close"].iloc[-1] / hist["Close"].iloc[-5] - 1) * 100), 2) if len(hist) >= 5 else None,
                "data": hist["Close"].round(4).to_dict(),
            }
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        logger.error("get_commodity_prices failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# yfinance Tool 6: USD Index
# ─────────────────────────────────────────────
@app.tool()
async def get_usd_index(period: str = "1mo") -> str:
    """Fetch the DXY US Dollar Index (DX-Y.NYB) via yfinance.

    获取美元指数（DXY）走势。美元指数走强通常伴随新兴市场资本外流，压制 A 股外资流入。

    Args:
        period: Time period string (1d, 5d, 1mo, 3mo, 6mo, 1y). Default: 1mo.
                时间周期。
    """
    try:
        import yfinance as yf
        hist = yf.Ticker("DX-Y.NYB").history(period=period)
        if hist.empty:
            return json.dumps({"error": "No DXY data returned"}, ensure_ascii=False)
        hist = hist.copy(); hist.index = pd.to_datetime(hist.index).strftime("%Y-%m-%d")
        return json.dumps({
            "symbol": "DX-Y.NYB (DXY US Dollar Index)",
            "latest_close": round(float(hist["Close"].iloc[-1]), 2),
            "change_pct_5d": round(float((hist["Close"].iloc[-1] / hist["Close"].iloc[-5] - 1) * 100), 2) if len(hist) >= 5 else None,
            "data": hist["Close"].round(2).to_dict(),
        }, ensure_ascii=False)
    except Exception as e:
        logger.error("get_usd_index failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# yfinance Tool 7: Cross-Market Snapshot
# ─────────────────────────────────────────────
@app.tool()
async def get_cross_market_snapshot() -> str:
    """Fetch a unified latest-price snapshot across all tracked cross-market assets.

    获取所有跨市场资产的最新快照：全球股指、大宗商品、美元指数、VIX 估算。
    用于 Stage 1 一次性获取完整的跨市场背景，无需多次调用。
    """
    try:
        import yfinance as yf
        symbols = {
            "SP500": "^GSPC",
            "Nasdaq": "^IXIC",
            "HangSeng": "^HSI",
            "VIX": "^VIX",
            "DXY": "DX-Y.NYB",
            "WTI_Crude": "CL=F",
            "Gold": "GC=F",
            "Copper": "HG=F",
            "US10Y": "^TNX",
        }
        result = {}
        for name, symbol in symbols.items():
            try:
                hist = yf.Ticker(symbol).history(period="5d")
                if hist.empty:
                    result[name] = {"symbol": symbol, "error": "no data"}
                    continue
                latest = float(hist["Close"].iloc[-1])
                prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else latest
                result[name] = {
                    "symbol": symbol,
                    "latest_close": round(latest, 4),
                    "change_pct_1d": round((latest / prev - 1) * 100, 2),
                }
            except Exception as inner_e:
                result[name] = {"symbol": symbol, "error": str(inner_e)}
        return json.dumps({"snapshot": result}, ensure_ascii=False)
    except Exception as e:
        logger.error("get_cross_market_snapshot failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─────────────────────────────────────────────
# Jina Tool 8: Article Content Extraction
# ─────────────────────────────────────────────
@app.tool()
async def fetch_article_content(url: str) -> str:
    """Extract clean markdown content from any URL via the Jina Reader API.

    使用 Jina Reader 将任意 URL 转换为干净的 Markdown 文本，支持中英文页面。
    适用于 Stage 2 叙事挖掘：将 Tavily 搜索到的文章 URL 转为可读全文供 LLM 分析。

    Args:
        url: The URL of the article to extract. / 要提取内容的文章 URL。
    """
    jina_url = f"https://r.jina.ai/{url}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                jina_url,
                headers={"Accept": "text/plain", "User-Agent": "Pixiu-Research-Agent/2.0"},
            )
            resp.raise_for_status()
            text = resp.text
            # Truncate to ~8000 chars to avoid context overflow
            if len(text) > 8000:
                text = text[:8000] + "\n\n[... content truncated at 8000 chars ...]"
            return json.dumps({"url": url, "content": text, "length": len(text)}, ensure_ascii=False)
    except httpx.TimeoutException:
        return json.dumps({"error": "Request timed out (30s)", "url": url}, ensure_ascii=False)
    except Exception as e:
        logger.error("fetch_article_content failed for %s: %s", url, e)
        return json.dumps({"error": str(e), "url": url}, ensure_ascii=False)


if __name__ == "__main__":
    app.run()
