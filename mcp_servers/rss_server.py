"""
RSS MCP Server — RSS/Announcement/Article tools for A-share market context.
Provides real-time regulatory, policy, and financial news for Stage 1 MarketAnalyst.

Tools:
  - fetch_rss_feed:       Pull latest entries from configured A-share news sources
  - fetch_announcement:   Fetch stock-specific announcements via AKShare
  - fetch_full_article:   Extract full article text via Jina Reader (r.jina.ai)

Start: python mcp_servers/rss_server.py

数据分层：RSS/新闻属于 Layer 4（Agent 上下文），仅注入 LLM prompt，
不进入回测公式，不写入 Factor Pool。
"""

import json
import logging
import time
from datetime import datetime, timezone, timedelta

import feedparser
import httpx
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("rss-mcp")

app = FastMCP("rss-mcp")

# ─────────────────────────────────────────────────────────
# Data source registry
# ─────────────────────────────────────────────────────────

# parser types: "rss" = standard feedparser, "json_sina" = Sina JSON Roll API
SOURCE_MAP: dict[str, dict] = {
    "sse": {
        "url": "http://www.sse.com.cn/disclosure/listedinfo/announcement/rss.xml",
        "parser": "rss",
        "name": "上交所",
        # TODO: verify — may require mainland CN network access or have anti-crawl restrictions
    },
    "szse": {
        "url": "http://www.szse.cn/api/disc/info/discInfoRss.xml",
        "parser": "rss",
        "name": "深交所",
        # TODO: verify — may require mainland CN network access or have anti-crawl restrictions
    },
    "csrc": {
        "url": "http://www.csrc.gov.cn/csrc/c101954/rss.xml",
        "parser": "rss",
        "name": "证监会",
        # TODO: verify — CSRC URL may have changed after site redesign
    },
    "pboc": {
        "url": "http://www.pbc.gov.cn/rss/index.xml",
        "parser": "rss",
        "name": "中国人民银行",
        # TODO: verify — PBOC URL may have changed after site redesign
    },
    "sina": {
        "url": "https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2516&k=&num=50&page=1",
        "parser": "json_sina",
        "name": "新浪财经",
        # Sina RSS shut down in 2023; this uses the JSON Roll API as equivalent replacement
    },
    "eastmoney": {
        "url": "https://rss.eastmoney.com/rss/news/2.xml",
        "parser": "rss",
        "name": "东方财富",
        # TODO: verify — check if URL is still active
    },
}

# In-process dedup cache: maps entry id → True to suppress duplicates within a process lifetime
_seen_ids: set[str] = set()

# China Standard Time offset
_CST = timezone(timedelta(hours=8))


# ─────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────

def _now_cst() -> datetime:
    return datetime.now(_CST)


def _struct_to_datetime(t) -> datetime | None:
    """Convert a feedparser struct_time (UTC) to a timezone-aware datetime."""
    if t is None:
        return None
    try:
        ts = time.mktime(t)  # struct_time → epoch (local-tz naive, but feedparser gives UTC)
        # feedparser returns UTC struct_time; calendar.timegm is the correct conversion
        import calendar
        ts = calendar.timegm(t)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except Exception:
        return None


def _entry_published(entry) -> datetime | None:
    """Extract publish time from a feedparser entry. Falls back to updated_parsed."""
    dt = _struct_to_datetime(getattr(entry, "published_parsed", None))
    if dt is None:
        dt = _struct_to_datetime(getattr(entry, "updated_parsed", None))
    return dt


def _entry_id(entry) -> str:
    """Return a stable dedup key for an entry."""
    return getattr(entry, "id", None) or getattr(entry, "link", "") or getattr(entry, "title", "")


def _fmt_dt(dt: datetime | None) -> str:
    """Format datetime to ISO-8601 string in CST. Returns empty string if None."""
    if dt is None:
        return ""
    return dt.astimezone(_CST).isoformat()


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


# ─────────────────────────────────────────────────────────
# RSS feed fetcher (internal, not a tool)
# ─────────────────────────────────────────────────────────

