# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Sistema de gestão de portfólio de investimentos com multi-agentes IA em 4 níveis hierárquicos (Goldman Sachs-style), rodando localmente (localhost only, sem autenticação). Todo conteúdo voltado ao usuário deve estar em **Português (BR)** — interface, análises, relatórios, alertas e emails. Inclui 3 bots Telegram (CEO chat + 2 grupos de equipe com debate entre agentes).

## Development Commands

```bash
# Backend
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8002

# Frontend (Vite on port 5173)
cd frontend && npm install && npm run dev

# Frontend lint/build
cd frontend && npm run lint
cd frontend && npm run build

# Scheduler
python -m app.scheduler &

# Tests
python -m pytest tests/
python -m pytest tests/test_agent_audit.py -v # agent audit (real OpenAI calls, gpt-4.1-mini)
python -m pytest tests/test_multiagent_logic.py -v -m "not integration"  # logic unit tests ($0)
python -m pytest tests/test_goldman_agents.py -v -m "not integration"   # goldman expansion tests ($0)
python -m pytest tests/test_multiagent_logic.py -v -m integration        # logic integration (gpt-5.1)
```

## CORS & Vite Proxy

- **CORS origins**: `localhost:3000`, `localhost:5173`, `127.0.0.1:3000`, `127.0.0.1:5173`
- **Vite proxy**: `/api` → `http://127.0.0.1:8002` (in `frontend/vite.config.ts`, `changeOrigin: true`)
- **Tailwind v4**: Uses `@tailwindcss/vite` plugin (not PostCSS) — configured in `vite.config.ts`

## Stack

| Layer | Tech |
|-------|------|
| Backend | Python + FastAPI (port 8002) |
| Frontend | React 18 + Tailwind CSS 4 + Vite + React Query + Recharts + Lucide React |
| Database | SQLite (WAL mode, `portfolio.db`) |
| AI Agents | OpenAI Responses API — 3 níveis hierárquicos com reasoning |
| Email | Gmail SMTP via aiosmtplib + Jinja2 templates |
| Scheduler | APScheduler (prices 1h, lockups daily, analysis Mon 7h, email Mon 10h) |

## Project Structure

| Path | Contents |
|------|----------|
| `app/models/db_models.py` | All SQLAlchemy ORM models (9 tables) |
| `app/schemas/api_schemas.py` | All Pydantic request/response schemas |
| `app/agents/b3_team/` | 5 N2 B3 agents + ticker_analyst (N3) |
| `app/agents/crypto_team/` | 5 N2 Crypto agents + crypto_analyst (N3) |
| `app/agents/cross_team/` | 4 cross-team staff agents (macro, sentiment, compliance, quant) |
| `app/agents/analysis_pipeline.py` | 4-phase Goldman Sachs orchestrator |
| `app/agents/personas.py` | 20 agent personas (names, emojis, voice tones) |
| `app/agents/cro.py` | Chief Risk Officer agent |
| `app/telegram/` | 3 Telegram bots (CEO, Mesa B3, Mesa Crypto) + debate orchestrator |
| `app/services/` | yahoo_scraper, market_data, portfolio_service, token_cost, ticker_resolver, email, progress |
| `app/templates/relatorio_semanal.html` | Jinja2 email template (weekly report) |
| `frontend/src/api/client.ts` | All API call functions + TypeScript interfaces |
| `frontend/src/pages/` | Dashboard, Transacoes, Analises, Alertas, Custos, Config |
| `api_guide/`, `open_ai_docs/` | Reference documentation |
| `tests/` | Test suite (see Testing section below) |

## Frontend — Design System (Financeiro Premium)

Theme: **Sidebar escura (navy) + conteúdo fundo claro (off-white)**. Zero gradientes, zero cantos arredondados.

### Paleta de Cores

