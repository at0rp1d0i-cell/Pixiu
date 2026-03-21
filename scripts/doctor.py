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
        
        qlib_path = os.path.expanduser("~/.qlib/qlib_data/cn_data/features")
        if not os.path.exists(qlib_path):
            return False, f"Qlib features dir not found: {qlib_path}"
        
        files = os.listdir(qlib_path)
        return True, f"Qlib 可用，检测到 {fields_count} 个能力集字段，底层 Bin 数量: {len(files)}"
    except Exception as e:
        return False, str(e)


async def check_llm_layer():
    """Ping test to configured LLM."""
    try:
        from src.llm.openai_compat import build_researcher_llm
        from langchain_core.messages import HumanMessage
        llm = build_researcher_llm(profile="doctor")
        
        start = perf_counter()
        # 1 token prompt
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
    
    # 1. OpenAI
    if not os.getenv("OPENAI_API_KEY"):
        messages.append("缺少 OPENAI_API_KEY")
        status = False
    else:
        messages.append(f"LLM Token 存在 ({os.getenv('OPENAI_API_BASE', 'Default')})")
        
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
        
        # We access sqlite cursor directly for quick broad stats
        cursor = getattr(pool, "cursor", None)
        if hasattr(pool, "_conn"):
            cursor = getattr(pool._conn, "cursor", lambda: None)()
        
        if not cursor:
            # Fallback to public methods
            factors = pool.get_top_factors(limit=1000)
            return True, {
                "knowledge": "无法直接访问 SQLite Cursor",
                "pool": f"已读出 {len(factors)} 个服役因子"
            }
        
        cursor.execute("SELECT COUNT(*) FROM failure_constraints")
        constraints_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM factor_pool WHERE passed=1")
        passed_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT island, MAX(sharpe), AVG(ic_mean) FROM factor_pool WHERE passed=1 GROUP BY island")
        islands = cursor.fetchall()
        
        knowledge_msg = f"已积累 {constraints_count} 条避坑约束规则"
        
        pool_details = [f"服役因子: {passed_count} 个"]
        for row in islands:
            island_name = row[0]
            max_sr = row[1]
            avg_ic = row[2]
            pool_details.append(f"[{island_name}] Max Sharpe={max_sr:.2f}, AvgIC={avg_ic:.4f}")
            
        pool_msg = " | ".join(pool_details)
        
        return True, {"knowledge": knowledge_msg, "pool": pool_msg}
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
        console.print("[bold red]⚠️ 发现红灯错误，请在运行 evoquant 之前修复。[/bold red]")
    else:
        console.print("[bold green]✓ 全系统自检通过。可以启动。[/bold green]")


if __name__ == "__main__":
    from dotenv import load_dotenv
    # Load environment variables
    load_dotenv(override=True)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]已取消。[/yellow]")
