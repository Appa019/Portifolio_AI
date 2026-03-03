# Portfolio AI

Sistema completo de gestão de portfólio de investimentos com **multi-agentes IA em 3 níveis hierárquicos**, **ensemble ML** (XGBoost + BiLSTM-Attention + Temporal Fusion Transformer), e **scraping de dados de mercado em tempo real** via Playwright.

Roda 100% local (localhost, sem autenticação). Toda a interface, análises, relatórios e alertas em **Português (BR)**.

---

## Índice

- [Stack Tecnológico](#stack-tecnológico)
- [Arquitetura Multi-Agentes](#arquitetura-multi-agentes-3-níveis)
- [Ensemble ML](#ensemble-ml)
- [Pipeline de Dados de Mercado](#pipeline-de-dados-de-mercado)
- [Frontend](#frontend)
- [API REST](#api-rest)
- [Banco de Dados](#banco-de-dados)
- [Scheduler](#scheduler)
- [Regras de Negócio](#regras-de-negócio)
- [Setup e Instalação](#setup-e-instalação)
- [Variáveis de Ambiente](#variáveis-de-ambiente)
- [Testes](#testes)
- [Estrutura do Projeto](#estrutura-do-projeto)

---

## Stack Tecnológico

| Camada | Tecnologia | Detalhes |
|--------|------------|----------|
| **Backend** | Python 3.12 + FastAPI | Uvicorn ASGI, port 8002, SQLAlchemy ORM |
| **Frontend** | React 18 + TypeScript | Tailwind CSS 4 (via `@tailwindcss/vite`), Vite 6, React Query, Recharts, Lucide React |
| **Database** | SQLite | WAL mode, foreign keys, 9 tabelas, indexes otimizados |
| **Agentes IA** | OpenAI Responses API | gpt-5.2 (N1) + gpt-5.1 (N2/N3), reasoning configurável por agente |
| **ML Ensemble** | XGBoost + BiLSTM + TFT | GPU CUDA 12.1, stacking meta-learner, walk-forward validation |
| **Scraping** | Playwright Chromium | Headless, anti-detecção (stealth headers, fingerprint rotation), semáforo de concorrência |
| **Email** | Gmail SMTP | aiosmtplib + Jinja2 templates, relatório semanal |
| **Scheduler** | APScheduler | 4 jobs automáticos (preços, lockups, análise, email) |

### Dependências Principais

**Backend**: FastAPI, SQLAlchemy, OpenAI SDK, Playwright, Pandas, NumPy, scikit-learn, XGBoost, PyTorch, PyTorch Lightning, PyTorch Forecasting, Optuna, APScheduler, aiosmtplib, Jinja2

**Frontend**: React 18, React Router 7, TanStack React Query 5, Recharts 2, Axios, Lucide React, Tailwind CSS 4

---

## Arquitetura Multi-Agentes (3 Níveis)

O sistema utiliza uma hierarquia de agentes IA especializados que se coordenam automaticamente:

```
N1  Orchestrator (gpt-5.2, reasoning=xhigh)
│   Consciência total do portfólio. Coordena sub-agentes, toma decisões finais.
│
├── N2  B3Agent (gpt-5.1, reasoning=high)
│   │   Mapeia mercado B3 via web search. Identifica 5-8 tickers promissores.
│   │   NÃO acessa dados diretamente — delega a N3.
│   │
│   └── N3  TickerAnalyst × N (gpt-5.1, reasoning=medium)
│           Um agente por ticker: ticker_analyst_PETR4, ticker_analyst_VALE3, ...
│           Análise profunda: fundamentos, técnico, notícias, setor.
│           Contexto persistente entre execuções via previous_response_id.
│
├── N2  CryptoAgent (gpt-5.1, reasoning=high)
│   │   Mapeia mercado crypto via web search + trending.
│   │   NÃO acessa preço/histórico diretamente — delega a N3.
│   │
│   └── N3  CryptoAnalyst × N (gpt-5.1, reasoning=medium)
│           Um agente por crypto: crypto_analyst_bitcoin, crypto_analyst_ethereum, ...
│           Análise profunda: on-chain, técnico, sentimento, regulação BR.
│
└── N2  StatsAgent (gpt-5.1, reasoning=none)
        Roda APÓS B3 e Crypto (precisa dos tickers recomendados).
        Análise quantitativa pura + ensemble ML predictions.
        └── EnsemblePipeline: XGBoost + BiLSTM-Attention + TFT
```

### Fluxo de Execução

1. **Orchestrator** consulta portfólio, alocação e dados macro
2. **B3Agent** + **CryptoAgent** executam em paralelo, cada um delegando a múltiplos N3
3. **StatsAgent** executa após B3/Crypto, usando os tickers identificados
4. **Orchestrator** sintetiza tudo em recomendação final JSON

### Características do Agentic Loop (BaseAgent)

- **OpenAI Responses API** (não Chat Completions): `client.responses.create()`
- **Pattern A**: `input_list` acumulada entre rounds, `previous_response_id` apenas no round 0 para continuidade cross-execution
- **Parallel function calls**: `ThreadPoolExecutor(max_workers=4)` quando o modelo emite >1 tool call
- **Contexto persistente**: `resumo_contexto` (últimos 2000 chars) salvo em `agent_contexts` e injetado como prefixo na próxima execução
- **Web search** com `search_context_size` configurável: N3=`"high"`, N2=`"medium"`, Orchestrator=`"low"`
- **Reasoning effort** por agente: configurado em `app/config.py`, resolvido automaticamente (nomes dinâmicos N3 → base key)
- **Sub-agent timeouts**: 10 min via `ThreadPoolExecutor` no Orchestrator
- **Token costs**: logados automaticamente após cada execução (modelo, tokens in/out, custo USD/BRL)

### Ferramentas por Agente

| Agente | Ferramentas |
|--------|-------------|
| **Orchestrator** (N1) | `web_search`, `get_portfolio_summary`, `get_portfolio_assets`, `get_portfolio_allocation`, `run_b3_analysis`, `run_crypto_analysis`, `run_stats_analysis`, `get_macro_data` |
| **B3Agent** (N2) | `web_search`, `search_tickers`, `analyze_stock_deep` (spawna TickerAnalyst N3) |
| **CryptoAgent** (N2) | `web_search`, `get_crypto_trending`, `analyze_crypto_deep` (spawna CryptoAnalyst N3) |
| **TickerAnalyst** (N3) | `web_search`, `get_stock_price`, `get_stock_fundamentals`, `get_stock_history`, `get_stock_dividends` |
| **CryptoAnalyst** (N3) | `web_search`, `get_crypto_price`, `get_crypto_history` |
| **StatsAgent** (N2) | `get_stock_history`, `get_crypto_history`, `get_macro_data`, `calculate_stats`, `train_ensemble`, `predict_ensemble` |

---

## Ensemble ML

Otimizado para **GPU NVIDIA com CUDA** (desenvolvido/testado em RTX 2070 SUPER 8GB VRAM).

### Arquitetura

```
Dados brutos (OHLCV + Macro)
    │
    ▼
Feature Engineering (~50 features)
    │
    ├── XGBoost (GPU) ──────────────────── ALL ~50 features
    │
    ├── BiLSTM-Attention (FP16 GPU) ────── ~35 neural features
    │                                       (select_features() remove 14 redundantes)
    ├── TFT (FP32 GPU) ────────────────── ~35 neural features
    │
    ▼
Stacking Meta-Learner (XGBoost CPU)
    │
    ▼
Predição final: retorno_previsto_pct, direção, confiança
```

### Features

**6 tiers** de features técnicas e fundamentais:

| Tier | Features | Exemplos |
|------|----------|----------|
| 1 — Retornos | 5 | returns_1d, returns_5d, returns_20d, log_return, volatility_20d |
| 2 — Médias Móveis | 6 | sma_20, sma_50, ema_10, ema_20, ema10_ema20_ratio, sma20_sma50_cross |
| 3 — Momentum | 6 | rsi_14, macd, macd_signal, macd_histogram, stoch_k, stoch_d |
| 4 — Volume | 5 | volume_sma_20, volume_ratio, obv, vwap_ratio, mfi_14 |
| 5 — Volatilidade | 6 | bb_upper, bb_lower, bb_width, atr_14, atr_ratio, keltner_width |
| 6 — Macro (opcional) | 4 | selic_level, selic_change_3m, ipca_12m (multiplicativo), ptax_change_20d |

### Validação

- **Walk-forward temporal** com embargo (nunca random split)
- Mínimos: 252 treino, 80 validação, 80 teste
- Target: **retornos** (não preços). Scaler fit apenas no treino
- Zona neutra: `|pred| < 0.1%` → direção `"neutra"`
- Confiança: score exponencial baseado em dispersão × agreement entre learners
- **Fallback 2-learner**: se TFT < 20 predições válidas no val → stacking usa só XGBoost + BiLSTM
- **Cascading fallback**: ensemble → média → zero (validação NaN/inf)

### Controles de Recursos

- FP16 mixed precision para BiLSTM (FP32 no CPU), **FP32 obrigatório para TFT** (attention mask -1e9 overflow)
- VRAM monitoring: `_vram_stats()`, `_check_vram_budget()`, `_clear_vram()`
- Adaptive batch size baseado em VRAM livre
- Cache inteligente: `is_model_fresh(ticker, 7 dias)`, pula retreino se modelo é recente
- Feature importance: top 15 XGBoost logado + SSE + salvo em `meta.json`

---

## Pipeline de Dados de Mercado

Duas fontes externas, ambas sem autenticação:

### Yahoo Finance (Playwright Scraper)

Scraper headless em `app/services/yahoo_scraper.py` com anti-detecção validada em stress test (112/112 pass):

- **Stealth headers**: `_build_stealth_headers(ua)` gera `sec-ch-ua`/`sec-ch-ua-platform`/`sec-ch-ua-mobile` casados com o User-Agent
- **DOM polling**: `wait_for_function` em vez de `networkidle` (mais confiável)
- **Browser novo por tentativa**: evita CAPTCHA acumulado
- **Delay humano**: `random.uniform(1.5, 3.5)` entre requests
- **Concorrência controlada**: `threading.Semaphore(10)` — máximo 10 browsers Chromium simultâneos
- **Chromium memory args**: `--js-flags=--max-old-space-size=256` + 8 flags adicionais (~250MB/processo)
- **Estratégia progressiva de retry**: direto → warm-up via homepage → backoff exponencial
- **Cache**: tabela `cache_precos` com TTL de 1h

**Funções disponíveis**: `scrape_quote`, `scrape_history`, `scrape_financials` (income/balance/cashflow), `scrape_analysis`, `scrape_key_statistics`, `scrape_news`, `scrape_press_releases`, `scrape_multiple`

### BCB (Banco Central do Brasil)

Séries históricas via API pública:

| Série | ID | Uso |
|-------|----|-----|
| Selic | 432 | Taxa de juros meta |
| CDI | 12 | Rendimento CDB |
| IPCA | 433 | Inflação (acumulado 12m, cálculo multiplicativo) |
| PTAX | 1 | Câmbio USD/BRL (cache em memória 5min, thread-safe) |

### Convenções de Tickers

| Tipo | Local | Yahoo Finance |
|------|-------|---------------|
| Ações B3 | `PETR4` | `PETR4.SA` |
| Crypto | `bitcoin` | `BTC-USD` |
| CDB | `cdb_liquidez` | (interno, sem ticker Yahoo) |

### Autocomplete de Tickers

`GET /api/market/search?q=` — busca rápida sem scraping:
1. Ativos do portfólio (DB local)
2. Lista estática B3 (~176 tickers: Ibovespa + small/mid caps por setor)
3. Lista estática Crypto (~93 tokens: top market cap + L1/L2 + DeFi + Gaming + IA + Memes)

---

## Frontend

**Design system**: Financeiro Premium — sidebar navy escura + conteúdo fundo claro off-white.

### Paleta de Cores

| Token | Hex | Uso |
|-------|-----|-----|
| Background | `#f8f9fa` | Fundo principal conteúdo |
| Surface | `#ffffff` | Cards, painéis |
| Sidebar | `#0f172a` | Sidebar navy escuro |
| Primary | `#15803d` | Botões, links, ações em charts (verde mercado) |
| Accent | `#b8860b` | Destaques premium, CDB em charts (dourado) |
| Info | `#2563eb` | Crypto em charts |
| Positive | `#16a34a` | Lucro, sucesso |
| Negative | `#dc2626` | Prejuízo, erro |

### Princípios

- **Cantos retos** — zero `border-radius` em todo o frontend
- **Sem gradientes** — cores sólidas em charts, botões, backgrounds
- **Sombras sutis** — `box-shadow: 0 1px 3px rgba(0,0,0,0.08)` nos cards
- **Bordas finas** — `1px solid #e2e8f0`
- **Contraste forte** — sidebar escura vs conteúdo claro

### Páginas

| Página | Rota | Descrição |
|--------|------|-----------|
| **Dashboard** | `/` | Resumo do portfólio, alocação, evolução patrimonial, performance por ativo |
| **Transações** | `/transacoes` | CRUD de compras/vendas com autocomplete de tickers (debounce 300ms) |
| **Análises** | `/analises` | Histórico de análises IA, botão executar, widget SSE de progresso |
| **Alertas** | `/alertas` | Alertas de lock-up, desvio de alocação, oportunidades |
| **Custos** | `/custos` | Custos de tokens por agente, modelo e período |
| **Configurações** | `/config` | Alocação alvo, email, perfil de risco |

### Componentes Principais

| Componente | Descrição |
|------------|-----------|
| `PerformanceSection` | 4 cards de categoria (Total, Ações, Crypto, CDB) + barras horizontais por ativo |
| `AnalysisLiveWidget` | SSE de progresso em tempo real (vive no Layout, visível em todas as páginas) |
| `AllocationChart` | Gráfico de alocação atual vs alvo |
| `EvolutionChart` | Evolução patrimonial ao longo do tempo |
| `AssetTable` | Tabela de ativos com P&L, preço, lock-up |
| `Toast` | Notificações com auto-dismiss 4s e barra de progresso |
| `Skeleton` | Loading states com shimmer animation |
| `EmptyState` | Estado vazio com ícone, título e CTA |

### SSE (Server-Sent Events)

O progresso das análises é transmitido em tempo real:

1. `POST /api/analises/executar` retorna `{job_id}` imediatamente (HTTP 202)
2. Frontend conecta em `GET /api/analises/stream/{job_id}` via `EventSource`
3. `AnalysisLiveWidget` mostra timeline colapsável com barra de progresso
4. Cada agente N3 emite eventos com nome específico (ex: `agent=ticker_analyst_PETR4`)
5. `onDone` invalida 4 query keys para refresh automático do dashboard

---

## API REST

Todos os endpoints sob `/api`. Backend em `http://127.0.0.1:8002`, frontend proxy via Vite.

### Portfolio (`/api/portfolio`)

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/` | Resumo: valor total, rentabilidade, alocação por classe |
| `GET` | `/ativos` | Lista detalhada de todos os ativos (preço, P&L, lock-up) |
| `GET` | `/alocacao` | Alocação atual vs alvo com desvios |
| `GET` | `/evolucao?periodo=` | Evolução patrimonial no período |

### Transações (`/api/transacoes`)

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/` | Lista transações (com `joinedload` para evitar N+1) |
| `POST` | `/` | Nova transação (auto lock-up 30 dias para compras) |
| `GET` | `/{id}` | Detalhe de uma transação |

### Análises (`/api/analises`)

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/` | Histórico de análises |
| `GET` | `/{id}` | Detalhe de uma análise |
| `POST` | `/executar` | Inicia análise completa (retorna `job_id`, HTTP 202) |
| `POST` | `/aporte` | Análise de alocação de novo aporte |
| `GET` | `/stream/{job_id}` | SSE de progresso em tempo real |

### Alertas (`/api/alertas`)

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/` | Lista alertas |
| `PATCH` | `/{id}/marcar-lido` | Marca alerta como lido |

### Custos (`/api/custos`)

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/` | Lista completa de custos de tokens |
| `GET` | `/resumo` | Resumo agregado por período |
| `GET` | `/por-agente` | Custos agrupados por agente |

### Configurações (`/api/configuracoes`)

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/` | Todas as configurações |
| `PATCH` | `/` | Atualiza configurações |

### Market Data (`/api/market`)

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/cotacao/{ticker}` | Cotação atual de um ativo |
| `GET` | `/historico/{ticker}` | Histórico OHLCV |
| `GET` | `/search?q=` | Autocomplete de tickers (sem scraping) |
| `GET` | `/macro` | Dados macroeconômicos (Selic, CDI, IPCA, PTAX) |

### Health

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/api/health` | Health check |

---

## Banco de Dados

SQLite com WAL mode e foreign keys habilitados. 9 tabelas auto-criadas no startup. Schema completo em `schema.md`.

### Tabelas

| Tabela | Descrição | Registros típicos |
|--------|-----------|-------------------|
| `ativos` | Cadastro de ativos (ações, cryptos, CDB) | ~10-30 |
| `transacoes` | Compras e vendas | ~50-200 |
| `portfolio_snapshot` | Snapshots periódicos do portfólio | ~100+/mês |
| `analises_ia` | Histórico de análises dos agentes | ~4-8/semana |
| `custos_tokens` | Log de cada chamada OpenAI | ~50-100/análise |
| `configuracoes` | Parâmetros do sistema (7 defaults) | 7 |
| `alertas` | Alertas de lock-up, desvio, oportunidades | variável |
| `cache_precos` | Cache de dados externos (TTL 1h) | ~50-100 |
| `agent_contexts` | Contexto persistente entre execuções | 1 por agente |

### Indexes

7 indexes otimizados para os queries mais frequentes:

- `ix_transacao_ativo_data` — (ativo_id, data_operacao)
- `ix_snapshot_data` — (data)
- `ix_analise_data`, `ix_analise_agente` — buscas por data e agente
- `ix_custo_agente_data` — custos por agente/período
- `ix_alerta_lido_data` — alertas não lidos por data
- `ix_cache_precos_lookup` — **UNIQUE** (ticker, fonte, tipo_dado) — previne duplicatas

### Concorrência

- **PTAX**: `threading.Lock()` para cache em memória thread-safe
- **Cache upsert**: `IntegrityError` handling para race condition com UNIQUE constraint
- **N3 sessions**: cada TickerAnalyst/CryptoAnalyst cria `SessionLocal()` próprio (não compartilha session do N2)

---

## Scheduler

4 jobs automáticos via APScheduler, todos no fuso **America/Sao_Paulo** (BRT):

| Job | Frequência | Horário | Descrição |
|-----|------------|---------|-----------|
| Atualizar preços | A cada 1h | (5min delay inicial) | Busca cotações de todos os ativos em carteira |
| Verificar lock-ups | Diário | 08:00 BRT | Alerta sobre lock-ups expirando |
| Análise semanal | Semanal | Segunda 07:00 BRT | Executa análise completa via Orchestrator |
| Email semanal | Semanal | Segunda 10:00 BRT | Envia relatório HTML via Gmail SMTP |

---

## Regras de Negócio

| Regra | Detalhe |
|-------|---------|
| **Alocação alvo** | 50% ações B3 / 20% crypto / 30% CDB liquidez diária |
| **Lock-up** | 30 dias corridos após compra — sistema impede recomendação de venda antes |
| **Perfil de risco** | Moderado — blue chips + apostas controladas, priorizar preservação de capital |
| **CDI** | Auto-fetched do BCB (série 12) |
| **Autonomia IA** | IA decide alocações; usuário executa manualmente via frontend |
| **Email** | Relatório semanal HTML com Jinja2 template |
| **Idioma** | Todo conteúdo em Português (BR) |

---

## Setup e Instalação

### Pré-requisitos

- Python 3.12+
- Node.js 18+
- GPU NVIDIA com CUDA 12.1+ (para ensemble ML — funciona sem GPU mas sem os modelos neurais)
- Conta OpenAI com acesso aos modelos gpt-5.1 e gpt-5.2
- (Opcional) Conta Gmail com App Password para emails

### Backend

```bash
# Criar ambiente virtual
python -m venv .venv
source .venv/bin/activate

# Instalar dependências
pip install -r requirements.txt

# PyTorch com CUDA (ajustar versão CUDA conforme sua GPU)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Instalar Playwright browsers
playwright install chromium

# Configurar variáveis de ambiente
cat > .env << 'EOF'
OPENAI_API_KEY=sk-...
GMAIL_USER=seu@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
EMAIL_DESTINATARIO=destino@email.com
EOF

# Iniciar servidor (cria DB e tabelas automaticamente)
uvicorn app.main:app --reload --host 127.0.0.1 --port 8002
```

### Frontend

```bash
cd frontend
npm install
npm run dev      # Vite dev server em http://localhost:5173
```

### Verificar

```bash
# Backend
curl http://127.0.0.1:8002/api/health
# → {"status": "ok"}

# Frontend
# Abrir http://localhost:5173 no navegador
```

### Scheduler (opcional)

```bash
# Em terminal separado (com .venv ativado)
python -m app.scheduler &
```

### Build para Produção

```bash
cd frontend
npm run build    # Gera dist/ com assets otimizados
```

---

## Variáveis de Ambiente

| Variável | Obrigatória | Descrição |
|----------|-------------|-----------|
| `OPENAI_API_KEY` | Sim | Chave da API OpenAI |
| `GMAIL_USER` | Não | Email Gmail para envio de relatórios |
| `GMAIL_APP_PASSWORD` | Não | App Password do Gmail (não é a senha normal) |
| `EMAIL_DESTINATARIO` | Não | Email destinatário dos relatórios |

---

## Testes

```bash
# Ativar ambiente virtual
source .venv/bin/activate

# === Testes unitários (sem API calls, custo $0, ~2s) ===
python -m pytest tests/test_multiagent_logic.py -v -m "not integration"
python -m pytest tests/test_browser_concurrency.py -v

# === Testes de integração (chamadas reais OpenAI) ===
# Audit multi-agentes (gpt-4.1-mini, ~34s, custo mínimo)
python -m pytest tests/test_agent_audit.py -v

# Lógica de integração (gpt-5.1, ~100s)
python -m pytest tests/test_multiagent_logic.py -v -m integration

# === Testes GPU / Ensemble ===
python -m pytest tests/test_gpu_real.py -v
python -m pytest tests/test_ensemble_validation.py -v
```

### Cobertura de Testes

| Arquivo de Teste | O que testa | Notas |
|------------------|-------------|-------|
| `test_multiagent_logic.py` | 10 unit + 4 integration: routing, deduplicação, naming, contexto | Unit: $0. Integration: OpenAI real |
| `test_agent_audit.py` | 19 testes de auditoria multi-agente | OpenAI real (gpt-4.1-mini) |
| `test_browser_concurrency.py` | 14 testes: semáforo, Chromium args, executor, timeout | Sem rede, ~2s |
| `test_ensemble_validation.py` | Pipeline ensemble (features, qualidade, treino, predição) | GPU real |
| `test_gpu_real.py` | Pipeline GPU end-to-end (BiLSTM, TFT, stacking) | GPU real, PETR4 |
| `test_e2e_multiagent.py` | Fluxo end-to-end multi-agentes | OpenAI + GPU |

---

## Estrutura do Projeto

```
.
├── app/
│   ├── agents/
│   │   ├── base_agent.py          # BaseAgent — agentic loop, parallel tool execution
│   │   ├── orchestrator.py        # N1 Orchestrator (gpt-5.2, reasoning=xhigh)
│   │   ├── b3_agent.py            # N2 B3Agent — mapeia mercado B3, delega a N3
│   │   ├── crypto_agent.py        # N2 CryptoAgent — mapeia mercado crypto, delega a N3
│   │   ├── stats_agent.py         # N2 StatsAgent — ensemble ML quantitativo
│   │   ├── ticker_analyst.py      # N3 TickerAnalyst — análise profunda por ação
│   │   └── crypto_analyst.py      # N3 CryptoAnalyst — análise profunda por crypto
│   │
│   ├── ensemble/
│   │   ├── pipeline.py            # Pipeline principal (collect → features → train → predict)
│   │   ├── features.py            # Feature engineering (6 tiers, ~50 features)
│   │   ├── xgboost_model.py       # XGBoost GPU wrapper
│   │   ├── bilstm_model.py        # BiLSTM-Attention (FP16/FP32)
│   │   ├── tft_model.py           # Temporal Fusion Transformer (FP32)
│   │   ├── stacking.py            # Meta-learner stacking
│   │   ├── validation.py          # Walk-forward temporal validation com embargo
│   │   └── progress.py            # SSE events thread-safe (asyncio.Queue)
│   │
│   ├── models/
│   │   └── db_models.py           # 9 tabelas SQLAlchemy ORM + 7 indexes
│   │
│   ├── routers/
│   │   ├── portfolio.py           # GET /portfolio, /ativos, /alocacao, /evolucao
│   │   ├── transacoes.py          # GET/POST /transacoes
│   │   ├── analises.py            # GET/POST /analises, SSE /stream/{job_id}
│   │   ├── alertas.py             # GET /alertas, PATCH marcar-lido
│   │   ├── custos.py              # GET /custos, /resumo, /por-agente
│   │   ├── configuracoes.py       # GET/PATCH /configuracoes
│   │   └── market_data_router.py  # GET /cotacao, /historico, /search, /macro
│   │
│   ├── schemas/
│   │   └── api_schemas.py         # Pydantic request/response schemas
│   │
│   ├── services/
│   │   ├── yahoo_scraper.py       # Playwright scraper (stealth, semáforo, retry)
│   │   ├── market_data.py         # Cache, BCB API, conversões ticker
│   │   ├── portfolio_service.py   # Cálculos de portfólio, posições, P&L
│   │   ├── ticker_resolver.py     # Resolve tickers B3 mudados via IA
│   │   ├── token_cost.py          # Log de custos OpenAI (USD/BRL)
│   │   └── email_service.py       # Gmail SMTP + Jinja2
│   │
│   ├── templates/
│   │   └── relatorio_semanal.html # Template HTML do email semanal
│   │
│   ├── config.py                  # Settings (Pydantic, .env)
│   ├── database.py                # SQLite engine, WAL mode, seeds
│   ├── main.py                    # FastAPI app, CORS, lifespan
│   └── scheduler.py               # APScheduler (4 jobs BRT)
│
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   │   └── client.ts          # Axios client + todas as funções API + TypeScript interfaces
│   │   ├── components/
│   │   │   ├── Layout.tsx          # Layout com Sidebar + AnalysisLiveWidget
│   │   │   ├── Sidebar.tsx         # Sidebar navy com navegação
│   │   │   ├── PerformanceSection.tsx  # Cards de performance + barras por ativo
│   │   │   ├── AnalysisLiveWidget.tsx  # SSE progresso em tempo real
│   │   │   ├── AllocationChart.tsx     # Gráfico de alocação
│   │   │   ├── EvolutionChart.tsx      # Evolução patrimonial
│   │   │   ├── AssetTable.tsx          # Tabela de ativos
│   │   │   ├── StatsCard.tsx           # Card de estatística
│   │   │   └── ui/
│   │   │       ├── Toast.tsx       # Notificações com auto-dismiss
│   │   │       ├── Skeleton.tsx    # Loading shimmer animation
│   │   │       └── EmptyState.tsx  # Estado vazio com CTA
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx       # Página principal
│   │   │   ├── Transacoes.tsx      # CRUD transações + autocomplete
│   │   │   ├── Analises.tsx        # Histórico + executar análise
│   │   │   ├── Alertas.tsx         # Lista de alertas
│   │   │   ├── Custos.tsx          # Custos de tokens
│   │   │   └── Config.tsx          # Configurações do sistema
│   │   ├── App.tsx                 # Router principal
│   │   ├── main.tsx                # Entry point (ToastProvider)
│   │   └── index.css               # Estilos globais + design tokens
│   ├── index.html
│   ├── vite.config.ts              # Vite + Tailwind v4 + proxy /api
│   ├── tsconfig.json
│   └── package.json
│
├── api_guide/                      # Documentação de referência (APIs financeiras BR)
├── tests/                          # Suite de testes (unit, integration, GPU, stress)
├── schema.md                       # Schema completo do banco de dados
├── requirements.txt                # Dependências Python
└── .gitignore
```

---

## Licença

Projeto pessoal — todos os direitos reservados.
