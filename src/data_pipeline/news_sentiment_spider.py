"""
Pixiu: Layer 3 金融新闻情绪提取器 (News Sentiment Spider)
目标：
1. 走本地 Mihomo 代理 (HTTP: 17890) 绕过防火墙。
2. 爬取金十/财联社的每日宏观及市场动态摘要。
3. 利用代理连点大模型（如 Claude-Haiku / DeepSeek）提取情感极性分数 (-1 ~ 1)。
4. 将该分数存储下来，供后续格式化为 Qlib 特征数据。
"""
import requests
import os
import time
import json
from datetime import datetime
from tqdm import tqdm

# 代理配置 (基于 config.yaml 测试发现 HTTP 端口为 17890)
PROXIES = {
    "http": "http://127.0.0.1:17890",
    "https": "http://127.0.0.1:17890"
}

# 代理后的 LLM Gateway
LLM_API_BASE = os.environ.get("ANTHROPIC_BASE_URL", "http://172.30.128.1:8045/v1").rstrip("/")
# Claude 临时 Key，或者您可以在环境里配置 OPENAI_API_KEY
LLM_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "sk-746322967ed04448b49e5a9273b1fdfd")
LLM_MODEL = "claude-3-5-haiku-20241022" # 情绪识别用 Haiku 更快更便宜

# 输出路径
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "news_sentiment"))
os.makedirs(DATA_DIR, exist_ok=True)

def analyze_sentiment(news_text: str) -> float:
    """
    使用大模型执行少样本情绪打分（Layer 3 知识注入的核心环节）。
    返回 -1.0 (极度利空) 到 1.0 (极度利好) 之间的浮点数。
    """
    prompt = f"""
    作为拥有量化交易背景的资深分析师，请评估以下财经新闻对A股/整体宏观环境的短期情绪影响。
    评分规则：只输出一个数字，介于 -1.0 到 1.0 之间。
    - 1.0：历史级别重大利好（降息降准、特大资金入市）。
    - 0.5：普通利好消息（行业政策扶持、利润大增）。
    - 0.0：中性消息（常规数据发布，无惊无险）。
    - -0.5：普通利空消息（财报不及预期、轻微监管）。
    - -1.0：特大利空（黑天鹅、金融战、重大地缘冲突）。
    
    新闻内容：
    "{news_text}"
    
    输出（仅包含浮点数字）：
    """
    
    headers = {
        "x-api-key": LLM_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    
    data = {
        "model": LLM_MODEL,
        "max_tokens": 10,
        "temperature": 0.0,
        "messages": [{"role": "user", "content": prompt}]
    }
    
    try:
        # 这个调用可以直接走 Windows/WSL 的 Gateway (不需要挂爬虫代理)
        resp = requests.post(f"{LLM_API_BASE}/messages", headers=headers, json=data, timeout=10)
        resp.raise_for_status()
        reply = resp.json()
        text_score = reply["content"][0]["text"].strip()
        # 提取浮点数
        import re
        match = re.search(r'-?\d+(\.\d+)?', text_score)
        if match:
             # 为了避免模型过度自信，可以人为在这里加一层 Clip
             score = float(match.group(0))
             return max(-1.0, min(1.0, score))
        return 0.0
    except Exception as e:
        print(f"  [LLM Error] 情感分析失败: {e}")
        return 0.0

def test_fetch_jin10_flash():
    """
    测试通过 Mihomo 代理访问金十数据快讯。
    实际工程中，我们会爬取更长时间序列的历史数据。目前仅作单日截面演示。
    """
    print("Testing News API with Local Mihomo Proxy...")
    # 金十的公开快讯接口 (非官方严谨 API，此为演示)
    # 此 API 会返回近期的全球经济快讯
    url = "https://flash-api.jin10.com/get_flash_list?channel=-8200&max_time=0"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "x-app-id": "bV1ulvE2r5H9kK7k", # 常用匿名鉴权头
    }
    
    try:
        resp = requests.get(url, headers=headers, proxies=PROXIES, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        items = data.get("data", [])
        print(f"成功获取 {len(items)} 条最新财经快讯。")
        
        results = []
        for item in tqdm(items[:5], desc="Analyzing Sentiment (Top 5)"): # 为减少费用和演示时间，我们只测前5条
            # 判断金十数据的嵌套类型
            if "data" in item and "content" in item["data"]:
                text = item["data"]["content"]
                # 剔除 HTML 标签
                import re
                clean_text = re.sub(r'<[^>]+>', '', text)
                if len(clean_text) > 10:
                    score = analyze_sentiment(clean_text)
                    results.append({
                        "time": item.get("time"),
                        "text": clean_text[:100] + "...",
                        "sentiment": score
                    })
        
        print("\n=== 今日情绪因子样本 ===")
        for r in results:
            print(f"[{r['sentiment']}] {r['text'][:60]}")
            
    except Exception as e:
        print(f"爬取失败，请检查本机 17890 代理是否畅通: {e}")

if __name__ == "__main__":
    test_fetch_jin10_flash()
