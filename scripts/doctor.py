#!/usr/bin/env python
"""
Pixiu System Doctor: Pre-flight Health Check
Run this script to verify the operational readiness of the pipeline.
"""

import asyncio
import os
import sqlite3
from datetime import datetime
from time import perf_counter

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

def check_data_layer():
    """Verify local Qlib data and features."""
    try:
        from src.formula.capabilities import get_runtime_formula_capabilities
        caps = get_runtime_formula_capabilities()
        fields_count = len(caps.available_fields)

        # 项目内 qlib_bin 目录
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        qlib_path = os.path.join(project_root, "data", "qlib_bin")
        if not os.path.exists(qlib_path):
            return False, f"Qlib bin dir not found: {qlib_path}"

        # 检查数据时效性：读取 calendars 最后日期
        cal_file = os.path.join(qlib_path, "calendars", "day.txt")
        freshness_msg = ""
        if os.path.exists(cal_file):
            with open(cal_file) as f:
                lines = f.read().strip().splitlines()
                if lines:
                    last_date = lines[-1].strip()
                    freshness_msg = f"，数据截止: {last_date}"

        instruments_path = os.path.join(qlib_path, "instruments")
        stock_count = len(os.listdir(instruments_path)) if os.path.exists(instruments_path) else 0
        features_path = os.path.join(qlib_path, "features")
        feature_dirs = len(os.listdir(features_path)) if os.path.exists(features_path) else 0

        return True, f"能力集 {fields_count} 字段，{feature_dirs} 只股票 Bin{freshness_msg}"
    except Exception as e:
        return False, str(e)


async def check_llm_layer():
    """Ping test to configured LLM."""
    try:
        from src.llm.openai_compat import build_researcher_llm
        from langchain_core.messages import HumanMessage
        llm = build_researcher_llm(profile="alignment_checker")

        start = perf_counter()
        resp = await asyncio.wait_for(
            llm.ainvoke([HumanMessage(content="Reply 'OK' only.")]),
            timeout=10.0
        )
        elapsed = perf_counter() - start

        model_name = getattr(llm, "model_name", "unknown")
        status = True
        warn = ""
        if elapsed > 3.0:
            warn = " (Latency High!)"
            status = "WARN"

        return status, f"延时 {elapsed:.2f}s{warn} | Model: {model_name} | Response: {resp.content.strip()}"
    except Exception as e:
        return False, str(e)


def check_env_apis():
    """Check required API keys and MCP configs."""
    messages = []
    status = True
    
    # 1. LLM API Key（优先 RESEARCHER_API_KEY，fallback OPENAI_API_KEY）
    api_key = os.getenv("RESEARCHER_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        messages.append("缺少 RESEARCHER_API_KEY / OPENAI_API_KEY")
        status = False
    else:
        base = os.getenv("OPENAI_API_BASE", "default")
        key_source = "RESEARCHER_API_KEY" if os.getenv("RESEARCHER_API_KEY") else "OPENAI_API_KEY"
        messages.append(f"LLM API Key 存在 ({key_source}, base: {base})")
        
    # 2. Tushare
    ts_token = os.getenv("TUSHARE_TOKEN")
    if not ts_token:
        messages.append("WARNING: 无 TUSHARE_TOKEN (如果仅使用 AkShare 可忽略)")
        if status is True:
            status = "WARN"
    else:
        try:
            import tushare as ts
            ts.set_token(ts_token)
            pro = ts.pro_api()
            # Test ping
            user = pro.user(token=ts_token)
            if user is not None and len(user) > 0:
                messages.append("Tushare Pro Token 验证成功")
            else:
                messages.append("Tushare Token 验证失败或欠费")
                status = False
        except ImportError:
            messages.append("Tushare API 未安装 (ModuleNotFoundError)")
            status = "WARN"
        except Exception as e:
            messages.append(f"Tushare Ping 失败: {e}")
            status = False
            
    return status, " | ".join(messages)


def check_pool_knowledge():
    """Query FactorPool for metrics on accumulated constraints and passed factors."""
    try:
        from src.factor_pool.pool import get_factor_pool
        pool = get_factor_pool()

        factors = pool.get_top_factors(limit=1000)
        constraints = pool.get_active_constraints() if hasattr(pool, "get_active_constraints") else []

        knowledge_msg = f"已积累 {len(constraints)} 条避坑约束规则"
        pool_msg = f"服役因子: {len(factors)} 个"

        return True, {"knowledge": knowledge_msg, "pool": pool_msg}
    except Exception as e:
        return False, str(e)
    except Exception as e:
        return False, {"knowledge": str(e), "pool": str(e)}


async def main():
    console.print(Panel("[bold cyan]Pixiu System Doctor: Pre-flight Check[/bold cyan]", border_style="cyan"))
    
    table = Table(show_header=True, header_style="bold magenta", expand=True)
    table.add_column("检查项目 (Domain)", width=20)
    table.add_column("状态 (Status)", width=10, justify="center")
    table.add_column("详情 (Details)")
    
    def _add_result(name, status_code, details):
        if status_code is True:
            color = "green"
            icon = "✅ PASS"
        elif status_code == "WARN":
            color = "yellow"
            icon = "⚠️ WARN"
        else:
            color = "red"
            icon = "❌ FAIL"
            
        table.add_row(name, f"[{color}]{icon}[/{color}]", details)
    
    # 1. Data layer
    data_pass, data_msg = check_data_layer()
    _add_result("数据 (Data)", data_pass, data_msg)
    
    # 2. LLM layer
    llm_pass, llm_msg = await check_llm_layer()
    _add_result("算力 (LLM)", llm_pass, llm_msg)
    
    # 3. Environment & APIs
    env_pass, env_msg = check_env_apis()
    _add_result("工具 (MCP/API)", env_pass, env_msg)
    
    # 4 & 5. Knowledge & Pool
    k_pass, k_dict = check_pool_knowledge()
    if k_pass:
        _add_result("知识 (Knowledge)", True, k_dict.get("knowledge", ""))
        _add_result("因子池 (Pool)", True, k_dict.get("pool", ""))
    else:
        _add_result("底层存储 (DB)", False, str(k_dict))
        
    console.print(table)
    
    if not all(x is True for x in [data_pass, llm_pass, k_pass]) or env_pass is False:
        console.print("[bold red]⚠️ 发现红灯错误，请在运行 Pixiu 之前修复。[/bold red]")
    else:
        console.print("[bold green]✓ 全系统自检通过。可以启动。[/bold green]")


if __name__ == "__main__":
    from dotenv import load_dotenv
    # 确保从项目根目录加载 .env
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(project_root, ".env"), override=True)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]已取消。[/yellow]")
