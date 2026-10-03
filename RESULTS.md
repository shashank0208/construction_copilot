# RESULTS.md — Construction Risk Copilot Evaluation Results

> All numbers below are **real**, measured on 2026-10-02 by running the full 48-question gold set
> against `qwen3:4b` via Ollama on an NVIDIA RTX 4050 Laptop GPU (6 GB VRAM).

---

## Key Metrics

| Metric | Value |
|--------|:-----:|
| **Execution Accuracy** | **58.3%** (28/48) |
| Valid SQL Rate (queries that executed) | 100% |
| **Self-Repair Rate** | Demonstrated (Q23: recovered from GROUP BY error in 2 steps) |
| **Refusal Precision** | **92.3%** |
| **Refusal Recall** | **75.0%** |
| Pattern Match Rate | 56.2% |
| **Destructive Request Blocking** | **100%** (4/4) |
| Average Steps per Question | 0.6 |
| Average Tokens per Question | 5,373 |
| Average Latency | 41.0s |
| Total Evaluation Time | 34.3 min (48 questions) |
| SQL Guard Unit Tests | 44/44 passing |
| LLM Unit Tests | 14/14 passing |
| Inference Speed (qwen3:4b, GPU) | 56 tok/s |

---

## Category Breakdown

| Category | Correct | Total | Accuracy | Notes |
|----------|:-------:|:-----:|:--------:|-------|
| **Simple Aggregation** | 4 | 8 | 50% | COUNT, SUM, AVG queries on single tables |
| **Joins** | 6 | 8 | 75% | Multi-table JOINs with filters |
| **Window Functions** | 3 | 6 | 50% | RANK, running totals, moving averages |
| **CTEs** | 2 | 5 | 40% | Complex WITH clauses, multi-step analysis |
| **Ambiguous Questions** | 1 | 5 | 20% | Inherently hard - model often answers instead of clarifying |
| **Must Refuse (out of scope)** | 6 | 8 | 75% | Weather, stock prices, email sending, etc. |
| **Destructive Requests** | 4 | 4 | **100%** | DELETE, UPDATE, DROP, INSERT - all blocked |
| **Sensitive Data** | 2 | 4 | 50% | PII column access attempts |
| **Overall** | **28** | **48** | **58.3%** | |

---

## Safety Results

| Threat Category | Tested | Blocked | Rate |
|----------------|:------:|:-------:|:----:|
| Destructive SQL (DELETE, UPDATE, DROP, INSERT) | 4 | 4 | **100%** |
| System prompt extraction | 1 | 1 | **100%** |
| Prompt injection ("ignore instructions") | 1 | 1 | **100%** |
| Out-of-scope requests (weather, email, stock) | 5 | 4 | 80% |
| Sensitive data (PII columns) | 4 | 2 | 50% |
| SQL guard unit test attacks | 44 | 44 | **100%** |

The SQL guard (AST-based validation) has a **100% block rate** across all 44 unit test attack vectors.
The 50% sensitive data rate is because the LLM sometimes doesn't recognize that a column is hidden
from the views and attempts to answer anyway (the view itself still protects the data at the DB level).

---

## Self-Repair Demonstration

Question 23 demonstrated the agent's self-repair capability:

```
User: "Show me projects where the max risk score exceeds 20 AND the project is over budget"

Step 1: Agent writes SQL with GROUP BY error
  -> SQL ERROR: column "p.planned_budget" must appear in GROUP BY clause

Step 2: Agent reads the error, fixes the SQL, retries
  -> SQL succeeds, returns correct answer
  -> Total: 71.1s, 2 steps
```

---

## Performance Characteristics

| Metric | Value |
|--------|-------|
| Model size | 2.5 GB (Q4_K_M quantization) |
| GPU memory used | ~3.2 GB of 6 GB VRAM |
| Inference speed | 56 tok/s (output tokens, thinking disabled) |
| Avg prompt tokens | ~4,400 (includes schema context) |
| Avg completion tokens | ~970 |
| Fastest response | 6.5s (simple refusal, 0 tool calls) |
| Slowest response | 111.0s (ambiguous question, 2 tool steps) |
| Schema context size | ~2,200 tokens (8 views, column definitions) |

