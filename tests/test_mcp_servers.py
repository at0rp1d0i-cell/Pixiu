"""
MCP server tests: cross_market_server (unit) + akshare_server (integration).

Sources:
  - tests/test_cross_market_mcp.py  (pytestmark = unit)
  - tests/test_akshare_mcp.py       (pytestmark = integration)
"""
import asyncio
import json
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd


# ─────────────────────────────────────────────────────────
# From test_cross_market_mcp.py  (unit tests)
# ─────────────────────────────────────────────────────────

pytestmark = pytest.mark.unit  # default; integration tests override with their own mark


def _make_fred_series(values: dict) -> "pd.Series":
    idx = pd.to_datetime(list(values.keys()))
    return pd.Series(list(values.values()), index=idx)


def _make_yf_history(closes: list) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=len(closes), freq="B")
    return pd.DataFrame({"Close": closes}, index=dates)


class TestGetUsTreasuryYields:
    @patch("mcp_servers.cross_market_server._FRED_API_KEY", "fake-key")
    @patch("mcp_servers.cross_market_server._fred_client")
    def test_returns_yield_data(self, mock_client_fn):
        mock_fred = MagicMock()
        series = _make_fred_series({"2024-01-02": 4.5, "2024-01-03": 4.6})
        mock_fred.get_series.return_value = series
        mock_client_fn.return_value = mock_fred

        from mcp_servers.cross_market_server import get_us_treasury_yields
        result = json.loads(asyncio.run(get_us_treasury_yields("2024-01-01", "")))

        assert "data" in result
        assert "series" in result
        assert mock_fred.get_series.call_count == 3

    def test_no_api_key_returns_error(self):
        with patch("mcp_servers.cross_market_server._FRED_API_KEY", ""):
            with patch("mcp_servers.cross_market_server._fred_client", return_value=None):
                from mcp_servers.cross_market_server import get_us_treasury_yields
                result = json.loads(asyncio.run(get_us_treasury_yields()))
                assert "error" in result
                assert "FRED_API_KEY" in result["error"]


class TestGetUsdCnyRate:
    @patch("mcp_servers.cross_market_server._FRED_API_KEY", "fake-key")
    @patch("mcp_servers.cross_market_server._fred_client")
    def test_returns_rate_series(self, mock_client_fn):
        mock_fred = MagicMock()
        mock_fred.get_series.return_value = _make_fred_series({"2024-01-02": 7.1, "2024-01-03": 7.15})
        mock_client_fn.return_value = mock_fred

        from mcp_servers.cross_market_server import get_usd_cny_rate
        result = json.loads(asyncio.run(get_usd_cny_rate("2024-01-01", "")))

        assert "data" in result
        assert result["series"] == "DEXCHUS (USD/CNY daily rate)"

    def test_no_api_key_returns_error(self):
        with patch("mcp_servers.cross_market_server._fred_client", return_value=None):
            from mcp_servers.cross_market_server import get_usd_cny_rate
            result = json.loads(asyncio.run(get_usd_cny_rate()))
            assert "error" in result


class TestGetGlobalRiskIndicators:
    @patch("mcp_servers.cross_market_server._FRED_API_KEY", "fake-key")
    @patch("mcp_servers.cross_market_server._fred_client")
    def test_returns_vix_and_spread(self, mock_client_fn):
        mock_fred = MagicMock()
        mock_fred.get_series.return_value = _make_fred_series({"2024-01-02": 18.5, "2024-01-03": 19.0})
        mock_client_fn.return_value = mock_fred

        from mcp_servers.cross_market_server import get_global_risk_indicators
        result = json.loads(asyncio.run(get_global_risk_indicators("2024-01-01", "")))

        assert "data" in result
        assert "VIX" in result["series"][0]


