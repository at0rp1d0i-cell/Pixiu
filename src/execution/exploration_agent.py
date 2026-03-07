import uuid
import os
import json
import re
from langchain_openai import ChatOpenAI
from src.schemas.research_note import FactorResearchNote, ExplorationQuestion
from src.schemas.exploration import ExplorationRequest, ExplorationResult
from src.execution.docker_runner import DockerRunner

EXPLORATION_SYSTEM_PROMPT = """你是一个量化数据分析师，专门用 Python 探索 A 股市场数据。
你的工作是回答研究员的探索性问题，帮助他们验证假设。

可用数据：
- Qlib 数据库（路径：/data/qlib_bin/）
- 字段：$close, $open, $high, $low, $volume, $factor（复权因子）
- 股票池：沪深300 (csi300)
- 时间范围：2021-01-01 至 2025-03-31

你的输出必须是可以直接执行的 Python 脚本，最后一行打印一个 JSON 对象：
print("EXPLORATION_RESULT_JSON:" + json.dumps({"findings": "...", "key_statistics": {...}, "refined_formula_suggestion": "...或null"}))

脚本要求：
1. 使用 qlib.data 加载数据，导入 qlib 前先 qlib.init(provider_uri="/data/qlib_bin/")
2. 所有统计必须用真实数据计算，不能虚构数字
3. 脚本执行时间不超过 60 秒
4. 如果有公式建议，必须是合法的 Qlib 表达式（只用已知算子）
"""

class ExplorationAgent:
    def __init__(self):
        # Fallback to general openai keys if specific researcher keys are missing
        self.llm = ChatOpenAI(
            model=os.getenv("RESEARCHER_MODEL", os.getenv("OPENAI_MODEL", "deepseek-chat")),
            base_url=os.getenv("RESEARCHER_BASE_URL", os.getenv("OPENAI_API_BASE")),
            api_key=os.getenv("RESEARCHER_API_KEY", os.getenv("OPENAI_API_KEY")),
            temperature=0.3,  # 低温度，代码生成要精确
        )
        self.runner = DockerRunner()

    async def explore(
        self,
        note: FactorResearchNote,
        question: ExplorationQuestion,
    ) -> ExplorationResult:
        request_id = str(uuid.uuid4())

        # Step 1: 生成 EDA 脚本
        prompt = self._build_prompt(note, question)
        # Using a simple list of messages directly
        messages = [
            {"role": "system", "content": EXPLORATION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
        response = await self.llm.ainvoke(messages)
        script = self._extract_script(response.content)

        # Step 2: Docker 沙箱执行
        exec_result = await self.runner.run_python(
            script=script,
            timeout_seconds=120,
        )

        # Step 3: 解析结果
        if exec_result.success:
            output = {}
            for line in exec_result.stdout.split("\n"):
                if line.startswith("EXPLORATION_RESULT_JSON:"):
                    try:
                        output = json.loads(line.replace("EXPLORATION_RESULT_JSON:", ""))
                    except Exception:
                        pass
                    break
                    
            return ExplorationResult(
                request_id=request_id,
                note_id=note.note_id,
                success=True,
                script_used=script,
                findings=output.get("findings", ""),
                key_statistics=output.get("key_statistics", {}),
                refined_formula_suggestion=output.get("refined_formula_suggestion"),
            )
        else:
            return ExplorationResult(
                request_id=request_id,
                note_id=note.note_id,
                success=False,
                script_used=script,
                findings="",
                key_statistics={},
                error_message=(exec_result.stderr or exec_result.stdout)[:500],
            )

    def _build_prompt(self, note: FactorResearchNote, q: ExplorationQuestion) -> str:
        fields_str = ', '.join(q.required_fields) if q.required_fields else '无特定要求'
        return f"""研究背景：{note.hypothesis}
初步公式方向：{note.proposed_formula}

探索问题：{q.question}
建议分析方式：{q.suggested_analysis}
需要的数据字段：{fields_str}

请生成一个 Python EDA 脚本回答这个问题。"""

    def _extract_script(self, content: str) -> str:
        """从 LLM 输出中提取 Python 代码块"""
        match = re.search(r"```python\s*(.*?)```", content, re.DOTALL)
        if match:
            return match.group(1).strip()
        # 如果没有代码块，尝试整体作为脚本
        return content.strip()
