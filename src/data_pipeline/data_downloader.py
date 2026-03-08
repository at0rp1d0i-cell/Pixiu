"""
Pixiu 数据下载与预处理核心引擎 (Phase 1 架构升级)
实现从 BaoStock 获取 A 股数据，处理前/后复权，严格计算 Factor，
清洗停牌缺失值，并输出为 Qlib 兼容的 Parquet 格式，杜绝数据倾轧。
"""
import baostock as bs
import pandas as pd
import numpy as np
import os
from tqdm import tqdm
from datetime import datetime, timedelta

# ============ 配置 ============
PARQUET_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "parquet_staging"))
START_DATE = (datetime.now() - timedelta(days=365 * 5)).strftime("%Y-%m-%d")
END_DATE = datetime.now().strftime("%Y-%m-%d")
# ==============================

def setup_dirs():
    os.makedirs(PARQUET_DIR, exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(__file__), "..", "..", "data", "qlib_bin"), exist_ok=True)

def bs_code_to_qlib(bs_code: str) -> str:
    """市场代码正规化：sh.600000 -> SH600000"""
    return bs_code.replace(".", "").upper()

def get_csi300_components():
    print("正在获取沪深300成分股名单...")
    rs = bs.query_hs300_stocks()
    if rs.error_code != '0':
        print(f"获取失败: {rs.error_msg}")
        return []
    
    stocks = []
    while rs.next():
        row = rs.get_row_data()
        stocks.append(row[1]) 
    return stocks

def fetch_bs_data(code: str, adjustflag: str) -> pd.DataFrame:
    """统一的 BaoStock 获取数据函数"""
    fields = "date,open,high,low,close,volume,amount"
    rs = bs.query_history_k_data_plus(
        code, fields, start_date=START_DATE, end_date=END_DATE,
        frequency="d", adjustflag=adjustflag
    )
    if rs.error_code != '0':
        return pd.DataFrame()
    
    data_list = []
    while rs.next():
        data_list.append(rs.get_row_data())
    
    if not data_list:
        return pd.DataFrame()
    
    df = pd.DataFrame(data_list, columns=fields.split(","))
    for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    df['date'] = pd.to_datetime(df['date'])
    return df

def process_single_asset(code: str) -> bool:
    qlib_code = bs_code_to_qlib(code)
    parquet_path = os.path.join(PARQUET_DIR, f"{qlib_code}.parquet")
    
    if os.path.exists(parquet_path):
        return True # 已缓存
        
    # 1. 获取未复权数据 (用于真实的 Amount 和计算 Factor)
    df_unadj = fetch_bs_data(code, adjustflag="3")
    
    # 2. 获取后复权数据 (用于连续的 OHLC)
    df_hfq = fetch_bs_data(code, adjustflag="1")
    
    if df_unadj.empty or df_hfq.empty:
        return False
        
    # 按照日期进行强对齐
    df_merged = pd.merge(
        df_hfq, 
        df_unadj[['date', 'close', 'volume', 'amount']], 
        on='date', 
        suffixes=('_hfq', '_unadj')
    )
    
    qlib_df = pd.DataFrame()
    qlib_df['date'] = df_merged['date']
    qlib_df['symbol'] = qlib_code
    
    # 3. 填充基础后复权价格特征
    qlib_df['open'] = df_merged['open']
    qlib_df['close'] = df_merged['close_hfq']
    qlib_df['high'] = df_merged['high']
    qlib_df['low'] = df_merged['low']
    
    # 4. 逆向推导复权因子: factor = adjusted / original
    unadj_close = df_merged['close_unadj'].replace(0, np.nan)
    qlib_df['factor'] = qlib_df['close'] / unadj_close
    
    # 5. 反推交易量，保持整体实际交易资金不异变
    qlib_df['volume'] = df_merged['volume_unadj'] / qlib_df['factor']
    qlib_df['amount'] = df_merged['amount_unadj']
    
    # 增加 vwap 字段计算 (VWAP = Amount / Volume)
    # 处理停牌或无交易引发的除 0 问题
    unadj_vwap = (df_merged['amount_unadj'] / df_merged['volume_unadj']).replace([np.inf, -np.inf], np.nan)
    qlib_df['vwap'] = unadj_vwap * qlib_df['factor']
    
    # 6. 停牌遮罩清洗机制：成交量为 0 的天强置为 NaN，阻断未来无效梯度
    suspended_mask = (df_merged['volume_unadj'] <= 0)
    target_cols = ['open', 'close', 'high', 'low', 'volume', 'amount', 'vwap', 'factor']
    qlib_df.loc[suspended_mask, target_cols] = np.nan
    
    # 针对极端未复权数据引发的问题进行保险清理
    qlib_df[target_cols] = qlib_df[target_cols].replace([np.inf, -np.inf], np.nan)
    
    # 7. 保留原始顺序并写入 Parquet
    qlib_df['date'] = qlib_df['date'].dt.strftime('%Y-%m-%d')
    qlib_df.to_parquet(parquet_path, index=False)
    
    return True

def download_all(stock_codes: list):
    print(f"开始核心清洗与并发下载 {len(stock_codes)} 只股票 ({START_DATE} ~ {END_DATE})...")
    
    success = 0
    fail = 0
    failed_codes = []
    
    for code in tqdm(stock_codes, desc="Processing Pipeline"):
        if process_single_asset(code):
            success += 1
        else:
            fail += 1
            failed_codes.append(code)
    
    print(f"\n✅ 数据提取清洗完成！成功: {success}, 失败: {fail}")
    if failed_codes:
        print(f"⚠️  失败的股票: {failed_codes[:10]}{'...' if len(failed_codes) > 10 else ''}")
    print(f"📂 Parquet 文件保存在: {PARQUET_DIR}")

if __name__ == "__main__":
    setup_dirs()
    
    # 登录 BaoStock
    lg = bs.login()
    if lg.error_code != '0':
        print(f"BaoStock 登录失败: {lg.error_msg}")
        exit(1)
        
    try:
        codes = get_csi300_components()
        if codes:
            download_all(codes)
    finally:
        bs.logout()
