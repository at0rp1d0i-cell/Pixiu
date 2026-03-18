"""
Unit tests for cross_market_server MCP tools.
All network calls are mocked — no real API keys required.

跨市场 MCP 工具单元测试，全部网络调用已 mock，无需真实 API Key。
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

pytestmark = pytest.mark.unit


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_fred_series(values: dict) -> "pd.Series":
    idx = pd.to_datetime(list(values.keys()))
    return pd.Series(list(values.values()), index=idx)


def _make_yf_history(closes: list[float]) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=len(closes), freq="B")
    return pd.DataFrame({"Close": closes}, index=dates)


# ── FRED tools ────────────────────────────────────────────────────────────────

class TestGetUsTreasuryYields:
    @patch("mcp_servers.cross_market_server._FRED_API_KEY", "fake-key")
    @patch("mcp_servers.cross_market_server._fred_client")
    def test_returns_yield_data(self, mock_client_fn):
        mock_fred = MagicMock()
        series = _make_fred_series({"2024-01-02": 4.5, "2024-01-03": 4.6})
        mock_fred.get_series.return_value = series
        mock_client_fn.return_value = mock_fred

        import asyncio
        from mcp_servers.cross_market_server import get_us_treasury_yields
        result = json.loads(asyncio.run(get_us_treasury_yields("2024-01-01", "")))

        assert "data" in result
        assert "series" in result
        assert mock_fred.get_series.call_count == 3  # DGS2, DGS10, T10Y2Y

    def test_no_api_key_returns_error(self):
        import asyncio
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

        import asyncio
        from mcp_servers.cross_market_server import get_usd_cny_rate
        result = json.loads(asyncio.run(get_usd_cny_rate("2024-01-01", "")))

        assert "data" in result
        assert result["series"] == "DEXCHUS (USD/CNY daily rate)"

    def test_no_api_key_returns_error(self):
        import asyncio
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

        import asyncio
        from mcp_servers.cross_market_server import get_global_risk_indicators
        result = json.loads(asyncio.run(get_global_risk_indicators("2024-01-01", "")))

        assert "data" in result
        assert "VIX" in result["series"][0]


# ── yfinance tools ────────────────────────────────────────────────────────────

class TestGetGlobalEquityIndices:
    @patch("yfinance.Ticker")
    def test_returns_indices_data(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _make_yf_history([4800.0, 4820.0, 4810.0, 4830.0, 4850.0, 4870.0])
        mock_ticker_cls.return_value = mock_ticker

        import asyncio
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

        import asyncio
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

        import asyncio
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

        import asyncio
        from mcp_servers.cross_market_server import get_usd_index
        result = json.loads(asyncio.run(get_usd_index()))

        assert "latest_close" in result
        assert "change_pct_5d" in result

    @patch("yfinance.Ticker")
    def test_empty_returns_error(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        mock_ticker_cls.return_value = mock_ticker

        import asyncio
        from mcp_servers.cross_market_server import get_usd_index
        result = json.loads(asyncio.run(get_usd_index()))

        assert "error" in result


class TestGetCrossMarketSnapshot:
    @patch("yfinance.Ticker")
    def test_returns_all_assets(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _make_yf_history([100.0, 101.0])
        mock_ticker_cls.return_value = mock_ticker

        import asyncio
        from mcp_servers.cross_market_server import get_cross_market_snapshot
        result = json.loads(asyncio.run(get_cross_market_snapshot()))

        assert "snapshot" in result
        snapshot = result["snapshot"]
        assert "SP500" in snapshot
        assert "VIX" in snapshot
        assert "DXY" in snapshot
        assert "Gold" in snapshot


# ── Jina Reader ───────────────────────────────────────────────────────────────

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
