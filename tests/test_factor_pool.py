"""验收测试：FactorPool ChromaDB 数据层。"""
import json
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.agents.schemas import BacktestMetrics, FactorHypothesis
from src.factor_pool.pool import FactorPool
from src.schemas.backtest import BacktestMetrics as V2BacktestMetrics, BacktestReport, FactorSpecSnapshot
from src.schemas.judgment import CriticVerdict, RiskAuditReport


@pytest.fixture()
def pool(tmp_path):
    """每个测试用独立临时数据库，互不干扰。"""
    return FactorPool(db_path=str(tmp_path / "test_db"))


def _make_hypothesis(name="test_factor", formula="Mean($close, 5) / Ref($close, 5)"):
    return FactorHypothesis(
        name=name,
        formula=formula,
        hypothesis="测试因子",
        rationale="用于单元测试",
    )


def _make_metrics(sharpe=2.0, ic=0.03, icir=0.4, turnover=20.0, success=True):
    return BacktestMetrics(
        sharpe=sharpe, ic=ic, icir=icir, turnover=turnover,
        parse_success=success,
    )


class TestRegister:
    def test_register_basic(self, pool):
        h = _make_hypothesis()
        m = _make_metrics()
        fid = pool.register(h, m, island_name="momentum")
        assert "momentum" in fid
        assert pool._collection.count() == 1

    def test_register_multiple(self, pool):
        for i in range(3):
            h = _make_hypothesis(name=f"test_factor_{i}")
            pool.register(h, _make_metrics(), island_name="momentum")
        assert pool._collection.count() == 3


class TestReads:
    def test_get_island_best_factors(self, pool):
        # 写入三个因子，Sharpe 分别为 1.0, 3.0, 2.0
        pool.register(_make_hypothesis("f1"), _make_metrics(sharpe=1.0), "momentum")
        pool.register(_make_hypothesis("f2"), _make_metrics(sharpe=3.0), "momentum")
        pool.register(_make_hypothesis("f3"), _make_metrics(sharpe=2.0), "momentum")
        
        # 另外一个 Island
        pool.register(_make_hypothesis("f4"), _make_metrics(sharpe=5.0), "valuation")

        bests = pool.get_island_best_factors("momentum", top_k=2)
        assert len(bests) == 2
        assert bests[0]["sharpe"] == 3.0
        assert bests[1]["sharpe"] == 2.0

    def test_get_similar_failures(self, pool):
        # 相似失败 (Sharpe 低于基线)
        pool.register(
            _make_hypothesis("fail1", "$close / Ref($close, 5)"),
            _make_metrics(sharpe=1.0, success=True),
            "momentum"
        )
        # 相似成功 (Sharpe 高于基线)
        pool.register(
            _make_hypothesis("success1", "$close / Ref($close, 5) + 1"),
            _make_metrics(sharpe=3.0, success=True),
            "momentum"
        )
        
        failures = pool.get_similar_failures("$close / Ref($close, 5)", top_k=5)
        
        assert len(failures) == 1
        assert failures[0]["sharpe"] == 1.0
        assert "fail1" in failures[0]["factor_name"]

    def test_get_island_leaderboard(self, pool):
        pool.register(_make_hypothesis("f1"), _make_metrics(sharpe=1.0), "momentum")
        pool.register(_make_hypothesis("f2"), _make_metrics(sharpe=2.0), "momentum")
        
        pool.register(_make_hypothesis("f3"), _make_metrics(sharpe=5.0), "valuation")

        board = pool.get_island_leaderboard()
        assert len(board) == 2
        # Valuation has max sharpe 5.0, so it should be first
        assert board[0]["island"] == "valuation"
        assert board[0]["best_sharpe"] == 5.0
        
        assert board[1]["island"] == "momentum"
        assert board[1]["best_sharpe"] == 2.0
        assert board[1]["avg_sharpe"] == 1.5
        assert board[1]["factor_count"] == 2

    def test_get_stats(self, pool):
        pool.register(_make_hypothesis("f1"), _make_metrics(sharpe=1.0), "momentum")
        # > 2.67 baseline
        pool.register(_make_hypothesis("f2"), _make_metrics(sharpe=3.0), "momentum") 

        stats = pool.get_stats()
        assert stats["total_factors"] == 2
        assert stats["beats_baseline_count"] == 1
        assert stats["global_best_sharpe"] == 3.0
        assert stats["global_avg_sharpe"] == 2.0

    def test_register_factor_writes_richer_contract_metadata(self, pool):
        report = BacktestReport(
            report_id="report-1",
            note_id="note-1",
            factor_id="factor-1",
            island="momentum",
            formula="$close",
            factor_spec=FactorSpecSnapshot(
                formula="$close",
                hypothesis="趋势延续",
                economic_rationale="资金流和惯性共同驱动。",
            ),
            metrics=V2BacktestMetrics(
                sharpe=3.0,
                annualized_return=0.2,
                annual_return=0.2,
                max_drawdown=0.1,
                ic_mean=0.04,
                ic_std=0.03,
                icir=0.6,
                turnover_rate=0.18,
                turnover=0.18,
                coverage=1.0,
            ),
            passed=True,
            execution_time_seconds=1.0,
            qlib_output_raw="{}",
        )
        verdict = CriticVerdict(
            report_id="report-1",
            factor_id="factor-1",
            note_id="note-1",
            overall_passed=True,
            decision="promote",
            score=0.92,
            checks=[],
            register_to_pool=True,
            pool_tags=["passed", "decision:promote"],
            reason_codes=[],
        )
        risk = RiskAuditReport(
            factor_id="factor-1",
            overfitting_score=0.1,
            overfitting_flag=False,
            correlation_flags=[],
            recommendation="clear",
            audit_notes="ok",
        )

        pool.register_factor(report=report, verdict=verdict, risk_report=risk)

        rows = pool._collection.get(where={"island": "momentum"}, include=["metadatas"])
        assert len(rows["metadatas"]) == 1
        meta = rows["metadatas"][0]
        assert meta["note_id"] == "note-1"
        assert meta["backtest_report_id"] == "report-1"
        assert meta["decision"] == "promote"
        assert meta["score"] == 0.92
        assert meta["coverage"] == 1.0
        assert meta["economic_rationale"] == "资金流和惯性共同驱动。"
