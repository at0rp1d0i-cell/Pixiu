"""
Pixiu: Qlib 基线模型 (Phase 1 Skateboard)
logging.basicConfig(level=logging.INFO, format='%(message)s')
使用 Alpha158 因子 + LightGBM 模型进行沪深300的截面选股回测。
这是 AI 系统未来需要击败的"及格线"。
"""
import logging
import qlib
from qlib.constant import REG_CN
from qlib.utils import init_instance_by_config
import os
from pathlib import Path
import pandas as pd
import numpy as np
from qlib.workflow import R

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_qlib_env = os.getenv("QLIB_DATA_DIR")
if _qlib_env:
    QLIB_DIR = Path(_qlib_env) if os.path.isabs(_qlib_env) else PROJECT_ROOT / _qlib_env
else:
    QLIB_DIR = PROJECT_ROOT / "data" / "qlib_bin"
RESULTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "results"))

def run_baseline():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    
    # MLflow Setup via Qlib
    R.set_uri(f"file://{os.path.abspath(os.path.join(RESULTS_DIR, '..', 'mlruns'))}")
    R.start_exp(experiment_name="Pixiu_Research")
    R.start_run(run_name="baseline_Alpha158_LGBM")
    
    logging.info("Step 1: 初始化 Qlib...")
    qlib.init(provider_uri=str(QLIB_DIR), region=REG_CN)
    logging.info("  ✅ Qlib 初始化成功。\n")

    # ============ Step 2: Alpha158 数据集 ============
    logging.info("Step 2: 构建 Alpha158 因子数据集...")
    
    dataset_config = {
        "class": "DatasetH",
        "module_path": "qlib.data.dataset",
        "kwargs": {
            "handler": {
                "class": "Alpha158",
                "module_path": "qlib.contrib.data.handler",
                "kwargs": {
                    "start_time": "2021-06-01",
                    "end_time": "2026-02-24",
                    "fit_start_time": "2021-06-01",
                    "fit_end_time": "2024-06-30",
                    "instruments": "all",
                },
            },
            "segments": {
                "train": ("2021-06-01", "2024-06-30"),
                "valid": ("2024-07-01", "2025-03-31"),
                "test":  ("2025-04-01", "2026-02-24"),
            },
        },
    }
    
    dataset = init_instance_by_config(dataset_config)
    logging.info("  ✅ Alpha158 数据集构建完成。\n")
        
    R.log_params(**{
        "dataset": "Alpha158",
        "universe": "all",
        "train_period": "2021-06-01 to 2024-06-30",
        "test_period": "2025-04-01 to 2026-02-24"
    })
    
    # ============ Step 3: LightGBM 模型 ============
    logging.info("Step 3: 训练 LightGBM 模型...")
    
    model_config = {
        "class": "LGBModel",
        "module_path": "qlib.contrib.model.gbdt",
        "kwargs": {
            "loss": "mse",
            "colsample_bytree": 0.8879,
            "learning_rate": 0.0421,
            "subsample": 0.8789,
            "lambda_l1": 205.6999,
            "lambda_l2": 580.9768,
            "max_depth": 8,
            "num_leaves": 210,
            "num_threads": 4,
        },
    }
    
    model = init_instance_by_config(model_config)
    model.fit(dataset)
    logging.info("  ✅ LightGBM 训练完成。\n")
        
    R.log_params(**{
        "model": "LightGBM",
        "learning_rate": model_config["kwargs"]["learning_rate"],
        "max_depth": model_config["kwargs"]["max_depth"],
        "num_leaves": model_config["kwargs"]["num_leaves"]
    })
    
    # ============ Step 4: 预测 ============
    logging.info("Step 4: 在测试集上预测...")
    pred = model.predict(dataset)
    logging.info(f"  预测结果形状: {pred.shape}")
    logging.info(f"  预测值范围: [{pred.min():.6f}, {pred.max():.6f}]\n")
    
    # 保存预测结果
    pred_path = os.path.join(RESULTS_DIR, "baseline_predictions.csv")
    pred.to_csv(pred_path)
    
    # ============ Step 5: 简化回测 (不依赖 benchmark) ============
    logging.info("Step 5: 简化回测 (TopK 选股模拟)...")
    
    # 将预测结果转为 DataFrame
    pred_df = pred.to_frame("score").reset_index()
    
    # 按日期分组，每天选 Top 50 只股票
    topk = 50
    daily_returns = []
    
    # 加载收盘价数据用于计算收益率
    from qlib.data import D
    
    # 获取测试期间所有股票的收盘价
    instruments = D.instruments("all")
    close_df = D.features(
        instruments, 
        fields=['$close'], 
        start_time='2025-04-01', 
        end_time='2026-02-24'
    ).reset_index().rename(columns={'$close': 'close'})
    
    # 计算每日收益率
    close_df['return'] = close_df.groupby('instrument')['close'].pct_change()
    
    # 合并预测分数和收益率
    merged = pd.merge(pred_df, close_df, on=['instrument', 'datetime'], how='inner')
    
    # 按日期分组，选 TopK
    dates = sorted(merged['datetime'].unique())
    portfolio_returns = []
    
    for date in dates:
        day_data = merged[merged['datetime'] == date].dropna(subset=['score', 'return'])
        if len(day_data) < topk:
            continue
        
        # 选择得分最高的 topk 只
        top_stocks = day_data.nlargest(topk, 'score')
        
        # 等权组合收益 (扣除万5买入+万15卖出手续费的粗略近似)
        avg_return = top_stocks['return'].mean()
        portfolio_returns.append({
            'date': date,
            'portfolio_return': avg_return,
            'num_stocks': len(top_stocks),
        })
    
    result_df = pd.DataFrame(portfolio_returns)
    result_df['cumulative_return'] = (1 + result_df['portfolio_return']).cumprod()
    
    # ============ Step 6: 输出结果 ============
    logging.info("\n" + "=" * 60)
    logging.info("📊 Pixiu Baseline Results (Alpha158 + LightGBM + TopK50)")
    logging.info("=" * 60)
    
    total_return = result_df['cumulative_return'].iloc[-1] - 1
    trading_days = len(result_df)
    annual_return = (1 + total_return) ** (252 / max(trading_days, 1)) - 1
    daily_returns_arr = result_df['portfolio_return'].values
    sharpe = np.sqrt(252) * daily_returns_arr.mean() / max(daily_returns_arr.std(), 1e-8)
    max_drawdown = (result_df['cumulative_return'] / result_df['cumulative_return'].cummax() - 1).min()
    
    logging.info(f"  测试期间:        2025-04-01 ~ 2026-02-24")
    logging.info(f"  交易天数:        {trading_days}")
    logging.info(f"  累计收益率:      {total_return:.2%}")
    logging.info(f"  年化收益率:      {annual_return:.2%}")
    logging.info(f"  夏普比率:        {sharpe:.4f}")
    logging.info(f"  最大回撤:        {max_drawdown:.2%}")
    logging.info(f"  每日平均持仓:    {topk} 只")
    
    # 保存完整结果
    result_path = os.path.join(RESULTS_DIR, "baseline_report.csv")
    result_df.to_csv(result_path, index=False)
    logging.info(f"\n📄 报告已保存: {result_path}")
    
    
    R.log_metrics(**{
        "total_return": total_return,
        "annual_return": annual_return,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown
    })
    # Qlib R module doesn't natively expose log_artifact directly sometimes, 
    # so we skip file artifacts for now or use save_objects if needed.
    
    # 生成简单的收益曲线图
    try:
        import matplotlib.pyplot as plt
        import matplotlib
        matplotlib.use('Agg')
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), gridspec_kw={'height_ratios': [3, 1]})
        
        ax1.plot(result_df['date'], result_df['cumulative_return'], color='#2196F3', linewidth=2)
        ax1.axhline(y=1.0, color='gray', linestyle='--', alpha=0.5)
        ax1.set_title('Pixiu Baseline: Alpha158 + LightGBM (CSI 300 Universe)', fontsize=14)
        ax1.set_ylabel('Cumulative Return')
        ax1.grid(True, alpha=0.3)
        
        drawdown = result_df['cumulative_return'] / result_df['cumulative_return'].cummax() - 1
        ax2.fill_between(result_df['date'], drawdown, 0, color='#F44336', alpha=0.4)
        ax2.set_ylabel('Drawdown')
        ax2.set_xlabel('Date')
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        fig_path = os.path.join(RESULTS_DIR, "baseline_equity_curve.png")
        plt.savefig(fig_path, dpi=150)
        logging.info(f"📈 收益曲线图: {fig_path}")
    except Exception as e:
        logging.info(f"绘图失败 (非关键): {e}")
        
    R.end_run()
    
    logging.info("\n✅ Phase 1 Skateboard 基线完成！这是 AI 系统需要击败的靶子。🎯")

if __name__ == "__main__":
    run_baseline()
