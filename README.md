# Construction Risk Copilot

**An Evaluated Text-to-SQL Agent with Local Open-Source LLMs**

Ask construction analytics questions in plain English. The agent writes safe SQL, queries a PostgreSQL database, and returns grounded answers — all powered by a locally-hosted open-source LLM running on your GPU.

```
You:   "Which projects are over budget?"

Agent: 3 projects are over budget:
       - Harbor Bridge Rehabilitation (+11.4%)
       - Central Park Pavilion (+7.8%)
       - Downtown Parking Structure (+7.4%)

       [SQL: SELECT project_name, planned_budget, actual_cost,
             ROUND((actual_cost - planned_budget) / planned_budget * 100, 1) AS pct_over
             FROM v_projects WHERE actual_cost > planned_budget ORDER BY pct_over DESC]
```

---

## Problem Statement

Construction projects generate massive amounts of cost, schedule, and risk data stored across relational databases. Project managers and executives need fast answers — _"Which projects are over budget?"_, _"What are our highest risks?"_, _"Show me the monthly spending trend"_ — but writing SQL queries requires technical expertise.

This project builds an **AI-powered analytics copilot** that:

1. Accepts natural-language business questions
2. Uses a **tool-calling LLM agent** (ReAct pattern) to decide which tools to call
3. Writes and executes **safe, read-only SQL** against a PostgreSQL database
4. **Self-repairs** SQL errors by reading error messages and retrying
5. Returns answers grounded in actual query results — no hallucinated data
6. **Refuses** destructive requests (DELETE, DROP), out-of-scope questions, and PII access

The entire system runs **locally on consumer hardware** — no cloud APIs, no API keys, no data leaves your machine.

---

## Key Results (Measured)

| Metric | Value |
|--------|:-----:|
| Execution Accuracy | **58.3%** (28/48 questions) |
| Destructive Request Blocking | **100%** (4/4) |
| Refusal Precision | **92.3%** |
| Refusal Recall | **75.0%** |
| SQL Guard Unit Tests | **44/44** passing |
| Total Unit Tests | **58/58** passing |
| Inference Speed | **56 tok/s** (GPU) |
| Self-Repair | Demonstrated (auto-fixes SQL errors) |

See [RESULTS.md](RESULTS.md) for full evaluation details, category breakdowns, and analysis.

---

## Tech Stack

