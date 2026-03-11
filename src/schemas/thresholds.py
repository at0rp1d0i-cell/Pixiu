from src.schemas import PixiuBase

class CriticThresholds(PixiuBase):
    """可通过环境变量覆盖的阈值配置"""
    min_sharpe: float = 0.8           # 最小 Sharpe（根据 golden_path 调整）
    min_ic_mean: float = 0.02
    min_icir: float = 0.3
    max_turnover: float = 0.5
    max_drawdown: float = 0.25
    min_coverage: float = 0.7
    max_overfitting_score: float = 0.40
    min_novelty_threshold: float = 0.30  # AST 相似度低于此值才通过 Novelty Filter
    stage3_top_k: int = 5             # Stage 3 最多放行多少个候选进入回测

THRESHOLDS = CriticThresholds()  # 全局单例
