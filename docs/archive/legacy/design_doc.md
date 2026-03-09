# EvoQuant System Design Document

## 1. Hardware & Environment
- **Local Compute**: RTX 4080 (12GB VRAM).
    - *Implication*: Large LLMs (70B+) must run via API. Small/Medium models (7B-14B) can run locally for tasks like summarization or simple coding.
    - *VectorBT*: GPU acceleration is possible via CuPy, but CPU parallelization is often sufficient for initial stages.
- **Frontend**: Custom Web UI (React + Vite) for maximum extensibility.
- **Backend**: Python (FastAPI/Flask) to orchestrate agents.

## 2. Agent Architecture (The "AI Scientist")

### 2.1 Tool Use & Sandbox
We will NOT let the LLM start from scratch. We will provide a **Standard Library** of tools:
- `data_loader.py`: Standardized data fetching (Yahoo/Binance).
- `indicators.py`: Pre-calculated TA-Lib/pandas-ta wrappers.
- `backtest_engine.py`: A simplified wrapper around VectorBT to avoid boilerplate errors.

### 2.2 The "Agentic" Workflow (Simulating "Claude Code")
**YES, we will implement direct terminal operation.**
Instead of a passive "Chat -> Code" flow, we will build an **Autonomous Loop**:

1.  **Perception**: Agent reads file content + previous execution logs.
2.  **Reasoning**: Agent decides "I need to run this script to see if it works" or "I need to install this library".
3.  **Action (Tool Call)**: Agent outputs a structured command, e.g.:
    ```json
    { "tool": "run_terminal", "command": "python3 strategies/test_strategy.py" }
    ```
4.  **Execution**: Our system executes the command in a subprocess.
5.  **Feedback**: The `stdout/stderr` is fed back to the Agent as a new observation.

**Tech Stack for this**:
- **LiteLLM / OpenAI SDK**: To handle the API calls.
- **Function Calling (Tools)**: We will define `execute_shell`, `write_file`, `read_file` as OpenAI-compatible functions.
- **Safety Sandbox**: Since the Agent has terminal access, we must run this inside a **Docker Container** or a restricted user environment to prevent `rm -rf /`.

### 2.3 Cost Control
- **Coder (High Intelligence)**: DeepSeek-V3 / Claude 3.5 (API). Used only for *writing* core logic.
- **Critic (Logic Check)**: DeepSeek-V3 / Qwen-Max (API).
- **Summarizer (Compression)**: Local Qwen-7B (4bit quantized) on RTX 4080. Used to compress 1000 lines of logs into a 5-line error summary.

## 3. Roadmap: Phase 1 (MVP)
1.  **Infrastructure**: Setup `EvoQuant` folder, virtual env, and basic `tools/` library.
2.  **The Loop**: Implement a simple Python script that:
    - Asks LLM to write a strategy using `tools.indicators`.
    - Saves it to `strategies/gen_1.py`.
    - Runs `python strategies/gen_1.py`.
    - Captures stdout/stderr.
    - If error -> Feeds error back to LLM -> Rewrite.
3.  **Visualization**: A simple React page polling the `results/` folder to show the latest equity curve.
