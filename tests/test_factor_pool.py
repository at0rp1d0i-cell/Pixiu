"""验收测试：FactorPool ChromaDB 数据层。"""
from unittest.mock import patch

import pytest

from src.factor_pool.pool import FactorPool
from src.schemas.backtest import BacktestMetrics, BacktestReport, FactorSpecSnapshot
from src.schemas.judgment import CriticVerdict, RiskAuditReport

pytestmark = pytest.mark.unit


@pytest.fixture()
def pool(tmp_path):
    """每个测试用独立临时数据库，互不干扰。"""
    return FactorPool(db_path=str(tmp_path / "test_db"))


def _make_report(name="test_factor", formula="Mean($close, 5) / Ref($close, 5)",
                 island="momentum", sharpe=2.0, ic_mean=0.03, icir=0.4,
                 turnover_rate=20.0) -> BacktestReport:
    # report.passed = quality outcome; execution_succeeded = parse/backtest success
    return BacktestReport(
        report_id=f"report-{name}",
        note_id=f"note-{name}",
        factor_id=f"{island}_{name}",
        island=island,
        formula=formula,
        metrics=BacktestMetrics(
            sharpe=sharpe,
            annualized_return=0.1,
            max_drawdown=-0.1,
            ic_mean=ic_mean,
            ic_std=0.01,
            icir=icir,
            turnover_rate=turnover_rate,
        ),
        passed=True,
        execution_succeeded=True,
        execution_time_seconds=1.0,
        qlib_output_raw="{}",
    )


def _make_verdict(name="test_factor", island="momentum", passed=True) -> CriticVerdict:
    return CriticVerdict(
        report_id=f"report-{name}",
        factor_id=f"{island}_{name}",
        note_id=f"note-{name}",
        overall_passed=passed,
        decision="promote" if passed else "archive",
        score=0.8 if passed else 0.3,
        checks=[],
        register_to_pool=True,
        pool_tags=[],
        reason_codes=[],
    )


def _make_risk(name="test_factor", island="momentum") -> RiskAuditReport:
    return RiskAuditReport(
        factor_id=f"{island}_{name}",
        overfitting_score=0.1,
        overfitting_flag=False,
        correlation_flags=[],
        recommendation="clear",
        audit_notes="ok",
    )


def _register(pool, name, formula="Mean($close, 5) / Ref($close, 5)",
              island="momentum", sharpe=2.0):
    report = _make_report(name=name, formula=formula, island=island, sharpe=sharpe)
    verdict = _make_verdict(name=name, island=island, passed=sharpe > 2.67)
    risk = _make_risk(name=name, island=island)
    pool.register_factor(report=report, verdict=verdict, risk_report=risk,
                         hypothesis="测试因子")


class TestRegister:
    def test_register_basic(self, pool):
        _register(pool, "test_factor", island="momentum")
        assert pool._collection.count() == 1

    def test_register_multiple(self, pool):
        for i in range(3):
            _register(pool, f"test_factor_{i}", island="momentum")
        assert pool._collection.count() == 3

    def test_factor_pool_passes_embedding_function_to_all_collections(self, tmp_path):
        embedding_function = object()

        class _StubCollection:
            def __init__(self):
                self._embedding_function = None

            def count(self):
                return 0

        class _StubClient:
            def __init__(self):
                self.calls = []

            def get_or_create_collection(self, name, embedding_function=None):
                collection = _StubCollection()
                self.calls.append((name, embedding_function, collection))
                return collection

        stub_client = _StubClient()

        with patch(
            "src.factor_pool.pool.build_default_chroma_embedding_function",
            return_value=embedding_function,
        ), patch(
            "src.factor_pool.pool.chromadb.PersistentClient",
            return_value=stub_client,
        ):
            FactorPool(db_path=str(tmp_path / "test_db"))

        assert [name for name, _, _ in stub_client.calls] == [
            "factor_experiments",
            "research_notes",
            "exploration_results",
            "failure_constraints",
        ]
        assert all(
            requested_embedding is None for _, requested_embedding, _ in stub_client.calls
        )
        assert all(
            collection._embedding_function is embedding_function
            for _, _, collection in stub_client.calls
        )


class TestReads:
    def test_get_island_best_factors(self, pool):
        # 写入三个因子，Sharpe 分别为 1.0, 3.0, 2.0
        _register(pool, "f1", island="momentum", sharpe=1.0)
        _register(pool, "f2", island="momentum", sharpe=3.0)
        _register(pool, "f3", island="momentum", sharpe=2.0)

        # 另外一个 Island
        _register(pool, "f4", island="valuation", sharpe=5.0)

        bests = pool.get_island_best_factors("momentum", top_k=2)
        assert len(bests) == 2
        assert bests[0]["sharpe"] == 3.0
        assert bests[1]["sharpe"] == 2.0

    def test_get_similar_failures(self, pool):
        # 相似失败 (Sharpe 低于基线)
        _register(pool, "fail1", formula="$close / Ref($close, 5)",
                  island="momentum", sharpe=1.0)
        # 相似成功 (Sharpe 高于基线)
        _register(pool, "success1", formula="$close / Ref($close, 5) + 1",
                  island="momentum", sharpe=3.0)

        failures = pool.get_similar_failures("$close / Ref($close, 5)", top_k=5)

        assert len(failures) == 1
        assert failures[0]["sharpe"] == 1.0

    def test_get_island_leaderboard(self, pool):
        _register(pool, "f1", island="momentum", sharpe=1.0)
        _register(pool, "f2", island="momentum", sharpe=2.0)

        _register(pool, "f3", island="valuation", sharpe=5.0)

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
        _register(pool, "f1", island="momentum", sharpe=1.0)
        # > 2.67 baseline
        _register(pool, "f2", island="momentum", sharpe=3.0)

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
            metrics=BacktestMetrics(
                sharpe=3.0,
                annualized_return=0.2,
                max_drawdown=0.1,
                ic_mean=0.04,
                ic_std=0.03,
                icir=0.6,
                turnover_rate=0.18,
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
        assert meta["execution_succeeded"] is True
        assert meta["economic_rationale"] == "资金流和惯性共同驱动。"
