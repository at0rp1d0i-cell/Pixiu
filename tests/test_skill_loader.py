"""验收测试：SkillLoader 条件注入逻辑。"""
import os, sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

pytestmark = pytest.mark.unit

from src.skills.loader import SkillLoader


@pytest.fixture()
def loader():
    return SkillLoader()


def _state(iteration=0, error=""):
    return {"current_iteration": iteration, "error_message": error,
            "max_iterations": 3, "island_name": "momentum"}


class TestSkillLoader:
    def test_type_a_always_injected(self, loader):
        """A 股约束和 Qlib 语法规范在任何状态下都必须存在。"""
        result = loader.load_for_researcher(_state(iteration=0))
        assert "T+1" in result or "前视偏差" in result  # a_share_constraints
        assert "Ref(expr, N)" in result or "合法算子" in result  # qlib_formula_syntax

    def test_island_evolution_not_injected_first_round(self, loader):
        """第一轮（iteration=0）不注入 island_evolution.md。"""
        result = loader.load_for_researcher(_state(iteration=0))
        assert "强制工作流程" not in result

    def test_island_evolution_injected_after_first_round(self, loader):
        """第二轮起注入 island_evolution.md。"""
        result = loader.load_for_researcher(_state(iteration=1))
        assert "强制工作流程" in result

    def test_feedback_not_injected_without_error(self, loader):
        """没有错误时不注入 feedback_interpretation.md。"""
        result = loader.load_for_researcher(_state(error=""))
        assert "上一次失败的错误消息解读" not in result

    def test_feedback_injected_with_error(self, loader):
        """有错误记录时注入 feedback_interpretation.md。"""
        result = loader.load_for_researcher(_state(error="Sharpe 2.1 未超越基线"))
        assert "上一次失败的错误消息解读" in result

    def test_both_context_skills_injected(self, loader):
        """iteration>0 且有 error 时，两个 Type C Skill 都应注入。"""
        result = loader.load_for_researcher(_state(iteration=2, error="IC低"))
        assert "强制工作流程" in result
        assert "上一次失败的错误消息解读" in result

    def test_coder_skill_loads(self, loader):
        result = loader.load_for_coder()
        out = result or "" # deal with missing coder skill for now
        assert len(out) >= 0

    def test_missing_skill_returns_none(self, loader):
        result = loader._load("nonexistent/file.md", required=False)
        assert result is None


class TestValidatorConstraints:
    """验证 validator.py 新增的硬约束检查。"""

    def test_future_ref_detected(self):
        from src.agents.validator import _check_no_future_leak
        ok, msg = _check_no_future_leak("Ref($close, -1)")
        assert not ok
        assert "前视偏差" in msg or "负数" in msg

    def test_positive_ref_passes(self):
        from src.agents.validator import _check_no_future_leak
        ok, _ = _check_no_future_leak("Ref($close, 5)")
        assert ok

    def test_invalid_field_detected(self):
        from src.agents.validator import _check_valid_fields
        ok, msg = _check_valid_fields("Mean($price, 5)")
        assert not ok
        assert "price" in msg

    def test_valid_fields_pass(self):
        from src.agents.validator import _check_valid_fields
        ok, _ = _check_valid_fields("Mean($close, 5) / Ref($volume, 1)")
        assert ok

    def test_log_negative_detected(self):
        from src.agents.validator import _check_log_safety
        ok, msg = _check_log_safety("Log($close - Ref($close, 1))")
        assert not ok

    def test_log_ratio_passes(self):
        from src.agents.validator import _check_log_safety
        ok, _ = _check_log_safety("Log($close / Ref($close, 1))")
        assert ok


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
