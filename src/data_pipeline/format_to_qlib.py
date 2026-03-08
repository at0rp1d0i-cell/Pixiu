"""
Pixiu: Parquet -> Qlib Bin 高速转换器 (完全对齐底层 C++ 内存映射规范)
读取 data_downloader 生成的高质量 Parquet 文件，注入 start_index，并输出二进制。
"""
import os
import struct
import numpy as np
import pandas as pd
from tqdm import tqdm

PARQUET_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "parquet_staging"))
QLIB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "qlib_bin"))
# 按照研报规范，这 8 个列是必须的，特别是 vwap 经常在因子中被使用
FIELDS = ["open", "close", "high", "low", "volume", "amount", "vwap", "factor"]
FREQ = "day"

def main():
    import shutil
    if os.path.exists(QLIB_DIR):
        shutil.rmtree(QLIB_DIR)
    
    parquet_files = [f for f in os.listdir(PARQUET_DIR) if f.endswith('.parquet')]
    print(f"找到 {len(parquet_files)} 个 Parquet 清洗文件。\n")
    
    # Step 1: 构建统一交易日历
    print("Step 1/3: 聚合系统交易日历 (Calendars)...")
    all_dates = set()
    for fname in parquet_files:
        df = pd.read_parquet(os.path.join(PARQUET_DIR, fname), columns=['date'])
        all_dates.update(df['date'].tolist())
    
    calendar = sorted(list(all_dates))
    date_to_idx = {d: i for i, d in enumerate(calendar)}
    
    cal_dir = os.path.join(QLIB_DIR, "calendars")
    os.makedirs(cal_dir, exist_ok=True)
    with open(os.path.join(cal_dir, f"{FREQ}.txt"), "w") as f:
        for d in calendar:
            f.write(d + "\n")
    print(f"  日历边界: {len(calendar)} 个交易日 ({calendar[0]} ~ {calendar[-1]})\n")
    
    # Step 2: 序列化浮点数因子至内存数组
    print("Step 2/3: 执行浮点数量化序列化 (注入 start_index)...")
    feat_dir = os.path.join(QLIB_DIR, "features")
    stock_info = {}
    
    for fname in tqdm(parquet_files, desc="Serializing to .bin"):
        symbol = fname.replace(".parquet", "").upper()
        df = pd.read_parquet(os.path.join(PARQUET_DIR, fname))
        
        if df.empty:
            continue
            
        df = df.sort_values('date').reset_index(drop=True)
        # 防止部分脏日期
        df = df[df['date'].isin(date_to_idx)]
        if df.empty:
            continue
        
        start_idx = date_to_idx[df['date'].iloc[0]]
        end_idx = date_to_idx[df['date'].iloc[-1]]
        
        stock_info[symbol] = (df['date'].iloc[0], df['date'].iloc[-1])
        
        sym_dir = os.path.join(feat_dir, symbol.lower())
        os.makedirs(sym_dir, exist_ok=True)
        
        for field in FIELDS:
            if field not in df.columns:
                continue
            
            length = end_idx - start_idx + 1
            arr = np.full(length, np.nan, dtype=np.float32)
            
            # 使用 numpy 加速映射，避免 iterrows
            valid_dates = df['date'].values
            valid_vals = df[field].values.astype(np.float32)
            
            for d, val in zip(valid_dates, valid_vals):
                idx = date_to_idx[d] - start_idx
                arr[idx] = val
            
            bin_path = os.path.join(sym_dir, f"{field}.{FREQ}.bin")
            with open(bin_path, 'wb') as fp:
                # 写入头: 4字节 uint32 start_index (小端序)
                fp.write(np.array([start_idx], dtype='<u4').tobytes())
                # 写入连续数组: N字节 float32 (小端序)
                # 为确保兼容性，统一指定为小端浮点 '<f4'
                fp.write(arr.astype('<f4').tobytes())
                
    # Step 3: 构建系统基准池索引
    print("\nStep 3/3: 封装 Instruments 索引集...")
    inst_dir = os.path.join(QLIB_DIR, "instruments")
    os.makedirs(inst_dir, exist_ok=True)
    with open(os.path.join(inst_dir, "all.txt"), "w") as f:
        for symbol, (start, end) in sorted(stock_info.items()):
            f.write(f"{symbol}\t{start}\t{end}\n")
            
    print(f"  装载标的: {len(stock_info)} 只成分股")
    print(f"\n✅ 平台数据隔离区重构完成！Qlib 引擎载入地址: {QLIB_DIR}")

if __name__ == "__main__":
    main()
