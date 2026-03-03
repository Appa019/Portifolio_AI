# Portfolio AI — Sistema de Gestão de Investimentos com Multi-Agentes IA

Sistema de gestão de portfólio de investimentos com **multi-agentes IA em 3 níveis hierárquicos**, ensemble ML (XGBoost + BiLSTM-Attention + TFT), e scraping de dados de mercado em tempo real.

Roda localmente (localhost) sem autenticação. Interface e análises em **Português (BR)**.

## Stack

| Camada | Tecnologia |
|--------|------------|
| Backend | Python + FastAPI (port 8002) |
| Frontend | React 18 + Tailwind CSS 4 + Vite + React Query + Recharts |
| Database | SQLite (WAL mode) |
| Agentes IA | OpenAI Responses API — 3 níveis hierárquicos com reasoning |
| ML Ensemble | XGBoost + BiLSTM-Attention + TFT, stacking meta-learner |
| Email | Gmail SMTP via aiosmtplib + Jinja2 templates |
| Scheduler | APScheduler (preços 1h, lockups diário, análise seg 7h, email seg 10h) |
| Scraping | Playwright Chromium headless (Yahoo Finance) |

## Arquitetura Multi-Agentes (3 Níveis)

```
N1  Orchestrator (gpt-5.2, reasoning=xhigh) — consciência total do portfólio
     ├── N2  B3Agent (gpt-5.1, reasoning=high) — mapeia mercado B3
     │        └── N3  TickerAnalyst (gpt-5.1, reasoning=medium) — análise profunda por ação
     ├── N2  CryptoAgent (gpt-5.1, reasoning=high) — mapeia mercado crypto
     │        └── N3  CryptoAnalyst (gpt-5.1, reasoning=medium) — análise profunda por crypto
     └── N2  StatsAgent (gpt-5.1, reasoning=none) — ensemble ML quantitativo
              └── EnsemblePipeline: XGBoost + BiLSTM-Attention + TFT
```

## Ensemble ML

Otimizado para **RTX 2070 SUPER (8GB VRAM)**:

- **XGBoost**: GPU-accelerated, ~50 features (técnicas + fundamentais + macro)
- **BiLSTM-Attention**: FP16 mixed precision, sequências temporais
- **TFT (Temporal Fusion Transformer)**: FP32, attention mechanism
- **Meta-learner**: Stacking com walk-forward validation e embargo temporal
- **Features macro**: Selic, IPCA (12m multiplicativo), PTAX via BCB API

## Setup

### Pré-requisitos

- Python 3.12+
- Node.js 18+
- GPU NVIDIA com CUDA 12.1+ (para ensemble ML)
- Conta OpenAI com acesso a gpt-5.1/5.2

### Backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# PyTorch com CUDA
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Configurar variáveis de ambiente
cp .env.example .env
# Editar .env com suas chaves

uvicorn app.main:app --reload --host 127.0.0.1 --port 8002
```

### Frontend

```bash
cd frontend
npm install
npm run dev  # Vite em http://localhost:5173
```

### Scheduler (opcional)

```bash
python -m app.scheduler &
```

## Variáveis de Ambiente

```env
OPENAI_API_KEY=sk-...
GMAIL_USER=seu@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
EMAIL_DESTINATARIO=destino@email.com
```

## Testes

```bash
# Testes unitários (sem API calls, $0)
python -m pytest tests/test_multiagent_logic.py -v -m "not integration"
python -m pytest tests/test_browser_concurrency.py -v

# Testes de integração (chamadas reais OpenAI)
python -m pytest tests/test_agent_audit.py -v
python -m pytest tests/test_multiagent_logic.py -v -m integration

# Ensemble ML (GPU)
python -m pytest tests/test_gpu_real.py -v

# Stress test scraping (20 tickers × 9 funções)
python -m pytest tests/stress_scraping_yahoo.py -v
```

## Regras de Negócio

- **Alocação alvo**: 50% ações B3 / 20% crypto / 30% CDB liquidez diária
- **Lock-up**: 30 dias corridos após compra
- **Perfil**: Moderado — blue chips + apostas controladas
- **Autonomia IA**: IA decide alocações; usuário executa manualmente

## Estrutura do Projeto

```
app/
├── agents/          # Multi-agentes IA (orchestrator, b3, crypto, stats, N3 analysts)
├── ensemble/        # Pipeline ML (XGBoost, BiLSTM, TFT, stacking, features)
├── models/          # SQLAlchemy ORM (9 tabelas)
├── routers/         # FastAPI endpoints
├── schemas/         # Pydantic schemas
├── services/        # Yahoo scraper, market data, portfolio, email, token cost
├── templates/       # Jinja2 email templates
├── config.py        # Configurações e modelos
├── database.py      # SQLite + seeds
├── main.py          # FastAPI app + lifespan
└── scheduler.py     # APScheduler (4 jobs)

frontend/
├── src/
│   ├── api/         # Client API + TypeScript interfaces
│   ├── components/  # UI components (Toast, Skeleton, EmptyState, Charts)
│   └── pages/       # Dashboard, Transações, Análises, Alertas, Custos, Config
└── vite.config.ts   # Proxy + Tailwind v4

tests/               # Unit, integration, GPU, stress tests
```

## API

Todos os endpoints prefixados com `/api`:

| Rota | Descrição |
|------|-----------|
| `GET /api/portfolio/` | Resumo do portfólio |
| `GET /api/portfolio/ativos` | Lista de ativos |
| `POST /api/transacoes/` | Nova transação (auto lock-up) |
| `POST /api/analises/executar` | Inicia análise completa (retorna job_id) |
| `GET /api/analises/stream/{job_id}` | SSE progresso em tempo real |
| `GET /api/market/cotacao/{ticker}` | Cotação atual |
| `GET /api/market/search?q=` | Autocomplete de tickers |
| `GET /api/custos/resumo` | Custos de tokens por agente |

## Licença

Projeto pessoal — todos os direitos reservados.
