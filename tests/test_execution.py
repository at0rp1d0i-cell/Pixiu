import pytest
import json
import asyncio
from unittest.mock import patch, MagicMock

# 等待实现的模块
from src.execution.coder import Coder
from src.execution.docker_runner import DockerRunner, ExecutionResult
from src.schemas.research_note import FactorResearchNote
from src.schemas.backtest import BacktestReport
from src.schemas.thresholds import THRESHOLDS

@pytest.fixture
def mock_note():
    return FactorResearchNote(
        note_id="test_island_20260307_01",
        island="test_island",
        iteration=1,
        hypothesis="Test",
        economic_intuition="Test",
        proposed_formula="$close",
        exploration_questions=[],
        risk_factors=[],
        market_context_date="2026-03-07"
    )

@pytest.mark.asyncio
async def test_coder_valid_formula(mock_note):
    """合法 Qlib 公式应返回 BacktestReport(passed=True 或 False，无 error)"""
    coder = Coder()
    
    # Mock DockerRunner 返回成功且带有标准 JSON 的输出
    mock_stdout = "Some logs...\nBACKTEST_RESULT_JSON:" + json.dumps({
        "sharpe": 2.8,
        "annualized_return": 0.3,
        "max_drawdown": 0.1,
        "ic_mean": 0.03,
        "ic_std": 0.04,
        "icir": 0.75,
        "turnover_rate": 0.2,
        "error": None
    })
    
    mock_exec_result = ExecutionResult(
        success=True,
        stdout=mock_stdout,
        stderr="",
        returncode=0,
        duration_seconds=10.5
    )
    
    with patch.object(coder.runner, "run_python", return_value=mock_exec_result):
        report = await coder.run_backtest(mock_note)
        
    assert isinstance(report, BacktestReport)
    assert report.error_message is None
    # 2.8 >= 2.67 (默认)，IC 等也满足条件
    assert report.passed is True
    assert report.metrics.sharpe == 2.8

@pytest.mark.asyncio
async def test_coder_invalid_formula(mock_note):
    """语法错误公式应返回 BacktestReport(passed=False, error_message 非空)"""
    coder = Coder()
    
    # 模拟 Qlib 崩溃或返回了 Error JSON
    mock_stdout = "Traceback...\nBACKTEST_RESULT_JSON:" + json.dumps({
        "sharpe": 0.0,
        "annualized_return": 0.0,
        "max_drawdown": 0.0,
        "ic_mean": 0.0,
        "ic_std": 0.0,
        "icir": 0.0,
        "turnover_rate": 0.0,
        "error": "SyntaxError: invalid syntax in formula"
    })
    
    mock_exec_result = ExecutionResult(
        success=True,  # 脚本没崩，但 Qlib 抓到了异常并输出了错误 JSON
        stdout=mock_stdout,
        stderr="",
        returncode=0,
        duration_seconds=5.0
    )
    
    with patch.object(coder.runner, "run_python", return_value=mock_exec_result):
        report = await coder.run_backtest(mock_note)
        
    assert report.passed is False
    assert "SyntaxError" in report.error_message

def test_coder_output_parsing(mock_note):
    """BACKTEST_RESULT_JSON 解析逻辑单元测试（不需要 Docker）"""
    coder = Coder()
    
    # 模拟容器彻底崩溃
    mock_exec_result = ExecutionResult(
        success=False,
        stdout="",
        stderr="OOM Killed",
        returncode=137,
        duration_seconds=20.0
    )
    
    report = coder._parse_result(mock_exec_result, mock_note, "test_factor", "$close")
    assert report.passed is False
    assert "执行失败" in report.error_message
    assert "OOM" in report.error_message

def test_exploration_agent_script_extraction():
    """LLM 输出代码块提取逻辑单元测试"""
    from src.execution.exploration_agent import ExplorationAgent
    
    with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key', 'RESEARCHER_API_KEY': 'test-key'}):
        agent = ExplorationAgent()
    
    # 情况1: 包含 markdown 代码块
    content_with_md = "Here is the script:\n```python\nimport pandas as pd\nprint('hello')\n```\nDone."
    assert agent._extract_script(content_with_md).strip() == "import pandas as pd\nprint('hello')"
    
    # 情况2: 直接是纯代码
    content_raw = "import pandas as pd\nprint('hello')"
    assert agent._extract_script(content_raw).strip() == content_raw

@pytest.mark.asyncio
async def test_docker_runner_timeout():
    """超时处理：运行 sleep(9999) 应在 timeout 后被我们拦截并返回失败状态"""
    runner = DockerRunner()
    
    script = "import time\ntime.sleep(10)"
    
    # 真实的依赖 Docker 会比较耗时，这里我们需要 mock asyncio.wait_for 来模拟 TimeoutError
    with patch("asyncio.create_subprocess_exec") as mock_exec, \
         patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
        
        mock_proc = MagicMock()
        mock_exec.return_value = mock_proc
        
        result = await runner.run_python(script, timeout_seconds=1)
        
        assert result.success is False
        assert "执行超时" in result.stderr
        mock_proc.kill.assert_called_once()