| Token | Hex | Uso |
|-------|-----|-----|
| `--color-bg` | `#f8f9fa` | Fundo principal conteúdo |
| `--color-surface` | `#ffffff` | Cards, painéis, tooltip bg |
| `--color-surface-alt` | `#f1f3f5` | Linhas alternadas em tabelas |
| `--color-sidebar` | `#0f172a` | Fundo sidebar (navy escuro) |
| `--color-border` | `#e2e8f0` | Bordas de cards, tabelas, CartesianGrid, tooltip border |
| `--color-border-strong` | `#cbd5e1` | Bordas de inputs |
| `--color-primary` | `#15803d` | Botões, links, ativo sidebar, Ações em charts (verde mercado) |
| `--color-primary-hover` | `#166534` | Hover em botões |
| `--color-primary-light` | `#dcfce7` | Background badges positivos |
| `--color-accent` | `#b8860b` | Destaques premium, CDB em charts (dourado) |
| `--color-text` | `#111827` | Texto principal |
| `--color-text-secondary` | `#6b7280` | Texto secundário |
| `--color-positive` | `#16a34a` | Lucro, sucesso |
| `--color-negative` | `#dc2626` | Prejuízo, erro |
| `--color-info` | `#2563eb` | Crypto em charts, informação |
| (axis ticks) | `#9ca3af` | Eixos em todos os charts |

### Princípios de Design

1. **Cantos retos** — zero `rounded-*` e `border-radius` em todo o frontend
2. **Sem gradientes** — cores sólidas em charts, botões, backgrounds
3. **Sombras sutis** — `box-shadow: 0 1px 3px rgba(0,0,0,0.08)` nos cards brancos
4. **Bordas finas** — `1px solid #e2e8f0` nos cards, inputs, tabelas
5. **Contraste forte** — sidebar escura vs conteúdo claro

### Componentes Utilitários (`frontend/src/components/ui/`)

| Componente | Arquivo | Uso |
|------------|---------|-----|
| **Toast** | `ui/Toast.tsx` | `ToastProvider` (context + portal) + `useToast()` hook. Container `fixed bottom-6 right-6`, auto-dismiss 4s com barra de progresso. Border-left colorida (verde/vermelho/azul) |
| **Skeleton** | `ui/Skeleton.tsx` | Shimmer CSS animation (`#e2e8f0` → `#f1f3f5`). Variantes: `Skeleton`, `SkeletonCard`, `SkeletonTable` |
| **EmptyState** | `ui/EmptyState.tsx` | Ícone em fundo verde claro + título + descrição + CTA opcional |

### PerformanceSection (`frontend/src/components/PerformanceSection.tsx`)

Componente de desempenho no Dashboard: 4 cards de categoria (Total, Ações B3, Crypto, CDB) com P/L % e R$ agregados + barras horizontais por ativo individual ordenadas por `|pnl_brl|` decrescente. Recebe `ativos: Ativo[]` e `resumo: PortfolioResumo` como props.

### AnalysisLiveWidget (`frontend/src/components/AnalysisLiveWidget.tsx`)

Widget SSE de progresso em tempo real. Vive em `Layout.tsx` (always mounted em todas as páginas), NÃO em Dashboard. State `jobId` + listener `CustomEvent('analysis-started')` no Layout. `onDone` callback invalida 4 query keys (`analises`, `portfolio-resumo`, `portfolio-ativos`, `portfolio-alocacao`) via `useQueryClient()`. Timeline colapsável com barra de progresso.

### Charts (Recharts)

Todas as cores de charts derivam da paleta acima. EvolutionChart area fill usa `rgba(21,128,61,0.08)`.

## Architecture — Multi-Agent System (4 Levels, Goldman Sachs-style)