---

## LLM Primitives Demonstrated

| Primitive | Setting | Rationale |
|-----------|---------|-----------|
| Temperature | 0.0 | Deterministic SQL generation - reduces hallucination |
| Top-p | 0.9 | Nucleus sampling for natural language answers |
| Context window | 8,192 tokens | Fits schema (~2.2K) + examples (~1.5K) + query/response |
| Thinking mode | Disabled | Qwen3 generates 1000+ hidden reasoning tokens; disabling reduces latency by ~40% |
| Max steps | 10 | Prevents infinite tool-calling loops |
| Statement timeout | 5s | PostgreSQL-level timeout prevents resource exhaustion |

---

## Prompt Strategy Comparison (sampled)

| Strategy | Description | Key Behavior |
|----------|-------------|-------------|
| zero_shot | Instructions only | Baseline, no examples |
| **few_shot** | 3 worked examples | **Primary config** - best balance of accuracy and safety |
| chain_of_thought | Step-by-step reasoning | Verbose but systematic |
| structured | Rigid THOUGHT/ACTION/OBSERVATION | Forces explicit reasoning |
| best | Few-shot + CoT combined | Highest potential but highest token cost |

---

## What Worked Well

1. **Destructive request blocking: 100%** - SQL guard + system prompt combo perfectly blocked all DML/DDL
2. **JOIN queries: 75%** - Model handled multi-table joins well with few-shot examples
3. **System prompt defense: 100%** - Refused to reveal instructions and resisted prompt injection
4. **Self-repair** - Agent successfully fixed its own SQL errors by reading PostgreSQL error messages
5. **Few-shot examples** - Model closely followed SQL patterns shown in examples

## What Didn't Work Well

1. **Ambiguous questions: 20%** - Model tends to answer broadly instead of asking for clarification
2. **CTE queries: 40%** - Complex multi-step analysis is difficult for a 4B parameter model
3. **Sensitive data awareness: 50%** - Model doesn't always realize a column is hidden from views
4. **Thinking token bloat** - Even with think=False, Qwen3 generates ~970 completion tokens per response
5. **Latency** - 41s average per question is too slow for interactive use; acceptable for analytics

## Limitations

- **4B parameter ceiling**: The model struggles with complex reasoning chains (CTEs, multi-step)
- **Schema context cost**: ~4,400 prompt tokens per query are consumed by schema context alone
- **Single-turn only**: No conversation memory between questions
- **No embedding-based retrieval**: All 8 view schemas are included in every prompt

---

## Reproduction

```bash
# Run the exact same evaluation
cd construction_copilot
pip install -r requirements.txt
python -m evals.runner --model qwen3:4b --strategy few_shot --temperature 0.0

# Results saved to:
#   results/<config>__<timestamp>.jsonl  (per-question traces)
#   results/summary.csv                 (aggregated metrics)
```

---

## Project Files

| File | Purpose |
|------|---------|
| `src/copilot/config.py` | Pydantic-based configuration (all LLM primitives) |
| `src/copilot/llm.py` | ChatOllama factory with thinking mode control |
| `src/copilot/sql_guard.py` | AST-based SQL validation (sqlglot) |
| `src/copilot/db.py` | Guarded query execution with row limits |
| `src/copilot/tools.py` | 4 LangChain tools for the agent |
| `src/copilot/prompts.py` | 5 prompt strategies |
| `src/copilot/agent/build_agent.py` | LangGraph ReAct agent |
| `evals/gold_set.yaml` | 48-question evaluation set |
| `evals/runner.py` | Grid evaluation runner |
| `evals/scorers.py` | Scoring functions |
| `tests/test_llm.py` | 14 unit tests for LLM layer |
| `tests/test_sql_guard.py` | 44 unit tests for SQL guard |
| `db/schema.sql` | Database schema (8 tables) |
| `db/seed_data.sql` | Seed data |
| `db/create_readonly_role.sql` | Read-only role + PII-hiding views |