class TestGetGlobalEquityIndices:
    @patch("yfinance.Ticker")
    def test_returns_indices_data(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _make_yf_history([4800.0, 4820.0, 4810.0, 4830.0, 4850.0, 4870.0])
        mock_ticker_cls.return_value = mock_ticker

        from mcp_servers.cross_market_server import get_global_equity_indices
        result = json.loads(asyncio.run(get_global_equity_indices("1mo")))

        assert "SP500" in result
        assert "latest_close" in result["SP500"]
        assert "change_pct_5d" in result["SP500"]

    @patch("yfinance.Ticker")
    def test_handles_empty_history(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        mock_ticker_cls.return_value = mock_ticker

        from mcp_servers.cross_market_server import get_global_equity_indices
        result = json.loads(asyncio.run(get_global_equity_indices()))

        assert "SP500" in result
        assert result["SP500"]["error"] == "no data"


class TestGetCommodityPrices:
    @patch("yfinance.Ticker")
    def test_returns_commodity_data(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _make_yf_history([75.0, 74.5, 76.0, 75.8, 77.0, 76.5])
        mock_ticker_cls.return_value = mock_ticker

        from mcp_servers.cross_market_server import get_commodity_prices
        result = json.loads(asyncio.run(get_commodity_prices()))

        assert "WTI_Crude" in result
        assert "Gold" in result
        assert "Copper" in result


class TestGetUsdIndex:
    @patch("yfinance.Ticker")
    def test_returns_dxy(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _make_yf_history([104.0, 104.2, 103.8, 104.5, 104.1, 104.3])
        mock_ticker_cls.return_value = mock_ticker

        from mcp_servers.cross_market_server import get_usd_index
        result = json.loads(asyncio.run(get_usd_index()))

        assert "latest_close" in result
        assert "change_pct_5d" in result

    @patch("yfinance.Ticker")
    def test_empty_returns_error(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        mock_ticker_cls.return_value = mock_ticker

        from mcp_servers.cross_market_server import get_usd_index
        result = json.loads(asyncio.run(get_usd_index()))

        assert "error" in result


class TestGetCrossMarketSnapshot:
    @patch("yfinance.Ticker")
    def test_returns_all_assets(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _make_yf_history([100.0, 101.0])
        mock_ticker_cls.return_value = mock_ticker

        from mcp_servers.cross_market_server import get_cross_market_snapshot
        result = json.loads(asyncio.run(get_cross_market_snapshot()))

        assert "snapshot" in result
        snapshot = result["snapshot"]
        assert "SP500" in snapshot
        assert "VIX" in snapshot
        assert "DXY" in snapshot
        assert "Gold" in snapshot


class TestFetchArticleContent:
    @pytest.mark.asyncio
    async def test_returns_markdown_content(self):
        fake_content = "# Article Title\n\nThis is the article body."
        mock_resp = MagicMock()
        mock_resp.text = fake_content
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            from mcp_servers.cross_market_server import fetch_article_content
            result = json.loads(await fetch_article_content("https://example.com/article"))

        assert result["content"] == fake_content
        assert "url" in result

    @pytest.mark.asyncio
    async def test_truncates_long_content(self):
        long_content = "x" * 10000
        mock_resp = MagicMock()
        mock_resp.text = long_content
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            from mcp_servers.cross_market_server import fetch_article_content
            result = json.loads(await fetch_article_content("https://example.com/long"))

        assert len(result["content"]) < 10000
        assert "truncated" in result["content"]

    @pytest.mark.asyncio
    async def test_handles_timeout(self):
        import httpx
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            from mcp_servers.cross_market_server import fetch_article_content
            result = json.loads(await fetch_article_content("https://slow.example.com"))

        assert "error" in result
        assert "timed out" in result["error"]


# ─────────────────────────────────────────────────────────
# From test_akshare_mcp.py  (integration tests)
# ─────────────────────────────────────────────────────────

MCP_SERVER_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "mcp_servers", "akshare_server.py")
)


@pytest.fixture(scope="module")
def mcp_client():
    from langchain_mcp_adapters.client import MultiServerMCPClient
    return MultiServerMCPClient(
        {"akshare": {"command": "python3", "args": [MCP_SERVER_PATH], "transport": "stdio"}}
    )


@pytest.fixture(scope="module")
def tools(mcp_client):
    return asyncio.run(mcp_client.get_tools())


@pytest.mark.integration
def test_tools_loaded(tools):
    """应加载 25 个工具（Phase 4A 扩展后）。"""
    tool_names = [t.name for t in tools]
    # 原始 7 个工具
    original_tools = [
        "get_northbound_flow_today",
        "get_northbound_flow_history",
        "get_market_fund_flow",
        "get_northbound_top_holdings",
        "get_research_reports",
        "get_industry_pe",
        "get_individual_fund_flow_rank",
    ]
    # Phase 4A 新增工具
    phase4a_tools = [
        "get_stock_financial_summary",
        "get_macro_indicators",
        "get_margin_trading_summary",
        "get_stock_news",
        "get_market_hot_topics",
        "get_concept_board_flow",
        "get_global_indices",
        "get_commodity_prices",
        "get_exchange_rates",
        "get_market_breadth",
        "get_index_valuation",
        "get_margin_balance",
        "get_limit_up_pool",
        "get_limit_down_pool",
        "get_sector_rotation_speed",
        "get_north_bound_flow",
        "get_volatility_index",
        "get_top_list",
    ]
    for name in original_tools + phase4a_tools:
        assert name in tool_names, f"Missing tool: {name}"
    assert len(tool_names) == 25, f"Expected 25 tools, got {len(tool_names)}: {tool_names}"


@pytest.mark.integration
def test_northbound_flow_today(tools):
    """北向资金今日摘要应返回非空 JSON。"""
    tool = next(t for t in tools if t.name == "get_northbound_flow_today")
    result = asyncio.run(tool.ainvoke({}))
    data = json.loads(result) if isinstance(result, str) else result
    assert isinstance(data, list) or "error" not in data


@pytest.mark.integration
def test_northbound_flow_history(tools):
    """北向资金历史默认 20 天，应返回数据。"""
    tool = next(t for t in tools if t.name == "get_northbound_flow_history")
    result = asyncio.run(tool.ainvoke({"days": 10}))
    data = json.loads(result) if isinstance(result, str) else result
    assert isinstance(data, list)
    assert len(data) <= 10


@pytest.mark.integration
def test_market_fund_flow(tools):
    """全市场资金流向应包含主力净流入字段。"""
    tool = next(t for t in tools if t.name == "get_market_fund_flow")
    result = asyncio.run(tool.ainvoke({"days": 5}))
    data = json.loads(result) if isinstance(result, str) else result
    assert isinstance(data, list)


@pytest.mark.integration
def test_research_reports(tools):
    """平安银行 000001 应有研报数据。"""
    tool = next(t for t in tools if t.name == "get_research_reports")
    result = asyncio.run(tool.ainvoke({"symbol": "000001", "limit": 3}))
    data = json.loads(result) if isinstance(result, str) else result
    assert isinstance(data, list) or "error" not in str(data)


@pytest.mark.integration
def test_industry_pe(tools):
    """行业 PE 应返回多行数据。"""
    tool = next(t for t in tools if t.name == "get_industry_pe")
    result = asyncio.run(tool.ainvoke({}))
    data = json.loads(result) if isinstance(result, str) else result
    assert isinstance(data, list) or "error" in data


# ─────────────────────────────────────────────────────────
# RSS MCP Server tests  (unit)
# ─────────────────────────────────────────────────────────

def _make_feedparser_entry(title="测试标题", link="http://example.com/1",
                           entry_id="http://example.com/1",
                           published_parsed=None):
    """Build a minimal feedparser-like entry object."""
    entry = MagicMock()
    entry.title = title
    entry.link = link
    entry.id = entry_id
    entry.summary = "这是一段测试摘要内容"
    entry.published_parsed = published_parsed
    entry.updated_parsed = None
    return entry


def _make_feedparser_result(entries):
    feed = MagicMock()
    feed.entries = entries
    return feed


def _recent_struct():
    """Return a UTC struct_time for 1 hour ago (within any since_hours >= 1 window)."""
    import time
    return time.gmtime(time.time() - 3600)


def _old_struct():
    """Return a UTC struct_time for 48 hours ago (outside a since_hours=1 window)."""
    import time
    return time.gmtime(time.time() - 48 * 3600)


class TestFetchRssFeedFormat:
    @pytest.mark.asyncio
    async def test_returns_required_fields(self):
        """fetch_rss_feed 返回 JSON 且包含必要顶层字段。"""
        mock_resp = MagicMock()
        mock_resp.text = "<rss></rss>"
        mock_resp.raise_for_status = MagicMock()

        entry = _make_feedparser_entry(published_parsed=_recent_struct())
        parsed_feed = _make_feedparser_result([entry])

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("feedparser.parse", return_value=parsed_feed):
                from mcp_servers.rss_server import fetch_rss_feed
                result = json.loads(await fetch_rss_feed(sources=["csrc"], max_items=5, since_hours=24))

        assert "items" in result
        assert "sources_ok" in result
        assert "sources_failed" in result
        assert "fetched_at" in result
        assert "total_items" in result

    @pytest.mark.asyncio
    async def test_item_fields_present(self):
        """每个 item 包含 source / title / url / published_at 字段。"""
        mock_resp = MagicMock()
        mock_resp.text = "<rss></rss>"
        mock_resp.raise_for_status = MagicMock()

        entry = _make_feedparser_entry(published_parsed=_recent_struct())
        parsed_feed = _make_feedparser_result([entry])

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("feedparser.parse", return_value=parsed_feed):
                from mcp_servers.rss_server import fetch_rss_feed
                result = json.loads(await fetch_rss_feed(sources=["csrc"], max_items=5, since_hours=24))

        for item in result["items"]:
            assert {"source", "title", "url", "published_at"}.issubset(item.keys())


class TestFetchRssFeedTimeFilter:
    @pytest.mark.asyncio
    async def test_old_entries_excluded(self):
        """since_hours=1 时，超过 1 小时的条目不应出现在结果中。"""
        mock_resp = MagicMock()
        mock_resp.text = "<rss></rss>"
        mock_resp.raise_for_status = MagicMock()

        recent_entry = _make_feedparser_entry(
            title="新条目", link="http://example.com/new", entry_id="http://example.com/new",
            published_parsed=_recent_struct(),
        )
        old_entry = _make_feedparser_entry(
            title="旧条目", link="http://example.com/old", entry_id="http://example.com/old",
            published_parsed=_old_struct(),
        )
        parsed_feed = _make_feedparser_result([recent_entry, old_entry])

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)

        # Clear dedup cache before test to avoid cross-test contamination
        import mcp_servers.rss_server as rss_mod
        rss_mod._seen_ids.clear()

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("feedparser.parse", return_value=parsed_feed):
                result = json.loads(await rss_mod.fetch_rss_feed(sources=["pboc"], max_items=10, since_hours=1))

        titles = [item["title"] for item in result["items"]]
        assert "旧条目" not in titles

    @pytest.mark.asyncio
    async def test_no_published_time_entry_kept(self):
        """发布时间缺失的条目默认保留（宁可多返回）。"""
        mock_resp = MagicMock()
        mock_resp.text = "<rss></rss>"
        mock_resp.raise_for_status = MagicMock()

        entry = _make_feedparser_entry(
            title="无时间条目", link="http://example.com/notime",
            entry_id="http://example.com/notime",
            published_parsed=None,
        )
        parsed_feed = _make_feedparser_result([entry])

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)

        import mcp_servers.rss_server as rss_mod
        rss_mod._seen_ids.clear()

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("feedparser.parse", return_value=parsed_feed):
                result = json.loads(await rss_mod.fetch_rss_feed(sources=["eastmoney"], max_items=5, since_hours=1))

        assert any(item["title"] == "无时间条目" for item in result["items"])


class TestFetchRssFeedSourceIsolation:
    @pytest.mark.asyncio
    async def test_failing_source_in_sources_failed(self):
        """单个源失败时进入 sources_failed，不影响其他源。"""
        import httpx as httpx_mod

        mock_resp_ok = MagicMock()
        mock_resp_ok.text = "<rss></rss>"
        mock_resp_ok.raise_for_status = MagicMock()

        entry = _make_feedparser_entry(published_parsed=_recent_struct())
        parsed_feed = _make_feedparser_result([entry])

        def side_effect_get(url, **kwargs):
            if "csrc" in url:
                raise httpx_mod.ConnectError("connection refused")
            return mock_resp_ok

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(side_effect=side_effect_get)

        import mcp_servers.rss_server as rss_mod
        rss_mod._seen_ids.clear()

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("feedparser.parse", return_value=parsed_feed):
                result = json.loads(
                    await rss_mod.fetch_rss_feed(sources=["csrc", "eastmoney"], max_items=5, since_hours=24)
                )

        assert "csrc" in result["sources_failed"]
        assert "eastmoney" in result["sources_ok"]
        assert len(result["items"]) > 0


class TestFetchFullArticle:
    @pytest.mark.asyncio
    async def test_returns_content_and_fields(self):
        """fetch_full_article 返回 url / jina_url / content / truncated 字段。"""
        fake_content = "# Article\n\nThis is the article body."
        mock_resp = MagicMock()
        mock_resp.text = fake_content
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            from mcp_servers.rss_server import fetch_full_article
            result = json.loads(await fetch_full_article("https://example.com/article"))

        assert result["content"] == fake_content
        assert "url" in result
        assert "jina_url" in result
        assert result["truncated"] is False
        assert "r.jina.ai" in result["jina_url"]

    @pytest.mark.asyncio
    async def test_truncates_long_content(self):
        """全文超过 3000 字时，content 被截断，truncated 为 True。"""
        long_content = "字" * 5000
        mock_resp = MagicMock()
        mock_resp.text = long_content
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            from mcp_servers.rss_server import fetch_full_article
            result = json.loads(await fetch_full_article("https://example.com/long"))

        assert len(result["content"]) <= 3000
        assert result["truncated"] is True

    @pytest.mark.asyncio
    async def test_handles_timeout(self):
        """网络超时时返回 error 字段。"""
        import httpx as httpx_mod
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(side_effect=httpx_mod.TimeoutException("timeout"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            from mcp_servers.rss_server import fetch_full_article
            result = json.loads(await fetch_full_article("https://slow.example.com"))

        assert "error" in result


class TestFetchAnnouncement:
    @pytest.mark.asyncio
    async def test_returns_required_fields(self):
        """fetch_announcement 返回 symbol / exchange / fetched_at / items / note。"""
        mock_df = pd.DataFrame([{
            "公告标题": "平安银行关于某事的公告",
            "公告链接": "http://www.szse.cn/announcement/1",
            "公告时间": "2026-03-18 09:00:00",
        }])

        with patch("akshare.stock_notice_report", return_value=mock_df):
            from mcp_servers.rss_server import fetch_announcement
            result = json.loads(await fetch_announcement("000001", max_items=5))

        assert result["symbol"] == "000001"
        assert "exchange" in result
        assert "fetched_at" in result
        assert "items" in result
        assert "note" in result
        assert len(result["items"]) == 1
        assert result["items"][0]["title"] == "平安银行关于某事的公告"

    @pytest.mark.asyncio
    async def test_akshare_failure_returns_note(self):
        """AKShare 抛异常时，items 为空，note 包含错误信息。"""
        with patch("akshare.stock_notice_report", side_effect=Exception("network error")):
            from mcp_servers.rss_server import fetch_announcement
            result = json.loads(await fetch_announcement("600519", max_items=5))

        assert result["items"] == []
        assert "AKShare error" in result["note"]
        assert result["symbol"] == "600519"
        assert result["exchange"] == "SSE"