```
N0  CIO "Carlos Mendonça" (gpt-5.2, xhigh) — final allocation decisions
    ├── N1  Head B3 "Marcelo Tavares" (gpt-5.1, high) — coordinates B3 team
    │   ├── N2  Fundamentalista "Ricardo Moura" (gpt-5.1, medium) — financial statements, valuation
    │   ├── N2  Técnico "Bruno Kato" (gpt-4.1) — price action, indicators
    │   ├── N2  Setorial "Beatriz Almeida" (gpt-5.1, medium) — sector rotation, Selic impact
    │   ├── N2  Risk "Patrícia Campos" (gpt-4.1) — concentration, beta → reports to CRO
    │   ├── N2  Trade "Diego Lopes" (gpt-4.1) — entry/exit, sizing
    │   └── N3  TickerAnalyst × N (gpt-5.1, medium) — one per ticker
    ├── N1  Head Crypto "Luísa Nakamoto" (gpt-5.1, high) — coordinates crypto team
    │   ├── N2  Fundamentalista "Thiago Satoshi" (gpt-5.1, medium) — tokenomics, TVL
    │   ├── N2  Técnica "Juliana Pires" (gpt-4.1) — 24/7 technicals, funding rates
    │   ├── N2  On-Chain "Lucas Webb" (gpt-5.1, medium) — whale tracking, exchange flows
    │   ├── N2  Risk "André Faria" (gpt-4.1) — smart contract risk → reports to CRO
    │   ├── N2  Trade "Camila Duarte" (gpt-4.1) — DCA, gas fees, sizing
    │   └── N3  CryptoAnalyst × N (gpt-5.1, medium) — one per crypto
    ├── N1  CRO "Fernando Rocha" (gpt-5.1, high) — cross-asset risk, veto power
    └── Cross-Team Staff:
        ├── N2  Macro "Helena Bastos" (gpt-5.1, high) — Selic, IPCA, câmbio, Fed
        ├── N2  Sentiment "Marina Leal" (gpt-4.1) — news flow, social sentiment
        ├── N2  Compliance "Rafael Tanaka" (gpt-4.1) — CVM, tributação, lockups
        └── N2  Quant "Eduardo Queiroz" (gpt-5.1, medium) — Sharpe, correlation, beta
```

### AnalysisPipeline — 4-Phase Execution ("Morning Meeting")

```
Phase 1 — Intelligence (parallel):  Macro + Sentiment + Risk B3 + Risk Crypto + Compliance
Phase 2 — Team Analysis (parallel): Head B3(+team) ‖ Head Crypto(+team) → N3 deep dives
Phase 3 — Risk Consolidation:       CRO + Quant
Phase 4 — Final Decision:           CIO
```

- **File**: `app/agents/analysis_pipeline.py` — deterministic Python orchestrator (NOT an LLM agent)
- **Budget cap**: `settings.max_cost_per_run_usd` (default $5.00) via `RunBudgetTracker`
- **DB record**: `AnalysisRun` table tracks status, cost, phases completed

### Telegram Integration (3 bots)

| Bot | Chat type | Agent | Commands |
|-----|-----------|-------|----------|
| CEO | Private 1-on-1 | Carlos Mendonça (CIO) | `/analise`, `/portfolio`, `/risco`, `/aporte N`, `/custos` |
| Mesa B3 | Group | Entire B3 team posts with personas | `/analise`, `/ticker PETR4` |
| Mesa Crypto | Group | Entire Crypto team posts with personas | `/analise`, `/moeda bitcoin` |

- **DebateOrchestrator**: detects divergences between agents, triggers rebuttal rounds
- **GroupBroadcaster**: posts formatted messages with persona name/emoji + typing delays
- **Config**: `TELEGRAM_CEO_TOKEN`, `TELEGRAM_MESA_B3_TOKEN`, `TELEGRAM_MESA_CRYPTO_TOKEN` in `.env`

### Orchestrator (N1)

- **Model**: gpt-5.2 | **Reasoning**: xhigh
- **Role**: Coordinates all sub-agents, takes final allocation decisions
- **Portfolio awareness**: Full — queries summary, assets, allocation, macro
- **Execution order**: B3 + Crypto → synthesize final recommendation
- **File**: `app/agents/orchestrator.py`

### B3Agent (N2)