async def _fetch_one_source(
    source_id: str,
    config: dict,
    max_items: int,
    since_hours: int,
    client: httpx.AsyncClient,
) -> tuple[list[dict], str | None]:
    """Fetch one source. Returns (items, error_msg). error_msg is None on success."""
    cutoff = _now_cst() - timedelta(hours=since_hours)
    items: list[dict] = []

    try:
        resp = await client.get(config["url"], timeout=10.0)
        resp.raise_for_status()

        if config.get("parser") == "json_sina":
            # Sina JSON Roll API: {"result": {"data": [...]}}
            payload = resp.json()
            raw_items = payload.get("result", {}).get("data", [])
            count = 0
            for item in raw_items:
                if count >= max_items:
                    break
                entry_id = item.get("url", "") or item.get("title", "")
                if entry_id in _seen_ids:
                    continue

                # Parse ctime (Unix timestamp string or int)
                published_dt: datetime | None = None
                ctime = item.get("ctime")
                if ctime:
                    try:
                        published_dt = datetime.fromtimestamp(int(ctime), tz=timezone.utc)
                    except Exception:
                        pass

                # Time filter: if we have a datetime and it's outside window, skip
                if published_dt is not None and published_dt.astimezone(_CST) < cutoff:
                    continue

                _seen_ids.add(entry_id)
                items.append({
                    "source": source_id,
                    "title": item.get("title", ""),
                    "summary": _truncate(item.get("intro", ""), 500),
                    "url": item.get("url", ""),
                    "published_at": _fmt_dt(published_dt),
                })
                count += 1

        else:
            # Standard RSS/Atom via feedparser
            feed = feedparser.parse(resp.text)
            count = 0
            for entry in feed.entries:
                if count >= max_items:
                    break
                entry_id = _entry_id(entry)
                if entry_id in _seen_ids:
                    continue

                published_dt = _entry_published(entry)

                # Time filter: keep if no datetime (richer coverage), skip if outside window
                if published_dt is not None and published_dt.astimezone(_CST) < cutoff:
                    continue

                _seen_ids.add(entry_id)
                summary = getattr(entry, "summary", "") or ""
                items.append({
                    "source": source_id,
                    "title": getattr(entry, "title", ""),
                    "summary": _truncate(summary, 500),
                    "url": getattr(entry, "link", ""),
                    "published_at": _fmt_dt(published_dt),
                })
                count += 1

    except Exception as e:
        logger.warning("[rss-mcp] Source '%s' failed: %s", source_id, e)
        return [], str(e)

    return items, None


# ─────────────────────────────────────────────────────────
# Tool 1: fetch_rss_feed
# ─────────────────────────────────────────────────────────

@app.tool()
async def fetch_rss_feed(
    sources: list[str] | None = None,
    max_items: int = 20,
    since_hours: int = 24,
) -> str:
    """获取 A 股主要信息源的最新条目。

    从配置的数据源（证监会、央行、新浪财经、东方财富等）拉取最新新闻和公告。
    每条包含：标题、摘要（截断至500字）、链接、发布时间、来源ID。
    单个 feed 失败不影响其他 feed，降级返回已成功获取的条目。

    数据来源 ID：sse（上交所）、szse（深交所）、csrc（证监会）、
                pboc（央行）、sina（新浪财经）、eastmoney（东方财富）

    Args:
        sources: 指定来源 ID 子集，如 ["csrc", "pboc"]。None 表示全部来源。
        max_items: 每个源最多返回条目数（默认 20）。
        since_hours: 只返回最近 N 小时的条目（默认 24）。
    """
    target_sources = sources if sources is not None else list(SOURCE_MAP.keys())
    # Filter to known sources only
    target_sources = [s for s in target_sources if s in SOURCE_MAP]

    all_items: list[dict] = []
    sources_ok: list[str] = []
    sources_failed: list[str] = []

    async with httpx.AsyncClient(
        headers={"User-Agent": "Pixiu-Research-Agent/2.0"},
        follow_redirects=True,
    ) as client:
        for source_id in target_sources:
            items, err = await _fetch_one_source(
                source_id, SOURCE_MAP[source_id], max_items, since_hours, client
            )
            if err is not None:
                sources_failed.append(source_id)
            else:
                sources_ok.append(source_id)
                all_items.extend(items)

    return json.dumps({
        "fetched_at": _now_cst().isoformat(),
        "since_hours": since_hours,
        "total_items": len(all_items),
        "sources_ok": sources_ok,
        "sources_failed": sources_failed,
        "items": all_items,
    }, ensure_ascii=False)


