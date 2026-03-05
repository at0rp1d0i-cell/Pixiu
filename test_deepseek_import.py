from langchain_deepseek import ChatDeepSeek
try:
    llm = ChatDeepSeek(model="deepseek-reasoner", api_key="sk-123", api_base="https://api.deepseek.com/v1")
    print("SUCCESS")
except Exception as e:
    print(e)