- **Model**: gpt-5.1 | **Reasoning**: high
- **Role**: Maps B3 market via web search, identifies 5-8 promising tickers, delegates deep analysis to TickerAnalyst N3
- **Does NOT access data directly** — calls `analyze_stock_deep()` for each ticker
- **Portfolio awareness**: Receives `portfolio_context` from orchestrator
- **File**: `app/agents/b3_agent.py`

### CryptoAgent (N2)

- **Model**: gpt-5.1 | **Reasoning**: high
- **Role**: Maps crypto market via web search + trending, delegates deep analysis to CryptoAnalyst N3
- **Does NOT access price/history directly** — calls `analyze_crypto_deep()` for each crypto
- **Portfolio awareness**: Receives `portfolio_context` from orchestrator
- **File**: `app/agents/crypto_agent.py`

### TickerAnalyst (N3)

- **Model**: gpt-5.1 | **Reasoning**: medium
- **Role**: Deep analysis of 1 individual B3 stock (fundamentals, technicals, news, sector)
- **Dynamic agent_name**: `ticker_analyst_{TICKER}` (e.g., `ticker_analyst_PETR4`) — each ticker has persistent context via `previous_response_id`
- **File**: `app/agents/ticker_analyst.py`

### CryptoAnalyst (N3)

- **Model**: gpt-5.1 | **Reasoning**: medium
- **Role**: Deep analysis of 1 individual crypto (on-chain, technicals, sentiment, BR regulation)
- **Dynamic agent_name**: `crypto_analyst_{id}` (e.g., `crypto_analyst_bitcoin`) — each crypto has persistent context
- **File**: `app/agents/crypto_analyst.py`

### ticker_resolver (utility)

- **Model**: gpt-4.1 | **Reasoning**: N/A (not supported)
- **Role**: Resolves B3 tickers that changed names via web search (e.g., ELET3 → AXIA3)
- **File**: `app/services/ticker_resolver.py`

## BaseAgent — Agentic Loop

All agents inherit from `BaseAgent` (`app/agents/base_agent.py`) which implements the agentic loop: call model → check for function_calls → execute → feed results back → repeat until text response. Key patterns:
- Uses **OpenAI Responses API** (not Chat Completions): `client.responses.create()`
- **Pattern A** (oficial OpenAI): `input_list` acumulada entre rounds. `previous_response_id` usado **APENAS no round 0** para continuidade cross-execution
- **`max_rounds=10`** default — agentic loop limit per execution
- **`web_search_tool(context_size)`** function with configurable `search_context_size`: N3=`"high"`, N2=`"medium"`, Orchestrator=`"low"`
- **Reasoning effort** per agent: configured in `app/config.py` `settings.reasoning_effort` dict, resolved automatically in `call_model()`. N3 agent names (e.g., `ticker_analyst_PETR4`) resolve to base key (`ticker_analyst`)
- **Parallel function_calls**: When model emits >1 function_call in same round, executed via `ThreadPoolExecutor(max_workers=4)`
- **Persistent context**: `resumo_contexto` (last response text[:2000]) saved to `agent_contexts` table and injected as prefix in next execution's input
- `previous_response_id` for conversation continuity across executions (stored in `agent_contexts` table). Falls back to `resumo_contexto` when stale
- Automatic retry without stale `previous_response_id` on error
- Token costs logged automatically via `app/services/token_cost.py` after each execution
- `job_id` propagated for SSE progress events
- **Sub-agent execution**: Orchestrator calls sub-agents via `_run_sub_agent()` — no timeout, aguarda conclusão com error handling

## Tool Inventory by Agent