# ─────────────────────────────────────────────────────────
# Tool 2: fetch_announcement
# ─────────────────────────────────────────────────────────

@app.tool()
async def fetch_announcement(
    symbol: str,
    max_items: int = 5,
) -> str:
    """获取指定股票的最新公告。

    使用 AKShare 的 stock_notice_report 接口按股票代码查询公告，
    而非 RSS 全量流过滤（交易所 RSS 不支持按股票代码过滤）。

    Args:
        symbol: 股票代码，6位数字，如 "000001"（平安银行）。
        max_items: 最多返回条目数（默认 5）。
    """
    fetched_at = _now_cst().isoformat()
    note = ""
    items: list[dict] = []

    # Determine exchange from code prefix
    exchange = "SZSE" if symbol.startswith(("0", "3")) else "SSE"

    try:
        import akshare as ak
        df = ak.stock_notice_report(symbol=symbol)
        if df is None or df.empty:
            note = "no announcements found"
        else:
            # Take the most recent max_items rows
            df = df.head(max_items)
            for _, row in df.iterrows():
                # Column names vary by akshare version; try common names
                title = str(row.get("公告标题", row.get("title", row.get("标题", ""))))
                url = str(row.get("公告链接", row.get("url", row.get("链接", ""))))
                pub_raw = row.get("公告时间", row.get("公告日期", row.get("date", "")))
                published_at = str(pub_raw) if pub_raw else ""
                items.append({
                    "title": title,
                    "url": url,
                    "published_at": published_at,
                })
    except Exception as e:
        logger.warning("[rss-mcp] fetch_announcement(%s) failed: %s", symbol, e)
        note = f"AKShare error: {e}"

    return json.dumps({
        "symbol": symbol,
        "exchange": exchange,
        "fetched_at": fetched_at,
        "items": items,
        "note": note,
    }, ensure_ascii=False)


# ─────────────────────────────────────────────────────────
# Tool 3: fetch_full_article
# ─────────────────────────────────────────────────────────

@app.tool()
async def fetch_full_article(url: str) -> str:
    """用 Jina Reader 抓取文章全文，用于 RSS 摘要不足时补全内容。

    通过 https://r.jina.ai/{url} 获取 Markdown 格式全文，截断至 3000 字。
    无需 API key。适合在 NARRATIVE_MINING 子空间中对高价值条目做深度阅读。

    Args:
        url: 要抓取全文的文章 URL。
    """
    jina_url = f"https://r.jina.ai/{url}"
    max_chars = 3000

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                jina_url,
                headers={"Accept": "text/plain", "User-Agent": "Pixiu-Research-Agent/2.0"},
                follow_redirects=True,
            )
            resp.raise_for_status()
            text = resp.text
            truncated = len(text) > max_chars
            if truncated:
                text = text[:max_chars]
            return json.dumps({
                "url": url,
                "jina_url": jina_url,
                "content": text,
                "truncated": truncated,
            }, ensure_ascii=False)
    except httpx.TimeoutException:
        return json.dumps({
            "error": "Request timed out (10s)",
            "url": url,
            "jina_url": jina_url,
        }, ensure_ascii=False)
    except Exception as e:
        logger.error("[rss-mcp] fetch_full_article failed for %s: %s", url, e)
        return json.dumps({
            "error": str(e),
            "url": url,
            "jina_url": jina_url,
        }, ensure_ascii=False)


if __name__ == "__main__":
    app.run()
