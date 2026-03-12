from src.schemas import PixiuBase

class CriticThresholds(PixiuBase):
    """可通过环境变量覆盖的阈值配置"""
    min_sharpe: float = 2.67          # 基线 Sharpe
    min_ic_mean: float = 0.02
    min_icir: float = 0.30
    max_turnover_rate: float = 0.50
    max_turnover: float = 0.50        # 兼容旧 critic / 测试命名
    max_drawdown: float = 0.25
    min_coverage: float = 0.70
    max_overfitting_score: float = 0.40
    min_novelty_threshold: float = 0.30  # AST 相似度低于此值才通过 Novelty Filter
    stage3_top_k: int = 5             # Stage 3 最多放行多少个候选进入回测

THRESHOLDS = CriticThresholds()  # 全局单例