| Agent | Tools |
|-------|-------|
| **Orchestrator** (N1) | `web_search`, `get_portfolio_summary`, `get_portfolio_assets`, `get_portfolio_allocation`, `run_b3_analysis`, `run_crypto_analysis`, `get_macro_data` |
| **B3Agent** (N2) | `web_search`, `search_tickers`, `analyze_stock_deep` → spawns TickerAnalyst N3 |
| **CryptoAgent** (N2) | `web_search`, `get_crypto_trending`, `analyze_crypto_deep` → spawns CryptoAnalyst N3 |
| **TickerAnalyst** (N3) | `web_search`, `get_stock_price`, `get_stock_fundamentals`, `get_stock_history`, `get_stock_dividends` |
| **CryptoAnalyst** (N3) | `web_search`, `get_crypto_price`, `get_crypto_history` |
| **ticker_resolver** | `web_search` (via direct Responses API call, not BaseAgent). Uses client singleton (`_get_client()`) |

## Market Data Pipeline

Two external sources, both unauthenticated — **no yfinance dependency**:

- **Yahoo Finance**: Playwright scraper (`app/services/yahoo_scraper.py`) with stealth anti-detection
- **BCB (Banco Central)**: Selic (series 432), CDI (series 12), IPCA (series 433), PTAX exchange rate (series 1)

Scraper anti-detection patterns (validated in stress tests — 112/112 pass):
- `wait_for_function` DOM polling instead of `networkidle`
- `_build_stealth_headers(ua)` — generates matched `sec-ch-ua`/`sec-ch-ua-platform`/`sec-ch-ua-mobile` with UA
- Human-like delays: `random.uniform(1.5, 3.5)` between requests
- Fresh browser per attempt to avoid CAPTCHA
- Cache: SQLite `cache_precos` table with 1h TTL

## Ticker Conventions

- B3 stocks: `PETR4` → `PETR4.SA` (Yahoo suffix added by scraper)
- Crypto: `bitcoin` → `BTC-USD` (via `CRYPTO_IDS` in `market_data.py`)
- CDB: `cdb_liquidez` (internal, no Yahoo ticker)

## Ticker Autocomplete (`GET /api/market/search?q=`)

Busca rápida sem scraping para o formulário de transações. Prioridade:
1. **Ativos locais** — busca na tabela `ativos` (portfolio existente)
2. **Lista estática B3** — ~176 tickers (Ibovespa + small/mid caps por setor)
3. **Lista estática Crypto** — ~93 tokens (top market cap + L1/L2 + DeFi + Gaming + IA + Memes)

Listas definidas em `app/routers/market_data_router.py` (`_B3_TICKERS`, `_CRYPTO_TICKERS`). Retorna `{ticker, nome, origem}`. Frontend debounce 300ms em `Transacoes.tsx`.

## SSE Live Progress

Analysis runs in `BackgroundTasks` (sync threads). Progress events bridge to async SSE via `app/services/progress.py`:
- `register_job(job_id, loop)` — creates `asyncio.Queue` + captures event loop
- `emit(job_id, step, message)` — uses `loop.call_soon_threadsafe(queue.put_nowait, event)` from sync threads
- Frontend connects to `GET /api/analises/stream/{job_id}` (SSE) via `AnalysisLiveWidget.tsx`
- `POST /api/analises/executar` returns `{job_id}` immediately (202)
- N3 agents emit events with agent-specific names (e.g., `agent=ticker_analyst_PETR4`)
- **Widget lives in `Layout.tsx`** (always mounted), NOT in Dashboard — visible on all pages
- `onDone` invalidates 4 query keys (`analises`, `portfolio-resumo`, `portfolio-ativos`, `portfolio-alocacao`) via `useQueryClient()`

## Business Rules

- **Allocation**: 50% ações B3 / 20% crypto / 30% CDB liquidez diária (seeded in `app/database.py:DEFAULT_CONFIGS`)
- **Lock-up**: 30 calendar days after purchase — no sell before
- **CDI**: Auto-fetched from BCB API
- **Profile**: Moderate — blue chips + controlled bets
- **AI autonomy**: AI decides allocations; user executes manually via frontend
- **Email default**: `pedropestana.fgv@gmail.com` (seeded in `DEFAULT_CONFIGS`)

## Database

SQLite with WAL mode and foreign keys enabled (`app/database.py`). Tables auto-created on startup via `Base.metadata.create_all`. Schema reference: `schema.md`.