| Component | Technology | Version |
|-----------|------------|---------|
| **LLM** | [Qwen3 4B](https://huggingface.co/Qwen/Qwen3-4B) via [Ollama](https://ollama.com) | Q4_K_M quantization |
| **Agent Framework** | [LangGraph](https://github.com/langchain-ai/langgraph) + [LangChain](https://github.com/langchain-ai/langchain) | LangGraph 1.2, LangChain 1.4 |
| **Database** | [PostgreSQL](https://www.postgresql.org/) | 17.x |
| **SQL Security** | [sqlglot](https://github.com/tobymao/sqlglot) (AST-based validation) | 30.21 |
| **Configuration** | [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) | 2.x |
| **Testing** | [pytest](https://docs.pytest.org/) | 9.x |
| **Evaluation** | Custom harness (YAML gold set, JSONL traces, CSV summary) | — |
| **Language** | Python | 3.11+ |

---

## Hardware Requirements

### Minimum (tested on)

| Component | Spec |
|-----------|------|
| **GPU** | NVIDIA RTX 4050 Laptop (6 GB VRAM) |
| **RAM** | 16 GB |
| **Storage** | ~5 GB free (model + database + packages) |
| **OS** | Windows 10/11, Linux, or macOS |

### GPU Notes

- **With GPU (NVIDIA, 4+ GB VRAM)**: ~56 tok/s, 41s avg per question
- **CPU-only**: Will work but much slower (~5-10 tok/s, ~200s per question)
- The model uses ~3.2 GB VRAM with Q4_K_M quantization

---

## Project Structure

```
construction_copilot/
├── src/copilot/                  # Main application code
│   ├── config.py                 # Pydantic-based configuration (LLM primitives)
│   ├── llm.py                    # ChatOllama factory (temperature, top_p, thinking mode)
│   ├── sql_guard.py              # AST-based SQL validation (sqlglot)
│   ├── db.py                     # Guarded query execution + schema introspection
│   ├── tools.py                  # 4 LangChain tools (list_tables, get_schema, run_sql, clarify)
│   ├── prompts.py                # 5 prompt strategies (zero_shot, few_shot, CoT, structured, best)
│   ├── cli.py                    # Command-line interface for testing
│   ├── smoke_test_tools.py       # Tool-calling verification
│   └── agent/
│       └── build_agent.py        # LangGraph ReAct agent with step tracing
├── db/
│   ├── schema.sql                # Database schema (8 tables, 89 columns)
│   ├── seed_data.sql             # Sample construction project data
│   └── create_readonly_role.sql  # Read-only role + PII-hiding views
├── evals/
│   ├── gold_set.yaml             # 48-question evaluation set (8 categories)
│   ├── runner.py                 # Grid evaluation runner (models × strategies × temps)
│   └── scorers.py                # Scoring: accuracy, refusal, groundedness
├── tests/
│   ├── test_llm.py               # 14 unit tests for LLM layer
│   ├── test_sql_guard.py         # 44 unit tests for SQL security
│   ├── e2e_test.py               # 3-question end-to-end agent test
│   └── live_test_db.py           # Live database integration test
├── results/                      # Evaluation output (JSONL traces + summary CSV)
├── requirements.txt              # Pinned Python dependencies
├── .env.example                  # Template for environment variables
├── .gitignore                    # Git ignore rules
└── RESULTS.md                    # Full evaluation results with real numbers
```

---

## Setup & Installation

### Prerequisites

1. **Python 3.11+** — [Download](https://www.python.org/downloads/)
2. **PostgreSQL 17** — [Download](https://www.postgresql.org/download/)
3. **Ollama** — [Download](https://ollama.com/download)
4. **NVIDIA GPU drivers** (optional, for GPU acceleration) — [Download](https://www.nvidia.com/Download/index.aspx)

### Step 1: Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/construction-risk-copilot.git
cd construction-risk-copilot
```

### Step 2: Install Python Dependencies

```bash
# Create a virtual environment (recommended)
python -m venv .venv

# Activate it
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# Install packages
pip install -r requirements.txt
```

### Step 3: Install and Pull the LLM Model

```bash
# Install Ollama from https://ollama.com/download, then:
ollama pull qwen3:4b
```

Verify it's working:
```bash
ollama run qwen3:4b "Say hello"
```

### Step 4: Set Up PostgreSQL Database

```bash
# Connect to PostgreSQL as superuser
psql -U postgres

# Create the database
CREATE DATABASE construction_risk;
\q

# Load the schema and seed data
psql -U postgres -d construction_risk -f db/schema.sql
psql -U postgres -d construction_risk -f db/seed_data.sql

# Create the read-only role and PII-hiding views
psql -U postgres -d construction_risk -f db/create_readonly_role.sql
```

### Step 5: Configure Environment Variables

```bash
# Copy the example and edit with your values
cp .env.example .env
```

Edit `.env` with your PostgreSQL password:
```ini
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/construction_risk
DATABASE_URL_READONLY=postgresql://copilot_reader:copilot_readonly@localhost:5432/construction_risk
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:4b
LLM_TEMPERATURE=0.0
LLM_TOP_P=0.9
LLM_NUM_CTX=8192
LLM_ENABLE_THINKING=false
```

### Step 6: Verify Everything Works

```bash
# Run unit tests (no database or LLM needed)
python -m pytest tests/test_llm.py tests/test_sql_guard.py -v

# Expected: 58 passed

# Run the CLI (needs Ollama running)
python -m copilot.cli "How many projects are in the database?"

# Run end-to-end test (needs Ollama + PostgreSQL)
python tests/e2e_test.py
```

---

## Usage

### CLI Mode

```bash
# Ask a question
python -m copilot.cli "Which projects are over budget?"

# With custom model settings
python -m copilot.cli "Show me the highest risks" --temperature 0.3
```

### Run the Evaluation

```bash
# Full 48-question evaluation (takes ~35 minutes)
python -m evals.runner --model qwen3:4b --strategy few_shot --temperature 0.0

# Quick test (specific categories only)
python -m evals.runner --categories simple_agg,destructive --max-questions 5

# Compare prompt strategies
python -m evals.runner --strategy zero_shot
python -m evals.runner --strategy chain_of_thought
python -m evals.runner --strategy best
```

Results are saved to:
- `results/<config>__<timestamp>.jsonl` — Per-question traces
- `results/summary.csv` — Aggregated metrics

### Tool-Calling Smoke Test

```bash
# Verify the LLM can produce tool calls
python -m copilot.smoke_test_tools
```

---

## Architecture

```
                    ┌──────────────┐
                    │  User Query  │
                    │  (English)   │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  System      │
                    │  Prompt      │◄── 5 strategies (zero_shot, few_shot, CoT, ...)
                    │  + Schema    │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  Qwen3 4B    │
                    │  (Ollama)    │◄── temperature=0.0, top_p=0.9, ctx=8192
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐         ┌─────────────────┐
                    │  LangGraph   │────────►│  Tool Execution  │
                    │  ReAct Loop  │◄────────│  (list_tables,   │
                    │  (max 10     │         │   get_schema,    │
                    │   steps)     │         │   run_sql_query, │
                    └──────┬───────┘         │   ask_clarify)   │
                           │                 └────────┬─────────┘
                           │                          │
                    ┌──────▼───────┐         ┌────────▼─────────┐
                    │  Final       │         │  SQL Guard       │
                    │  Answer      │         │  (sqlglot AST)   │
                    │  (grounded)  │         │  + Read-Only     │
                    └──────────────┘         │  PostgreSQL Role │
                                             └──────────────────┘
```

---

## Safety Layers

| Layer | Mechanism | What It Blocks |
|-------|-----------|----------------|
| **1. System Prompt** | Safety rules + examples | Out-of-scope, hallucination |
| **2. SQL Guard (AST)** | sqlglot parse + allow-list | INSERT, UPDATE, DELETE, DROP, system catalogs |
| **3. DB Role** | `copilot_reader` (SELECT only) | Any write operation at DB level |
| **4. PII Views** | `v_*` views hide columns | email, phone, client_name, project_manager |
| **5. Timeouts** | 5s statement timeout | Resource exhaustion, slow queries |
| **6. Row Limits** | 200 row max | Memory exhaustion |

---

## LLM Primitives Demonstrated

| Primitive | Setting | Why |
|-----------|---------|-----|
| **Temperature** | 0.0 | Deterministic SQL — same question → same query every time |
| **Top-p** | 0.9 | Nucleus sampling for natural language diversity in answers |
| **Context Window** | 8,192 tokens | Fits schema (~2.2K) + examples (~1.5K) + conversation |
| **Thinking Mode** | Disabled | Qwen3 generates 1000+ hidden reasoning tokens; disabling cuts latency ~40% |
| **Token Budgeting** | ~5,373 tokens/query | Measured: prompt ~4,400 + completion ~970 |

---

## Evaluation Categories

| Category | Count | Tests |
|----------|:-----:|-------|
| Simple Aggregation | 8 | COUNT, SUM, AVG on single tables |
| JOINs | 8 | Multi-table queries with filters |
| Window Functions | 6 | RANK, running totals, moving averages |
| CTEs | 5 | Complex WITH clauses |
| Ambiguous | 5 | Vague questions needing clarification |
| Must Refuse | 8 | Weather, stocks, email — outside DB scope |
| Destructive | 4 | DELETE, UPDATE, DROP, INSERT |
| Sensitive | 4 | PII column access attempts |
| **Total** | **48** | |

---

## License

This project is for educational and portfolio purposes.

---

## Author

Built as a portfolio project demonstrating AI engineering skills: local LLM deployment, tool-using agents, SQL security, prompt engineering, and rigorous evaluation with measured results.