9 tables: `ativos`, `transacoes`, `portfolio_snapshot`, `analises_ia`, `custos_tokens`, `configuracoes`, `alertas`, `cache_precos`, `agent_contexts`

- **Session management**: `get_db()` generator via FastAPI `Depends()` — yields session, auto-closes
- **Lifespan**: `main.py` creates tables + seeds DEFAULT_CONFIGS on startup; closes Playwright browser pool on shutdown

## API Routes

All prefixed with `/api`. Routers in `app/routers/`:

| Router | Prefix | Key endpoints |
|--------|--------|---------------|
| portfolio | /portfolio | GET / (resumo), /ativos, /alocacao, /evolucao?periodo= |
| transacoes | /transacoes | GET /, POST / (auto lock-up), GET /{id} |
| analises | /analises | GET /, GET /{id}, POST /executar (→ job_id), POST /aporte, GET /stream/{job_id} (SSE) |
| alertas | /alertas | GET /, PATCH /{id}/marcar-lido |
| custos | /custos | GET /, /resumo, /por-agente |
| configuracoes | /configuracoes | GET /, PATCH / |
| market_data | /market | GET /cotacao/{ticker}, /historico/{ticker}, /search?q=, /macro |
| (main.py) | /api | GET /health |

## Scheduler

APScheduler with 4 jobs (`app/scheduler.py`). All jobs use **`America/Sao_Paulo`** (BRT) timezone:
1. **Atualizar preços**: Every 1h (5-min startup delay) — fetches current prices for all portfolio assets
2. **Verificar lockups**: Daily at 08:00 BRT — checks and alerts on expiring lock-ups
3. **Análise semanal**: Monday 07:00 BRT — runs full orchestrator analysis
4. **Email semanal**: Monday 10:00 BRT — sends report via Gmail SMTP

## Testing

| Test file | What it tests | Notes |
|-----------|---------------|-------|
| `tests/test_agent_audit.py` | Multi-agent audit tests | **Real OpenAI calls** (gpt-4.1-mini), ~34s |
| `tests/test_multiagent_logic.py` | Multi-agent logic tests (unit + integration) | Unit: $0, ~2s. Integration: **Real OpenAI calls** (gpt-5.1), ~100s |
| `tests/test_e2e_multiagent.py` | E2E multi-agent hierarchy (scraping + N3/N2 agents + DB) | **Real OpenAI + Yahoo scraping**, ~2-5min |
| `tests/test_browser_concurrency.py` | Browser concurrency (semaphore, memory args, timeouts) | Unit tests with mocks |
| `tests/test_goldman_agents.py` | Goldman expansion: personas, budget, debate, N2 agents, pipeline | Unit tests ($0), ~1s |

## .gitignore

Ignored: `.env`, `__pycache__/`, `.venv/`, `node_modules/`, `*.db`, `checkpoints/`, `lightning_logs/`, `.claude/`, `dist/`

## Environment Variables (.env)

```
OPENAI_API_KEY=
GMAIL_USER=
GMAIL_APP_PASSWORD=
EMAIL_DESTINATARIO=
TELEGRAM_CEO_TOKEN=              # BotFather token for CEO private chat
TELEGRAM_MESA_B3_TOKEN=          # BotFather token for Mesa B3 group bot
TELEGRAM_MESA_CRYPTO_TOKEN=      # BotFather token for Mesa Crypto group bot
TELEGRAM_MESA_B3_CHAT_ID=        # Telegram group chat ID for Mesa B3
TELEGRAM_MESA_CRYPTO_CHAT_ID=    # Telegram group chat ID for Mesa Crypto
```

## Token Cost Tracking

Every OpenAI call is logged to `custos_tokens`: capture `usage.input_tokens`/`output_tokens`, calculate USD cost per model pricing table, convert to BRL using BCB PTAX rate. Exposed in dashboard grouped by agent/period. N3 agents (ticker_analyst_*, crypto_analyst_*) are logged individually per ticker.
