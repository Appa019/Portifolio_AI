# 📊 Guia Definitivo: APIs Gratuitas de Dados do Mercado Financeiro
### Atualizado em 01/Março/2026 — Ações, Fundos, Câmbio, Cripto e Dados Econômicos

---

## Sumário

1. [Visão Geral do Ecossistema](#1-visão-geral)
2. [APIs para o Mercado Brasileiro 🇧🇷](#2-mercado-brasileiro)
3. [APIs Globais de Ações, Fundos e Forex 🌍](#3-apis-globais)
4. [Bibliotecas Open-Source (Sem API Key) 🐍](#4-open-source)
5. [APIs de Criptomoedas 🪙](#5-cripto)
6. [APIs de Notícias e Sentimento 📰](#6-noticias)
7. [APIs de Dados Macroeconômicos 🏦](#7-macro)
8. [Tabela Comparativa Master](#8-tabela)
9. [Recomendações por Caso de Uso](#9-recomendacoes)
10. [Arquitetura de Produção e Boas Práticas](#10-producao)

---

## 1. Visão Geral do Ecossistema {#1-visão-geral}

O cenário de APIs financeiras em 2026 é maduro e competitivo. Existem dezenas de provedores, mas a maioria cobra caro para acesso completo. A boa notícia: é perfeitamente possível montar um pipeline robusto usando apenas tiers gratuitos, combinando múltiplas fontes.

**Categorias de dados financeiros:**

- **Market Data (Preços):** Cotações real-time, OHLCV histórico, intraday
- **Fundamentalista:** Balanços, DRE, Fluxo de Caixa, indicadores (P/L, ROE, DY)
- **Derivados e Indicadores Técnicos:** RSI, MACD, Bollinger, médias móveis
- **Notícias e Sentimento:** Análise de sentimento, manchetes, social signals
- **Macroeconômico:** PIB, inflação, juros, câmbio, emprego
- **On-chain (Cripto):** Dados de blockchain, DeFi, DEX, NFTs

**Realidade sobre "real-time" gratuito:** Quase todas as APIs gratuitas entregam dados com delay de 15-20 minutos. Dados verdadeiramente real-time (tick-level, <1s) são quase sempre pagos. Para a maioria dos projetos de análise e estudo, o delay é aceitável.

---

## 2. APIs para o Mercado Brasileiro 🇧🇷 {#2-mercado-brasileiro}

O mercado brasileiro é notoriamente difícil para dados gratuitos. A B3 cobra caro por acesso institucional (Market Data oficial). As alternativas abaixo democratizam esse acesso.

---

### 🟢 brapi.dev — A Principal API da B3

A API mais completa e popular para dados do mercado financeiro brasileiro. Referência entre desenvolvedores brasileiros.

| Aspecto | Detalhe |
|---|---|
| **URL** | [brapi.dev](https://brapi.dev) — [Documentação](https://brapi.dev/docs) |
| **Tier Gratuito** | 4 ações sem token (PETR4, MGLU3, VALE3, ITUB4) com acesso TOTAL a todos os endpoints, sem limite de requisições |
| **Planos Pagos** | A partir de ~R$20/mês para +4.000 ativos |
| **Delay** | ~15 minutos para cotações |
| **Formato** | REST API, JSON |
| **Autenticação** | Bearer Token (dispensável para as 4 ações de teste) |
| **SDKs Oficiais** | JavaScript/TypeScript (NPM), Python (PyPI) |
| **MCP Server** | Sim — integração com assistentes de IA |

**Dados disponíveis (plano gratuito, 4 ações):**

- Cotação atual (preço, variação, volume, market cap, máxima, mínima)
- Histórico OHLCV (múltiplos ranges: 1d, 5d, 1mo, 3mo, 6mo, 1y, 5y, max)
- Dividendos e JCP (datas com, ex, pagamento, valores)
- Balanço Patrimonial (anual e trimestral)
- Demonstração de Resultado (DRE)
- Fluxo de Caixa (DFC)
- Demonstração de Valor Adicionado (DVA)
- Indicadores fundamentalistas: P/L, P/VP, ROE, ROA, Dividend Yield, LPA, VPA, Margem Líquida
- Perfil da empresa (setor, descrição, website, nº funcionários)

**Dados adicionais (com token):**

- Todas as 4.000+ ações, FIIs, ETFs, BDRs da B3
- Índices (IBOVESPA, IFIX, etc.)
- Criptomoedas
- Câmbio (50+ pares de moedas)
- Inflação (IPCA, IGP-M, INPC, IPCA-E)
- Taxa Selic (série histórica)

**Exemplos práticos:**

```bash
# ✅ SEM TOKEN — cotação simples de ações de teste
curl "https://brapi.dev/api/quote/PETR4,VALE3"

# ✅ SEM TOKEN — histórico de 3 meses com intervalos diários
curl "https://brapi.dev/api/quote/MGLU3?range=3mo&interval=1d"

# ✅ SEM TOKEN — balanço patrimonial + DRE
curl "https://brapi.dev/api/quote/ITUB4?modules=balanceSheetHistory,incomeStatementHistory"

# ✅ SEM TOKEN — dividendos completos
curl "https://brapi.dev/api/quote/PETR4?dividends=true"

# ✅ SEM TOKEN — indicadores fundamentalistas + perfil
curl "https://brapi.dev/api/quote/VALE3?modules=defaultKeyStatistics,summaryProfile"

# ⚠️ COM TOKEN — qualquer ação do mercado
curl -H "Authorization: Bearer SEU_TOKEN" \
     "https://brapi.dev/api/quote/BBDC4,WEGE3?range=1y&interval=1d"
```

```python
# Python — sem token para ações de teste
import requests

# Cotação + fundamentos de PETR4
r = requests.get("https://brapi.dev/api/quote/PETR4", params={
    "modules": "defaultKeyStatistics,summaryProfile",
    "fundamental": "true"
})
data = r.json()["results"][0]
print(f"{data['shortName']}: R${data['regularMarketPrice']:.2f}")
print(f"P/L: {data.get('priceEarnings', 'N/A')}")
print(f"DY: {data.get('dividendYield', 'N/A')}")

# Lista todos os ativos disponíveis (com token)
r = requests.get("https://brapi.dev/api/available",
                  headers={"Authorization": "Bearer SEU_TOKEN"})
tickers = r.json()["stocks"]
print(f"Total de ativos: {len(tickers)}")
```

**Pontos fortes:** API mais completa para dados brasileiros, documentação em português, respostas rápidas, SDKs oficiais, suporte a MCP.

**Limitações:** Tier gratuito limitado a 4 ações. Para produção com múltiplos ativos, é necessário um plano pago (acessível).

---

### 🟡 HG Brasil Finance

API brasileira multi-propósito (finanças + clima + geolocalização). Ideal para dashboards rápidos.

| Aspecto | Detalhe |
|---|---|
| **URL** | [hgbrasil.com](https://hgbrasil.com) — [Doc Finance](https://console.hgbrasil.com/documentation/finance) |
| **Tier Gratuito** | ~3 requisições/minuto (varia); dados básicos de cotações |
| **Planos Pagos** | A partir de ~R$24/mês |
| **Formato** | REST, JSON |
| **Autenticação** | API Key via query parameter `?key=` |
| **Diferencial** | CORS liberado, respostas compactas, endpoint multi-dado |

**Dados disponíveis:**

- Cotações de ações do IBOVESPA (preço, variação, volume)
- Câmbio (USD, EUR, GBP, ARS, CAD, AUD, JPY, CNY, BTC)
- Índices (Ibovespa, IFIX, Nasdaq, S&P 500, Dow Jones)
- Dividendos de ações e FIIs
- Maiores altas e baixas do dia
- Dados de mercado com descrições geradas por IA
- Desdobramentos e grupamentos

```bash
# Cotação de ação + câmbio + índices numa requisição
curl "https://api.hgbrasil.com/finance?key=SUA-CHAVE"

# Cotação específica de ações
curl "https://api.hgbrasil.com/finance/stock_price?key=SUA-CHAVE&symbol=petr4,vale3"

# Dividendos de FIIs
curl "https://api.hgbrasil.com/finance/stock_dividends?key=SUA-CHAVE&symbol=alzr11,tgar11"

# Maiores altas do dia
curl "https://api.hgbrasil.com/finance/stock_price?key=SUA-CHAVE&symbol=get-high"
```

**Pontos fortes:** Simplicidade extrema, CORS liberado (use direto no frontend), múltiplos dados numa requisição.

**Limitações:** Sem dados históricos longos, sem dados fundamentalistas profundos, tier gratuito bastante restrito.

---

### 🟠 API Oficial da B3 (Developers)

Para referência: a B3 disponibiliza APIs para instituições, mas são pagas e voltadas para uso profissional.

| Aspecto | Detalhe |
|---|---|
| **URL** | [developers.b3.com.br](https://developers.b3.com.br/apis) |
| **Custo** | Pago (institucional) — R$1.500+/mês por pacote |
| **Uso** | Fintechs registradas, corretoras, instituições financeiras |

Para desenvolvedores independentes, não é viável. Use brapi.dev ou yfinance como alternativas.

---

## 3. APIs Globais de Ações, Fundos e Forex 🌍 {#3-apis-globais}

---

### 🟢 Alpha Vantage — Melhor para Aprender e Prototipar

Parceira oficial da NASDAQ. Uma das APIs mais populares entre desenvolvedores e pesquisadores.

| Aspecto | Detalhe |
|---|---|
| **URL** | [alphavantage.co](https://www.alphavantage.co) — [Docs](https://www.alphavantage.co/documentation/) |
| **Tier Gratuito** | **25 requisições/dia** (limite reduzido em 2025) |
| **Planos Pagos** | A partir de ~$49/mês |
| **Latência** | Moderada (não ideal para alta frequência) |
| **Formato** | REST, JSON e CSV |
| **Autenticação** | API Key via query parameter `&apikey=` |
| **MCP** | Sim — suporte a agentes de IA |

**Dados disponíveis:**

- Ações: cotações real-time, intraday (1/5/15/30/60 min), diário, semanal, mensal
- ETFs e Mutual Funds
- Forex (150+ pares)
- Criptomoedas
- Commodities
- 60+ indicadores técnicos (RSI, MACD, Bollinger, SMA, EMA, Stochastic, ADX, CCI, etc.)
- Dados fundamentalistas: income statement, balance sheet, cash flow, earnings
- Dados macroeconômicos: PIB, inflação, desemprego, juros (EUA)
- Notícias de mercado com análise de sentimento (IA)
- Cobertura global: 30+ países

```python
import requests

API_KEY = "SUA_CHAVE_GRATUITA"
BASE = "https://www.alphavantage.co/query"

# Cotação intraday (5 min) da Apple
r = requests.get(BASE, params={
    "function": "TIME_SERIES_INTRADAY",
    "symbol": "AAPL",
    "interval": "5min",
    "apikey": API_KEY
})

# RSI de 14 períodos
r = requests.get(BASE, params={
    "function": "RSI",
    "symbol": "AAPL",
    "interval": "daily",
    "time_period": 14,
    "series_type": "close",
    "apikey": API_KEY
})

# Notícias com sentimento
r = requests.get(BASE, params={
    "function": "NEWS_SENTIMENT",
    "tickers": "AAPL",
    "apikey": API_KEY
})

# Dados macroeconômicos (PIB dos EUA)
r = requests.get(BASE, params={
    "function": "REAL_GDP",
    "interval": "quarterly",
    "apikey": API_KEY
})
```

**Pontos fortes:** Enorme variedade de dados num único provedor, indicadores técnicos prontos, dados macro, sentimento de notícias, boa documentação.

**Limitações:** Tier gratuito agora muito restrito (25 req/dia). Cobertura limitada de ativos brasileiros. Latência moderada.

---

### 🟢 Finnhub — O Tier Gratuito Mais Generoso

API developer-friendly com o tier gratuito mais permissivo do mercado.

| Aspecto | Detalhe |
|---|---|
| **URL** | [finnhub.io](https://finnhub.io) — [Docs](https://finnhub.io/docs/api) |
| **Tier Gratuito** | **60 chamadas/minuto** (~86.400/dia) — o mais generoso! |
| **Planos Pagos** | A partir de $29/mês (Grow) |
| **Latência** | <100ms |
| **Formato** | REST + WebSocket |
| **Autenticação** | API Key via query parameter ou header |

**Dados disponíveis (free tier):**

- Cotações real-time (ações US via IEX — gratuitas)
- Cotações internacionais (com limitações)
- Forex e cripto real-time
- Fundamentos: perfil, financials, métricas
- Notícias com análise de sentimento
- Calendários: earnings, IPOs, dividendos, stock splits
- Dados alternativos: trades de congressistas dos EUA, ESG
- Indicadores técnicos
- Pattern recognition (candlestick patterns)
- Recommendation trends (analistas)
- WebSocket para streaming

```python
import requests

API_KEY = "SUA_CHAVE_FINNHUB"
BASE = "https://finnhub.io/api/v1"

# Cotação real-time
r = requests.get(f"{BASE}/quote", params={"symbol": "AAPL", "token": API_KEY})
# {"c": 178.72, "d": 0.56, "dp": 0.3143, "h": 179.63, "l": 177.54, "o": 178.18, ...}

# Recomendações de analistas
r = requests.get(f"{BASE}/stock/recommendation", params={"symbol": "AAPL", "token": API_KEY})

# Calendário de earnings (próximas semanas)
r = requests.get(f"{BASE}/calendar/earnings", params={
    "from": "2026-03-01", "to": "2026-03-15", "token": API_KEY
})

# Notícias com sentimento
r = requests.get(f"{BASE}/company-news", params={
    "symbol": "AAPL", "from": "2026-02-01", "to": "2026-03-01", "token": API_KEY
})

# Trades de congressistas (!)
r = requests.get(f"{BASE}/stock/congressional-trading", params={
    "symbol": "AAPL", "token": API_KEY
})

# WebSocket streaming (real-time)
import websocket
ws = websocket.create_connection(f"wss://ws.finnhub.io?token={API_KEY}")
ws.send('{"type":"subscribe","symbol":"AAPL"}')
```

**Pontos fortes:** 60 req/min grátis (imbatível), WebSocket streaming, dados alternativos (congressional trading, ESG), boa cobertura multi-asset.

**Limitações:** Fundamentos menos profundos que FMP. Cobertura de mercados asiáticos mais fraca. Dados de US são mais ricos que internacionais.

---

### 🟡 Financial Modeling Prep (FMP) — Melhor para Análise Fundamentalista

Excelente para quem precisa de demonstrações financeiras detalhadas e screeners.

| Aspecto | Detalhe |
|---|---|
| **URL** | [financialmodelingprep.com](https://site.financialmodelingprep.com) |
| **Tier Gratuito** | **250 requisições/dia**; limitado a ações dos EUA |
| **Latência** | <50ms |
| **Formato** | REST + WebSocket |

**Destaques do plano gratuito:**

- Income statements, balance sheets, cash flow (anuais/trimestrais)
- Financial ratios calculados (40+)
- Cotações real-time e históricas
- Screeners de ações
- SEC filings
- Insider trading
- Notícias com ticker association
- Cripto, forex, índices

```python
API_KEY = "SUA_CHAVE_FMP"
BASE = "https://financialmodelingprep.com/api/v3"

# Income statement trimestral da Apple
r = requests.get(f"{BASE}/income-statement/AAPL",
    params={"period": "quarter", "limit": 8, "apikey": API_KEY})

# Ratios financeiros
r = requests.get(f"{BASE}/ratios/AAPL", params={"limit": 5, "apikey": API_KEY})

# Screener: ações com P/E < 15 e market cap > 10B
r = requests.get(f"{BASE}/stock-screener",
    params={"priceMoreThan": 10, "marketCapMoreThan": 10000000000,
            "peRatioLowerThan": 15, "apikey": API_KEY})
```

---

### 🟡 Twelve Data — Multi-Ativos com Indicadores

API limpa, focada em séries temporais. Cobre ações, forex e cripto com interface unificada.

| Aspecto | Detalhe |
|---|---|
| **URL** | [twelvedata.com](https://twelvedata.com) |
| **Tier Gratuito** | **800 requisições/dia**, 8/minuto |
| **Cobertura** | 50+ países, ações, forex, cripto, ETFs, fundos |
| **Formato** | REST + WebSocket |

**Diferenciais:**

- 100+ indicadores técnicos via API (não precisa calcular localmente)
- Interface unificada para todos os ativos
- SDKs: Python, JavaScript, Ruby, PHP, Go
- Add-in para Google Sheets e Excel

```python
API_KEY = "SUA_CHAVE_12DATA"

# Série temporal + indicadores de uma vez
r = requests.get("https://api.twelvedata.com/time_series", params={
    "symbol": "AAPL", "interval": "1day", "outputsize": 100, "apikey": API_KEY
})

# RSI calculado pela API
r = requests.get("https://api.twelvedata.com/rsi", params={
    "symbol": "AAPL", "interval": "1day", "time_period": 14, "apikey": API_KEY
})
```

---

### 🟡 Tiingo — Ideal para Backtesting

Focada em pesquisa quantitativa. Dados limpos e bem validados para backtest.

| Aspecto | Detalhe |
|---|---|
| **URL** | [tiingo.com](https://www.tiingo.com) |
| **Tier Gratuito** | Dados EOD da maioria das ações dos EUA; limite de 1000 req/hora |
| **Diferencial** | Dados limpos e validados, ajustados por dividendos e splits |
| **Preços acadêmicos** | Disponíveis para estudantes e pesquisadores |

---

### 🟠 Polygon.io (Massive) — Alta Performance (Free Limitado)

Infraestrutura de alta performance para mercado dos EUA. Free tier muito restrito.

| Aspecto | Detalhe |
|---|---|
| **URL** | [polygon.io](https://polygon.io) |
| **Tier Gratuito** | 5 chamadas/minuto — apenas para explorar |
| **Diferencial** | WebSocket streaming, dados tick-level, opções |
| **Planos Pagos** | A partir de $199/mês |

---

### 🟠 Marketstack — Cobertura Global Simples

API leve para preços de ações em 70+ bolsas globais.

| Aspecto | Detalhe |
|---|---|
| **URL** | [marketstack.com](https://marketstack.com) |
| **Tier Gratuito** | **100 requisições/mês** (muito baixo); apenas dados EOD |
| **Cobertura** | 70+ bolsas, 125.000+ tickers |
| **Limitação** | Sem forex, sem cripto, sem intraday no free |

---

### 🟠 EODHD — Dados Históricos Longos

Forte em dados históricos com até 30 anos de cobertura.

| Aspecto | Detalhe |
|---|---|
| **URL** | [eodhd.com](https://eodhd.com) |
| **Tier Gratuito** | Limitado (20 chamadas/dia); acesso a dados EOD de bolsas dos EUA |
| **Diferencial** | Histórico de até 30 anos, 60+ bolsas mundiais |
| **Planos Pagos** | A partir de $19.99/mês (bom custo-benefício) |

---

## 4. Bibliotecas Open-Source (Sem API Key) 🐍 {#4-open-source}

---

### 🟢 yfinance (Python) — O Canivete Suíço Gratuito

A biblioteca Python mais popular para dados financeiros. Sem cadastro, sem chave, sem limites definidos.

| Aspecto | Detalhe |
|---|---|
| **Repositório** | [github.com/ranaroussi/yfinance](https://github.com/ranaroussi/yfinance) |
| **Licença** | Apache 2.0 (open-source) |
| **Custo** | 100% gratuito |
| **Instalação** | `pip install yfinance` |
| **Como funciona** | Scraping das páginas públicas do Yahoo Finance |
| **Manutenção** | Ativa (atualizações regulares em 2025-2026) |

**Dados disponíveis:**

- Cotações real-time e históricas (OHLCV) — qualquer ativo do Yahoo Finance
- Dados fundamentalistas: balance sheet, income statement, cash flow
- Dividendos e stock splits
- Opções (chain completa)
- Informações da empresa (setor, indústria, descrição, executivos)
- Recomendações de analistas
- Institutional holders e major holders
- Insider transactions
- Earnings dates e estimativas
- Sustainability/ESG scores
- **Tickers brasileiros**: PETR4.SA, VALE3.SA, ITUB4.SA, BBDC4.SA, etc.
- WebSocket para streaming real-time

```python
import yfinance as yf

# === AÇÕES BRASILEIRAS ===
petr = yf.Ticker("PETR4.SA")

# Histórico de 5 anos
hist = petr.history(period="5y")
print(hist.head())  # Date, Open, High, Low, Close, Volume, Dividends, Stock Splits

# Dados fundamentalistas
print(petr.balance_sheet)          # Balanço patrimonial
print(petr.income_stmt)            # DRE
print(petr.cashflow)               # Fluxo de caixa
print(petr.dividends)              # Série de dividendos
print(petr.info["dividendYield"])   # Dividend yield
print(petr.info["trailingPE"])      # P/L

# Recomendações de analistas
print(petr.recommendations)

# === AÇÕES AMERICANAS ===
aapl = yf.Ticker("AAPL")

# Download massivo — múltiplos tickers
data = yf.download(
    tickers=["AAPL", "MSFT", "GOOGL", "AMZN"],
    start="2020-01-01",
    end="2026-03-01",
    interval="1d",
    group_by="ticker"
)

# Opções
opts = aapl.options                     # Lista de datas de expiração
chain = aapl.option_chain(opts[0])      # Calls e puts
print(chain.calls.head())

# Insider transactions
print(aapl.insider_transactions)

# === ETFs / FIIs brasileiros ===
fii = yf.Ticker("HGLG11.SA")
print(fii.history(period="1y"))
print(fii.dividends)

# === CRIPTO ===
btc = yf.Ticker("BTC-USD")
print(btc.history(period="1y"))

# === CÂMBIO ===
usd_brl = yf.Ticker("USDBRL=X")
print(usd_brl.history(period="6mo"))

# === STREAMING REAL-TIME (WebSocket) ===
# Disponível desde versões recentes do yfinance
ws = yf.WebSocket()
ws.subscribe(["AAPL", "PETR4.SA"])
for msg in ws:
    print(msg)
```

**Pontos fortes:** Zero configuração, cobertura global (incluindo Brasil), dados fundamentalistas completos, ativamente mantido.

**Limitações críticas:**

- **Não oficial** — pode quebrar se o Yahoo mudar a estrutura do site
- **Sem SLA** — não use como única fonte em produção
- **Rate limiting implícito** — muitas requisições rápidas podem resultar em bloqueio temporário
- **Termos de uso** — Yahoo Finance é para uso pessoal/educacional, não redistribuição comercial

---

### 🟡 yahoo_fin (Python)

Alternativa ao yfinance com interface ligeiramente diferente.

```python
from yahoo_fin import stock_info as si

price = si.get_live_price("AAPL")
bs = si.get_balance_sheet("AAPL")
holders = si.get_holders("AAPL")
```

---

### 🟡 OpenBB (Python) — Terminal de Investimento Open-Source

Plataforma open-source que agrega múltiplas fontes de dados.

| Aspecto | Detalhe |
|---|---|
| **URL** | [openbb.co](https://openbb.co) |
| **Instalação** | `pip install openbb` |
| **Diferencial** | Agrega dados de várias APIs (yfinance, FMP, Alpha Vantage, etc.) |
| **Uso** | Terminal interativo + SDK Python |

---

## 5. APIs de Criptomoedas 🪙 {#5-cripto}

---

### 🟢 CoinGecko API — Líder Indiscutível em Dados Cripto

Usada por MetaMask, Coinbase, Etherscan. A API cripto mais completa e confiável.

| Aspecto | Detalhe |
|---|---|
| **URL** | [coingecko.com/en/api](https://www.coingecko.com/en/api) |
| **Tier Gratuito (Demo)** | **10.000 chamadas/mês**, 30/minuto |
| **Planos Pagos** | Analyst ($129/mês), Lite ($499/mês), Enterprise (custom) |
| **Cobertura** | **24M+ tokens**, 250+ redes, 1.700+ exchanges |
| **Formato** | REST, JSON |
| **Histórico** | Até 12 anos (desde 2014) |
| **Certificação** | SOC-2 Type 2, SLA 99.9% |

**Dados disponíveis (free tier):**

- Preços real-time (qualquer moeda fiat como base, incluindo BRL)
- Market cap, volume, dominância
- Histórico de preços (granularidade: 5min/1h/1d dependendo do range)
- OHLCV para candlestick charts
- Dados de exchanges (tickers, volumes, bid/ask)
- Trending coins, top gainers/losers
- Categorias (DeFi, NFT, Gaming, etc.)
- Dados on-chain via GeckoTerminal (DEX pools, tokens, trades)
- NFT floor prices e market data
- Global market data (total market cap, volume, dominância BTC)
- Busca por nome, símbolo ou contrato

```python
BASE = "https://api.coingecko.com/api/v3"

# Preço do Bitcoin em BRL e USD
r = requests.get(f"{BASE}/simple/price", params={
    "ids": "bitcoin,ethereum,solana",
    "vs_currencies": "brl,usd",
    "include_24hr_change": "true",
    "include_market_cap": "true"
})

# Top 20 criptos por market cap
r = requests.get(f"{BASE}/coins/markets", params={
    "vs_currency": "brl",
    "order": "market_cap_desc",
    "per_page": 20,
    "sparkline": "true"    # inclui gráfico de 7 dias
})

# Histórico de 90 dias do Ethereum
r = requests.get(f"{BASE}/coins/ethereum/market_chart", params={
    "vs_currency": "usd",
    "days": 90
})

# OHLCV (candlestick) de 30 dias
r = requests.get(f"{BASE}/coins/bitcoin/ohlc", params={
    "vs_currency": "usd",
    "days": 30
})

# Trending coins (últimas 24h)
r = requests.get(f"{BASE}/search/trending")

# Dados on-chain (GeckoTerminal) — pools de DEX
r = requests.get("https://api.geckoterminal.com/api/v2/networks/eth/trending_pools")
```

**Pontos fortes:** Cobertura inigualável (24M+ tokens incluindo micro-caps), dados on-chain, independente (sem viés de exchange), dados verificados por algoritmos proprietários.

**Limitações:** 30 req/min no free (pode ser limitante para apps com muitos usuários). Sem dados históricos de preço no tier gratuito para granularidade inferior a 1h.

---

### 🟢 CoinMarketCap API — Credibilidade Institucional

Uma das fontes mais reconhecidas e citadas no ecossistema cripto. Pertence à Binance.

| Aspecto | Detalhe |
|---|---|
| **URL** | [coinmarketcap.com/api](https://coinmarketcap.com/api/) |
| **Tier Gratuito (Basic)** | **10.000 chamadas/mês**; atualização a cada 1-2 min |
| **Cobertura** | 20.000+ criptomoedas, 255+ exchanges |
| **Formato** | REST, JSON |
| **Autenticação** | API Key via header `X-CMC_PRO_API_KEY` |

**Dados disponíveis (free tier):**

- Cotações real-time (preço, market cap, volume, variação 1h/24h/7d/30d)
- Rankings e listagens
- Métricas globais (total market cap, dominância BTC, total volume)
- Metadata de moedas (logo, descrição, links, plataformas)
- Conversão de moedas (fiat ↔ cripto)

**Limitação importante:** Sem dados históricos no tier gratuito (apenas real-time).

```python
headers = {"X-CMC_PRO_API_KEY": "SUA_CHAVE_CMC"}

# Top 10 criptos
r = requests.get("https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest",
    headers=headers,
    params={"start": 1, "limit": 10, "convert": "BRL"})
```

---

### 🟡 CryptoCompare — Tier Gratuito Generoso

| Aspecto | Detalhe |
|---|---|
| **URL** | [cryptocompare.com](https://www.cryptocompare.com) |
| **Tier Gratuito** | **100.000 chamadas/mês** — o mais generoso para cripto! |
| **Dados** | Preços (real-time e históricos), dados sociais, mining, exchanges |

---

### 🟡 CoinPaprika — Sinais Sociais

| Aspecto | Detalhe |
|---|---|
| **URL** | [coinpaprika.com](https://coinpaprika.com) |
| **Tier Gratuito** | Top 2.000 tokens por market cap |
| **Diferencial** | Tracking de atividade social (X/Twitter), eventos, people |

---

### 🟡 Binance API — Dados da Maior Exchange

Se você opera na Binance, a API deles é gratuita e sem limites rígidos.

| Aspecto | Detalhe |
|---|---|
| **URL** | [binance-docs.github.io/apidocs](https://binance-docs.github.io/apidocs/) |
| **Custo** | Gratuito (precisa de conta Binance para endpoints autenticados) |
| **Dados públicos** | Orderbook, trades, klines (OHLCV), ticker 24h — sem autenticação |
| **WebSocket** | Streaming real-time de trades, klines, orderbook |

```python
# Dados PÚBLICOS da Binance (sem autenticação)
r = requests.get("https://api.binance.com/api/v3/klines", params={
    "symbol": "BTCUSDT", "interval": "1d", "limit": 365
})
```

---

## 6. APIs de Notícias e Sentimento 📰 {#6-noticias}

| API | Tier Gratuito | Dados | URL |
|---|---|---|---|
| **Alpha Vantage** (News) | 25 req/dia (compartilhado) | Notícias + sentimento IA | alphavantage.co |
| **Finnhub** (News) | 60 req/min (compartilhado) | Notícias + sentimento por empresa | finnhub.io |
| **NewsData.io** | 200 créditos/dia | Notícias financeiras + filtros | newsdata.io |
| **GNews** | 100 req/dia | Manchetes globais | gnews.io |

---

## 7. APIs de Dados Macroeconômicos 🏦 {#7-macro}

| API / Fonte | Tier Gratuito | Dados | URL |
|---|---|---|---|
| **FRED (Federal Reserve)** | Ilimitado | PIB, inflação, juros, emprego (EUA) | fred.stlouisfed.org/docs/api |
| **World Bank API** | Ilimitado | Indicadores de 200+ países | data.worldbank.org |
| **Alpha Vantage** (Macro) | 25 req/dia | PIB, inflação, desemprego (EUA) | alphavantage.co |
| **brapi.dev** (BR) | Com token | IPCA, IGP-M, Selic, INPC | brapi.dev |
| **BCB (Banco Central)** | Ilimitado | Selic, câmbio, inflação, crédito | dadosabertos.bcb.gov.br |
| **IBGE API** | Ilimitado | IPCA, PIB, PNAD, PIM | servicodados.ibge.gov.br/api |

```python
# FRED — Federal Reserve (sem autenticação para dados básicos)
r = requests.get("https://api.stlouisfed.org/fred/series/observations",
    params={"series_id": "GDP", "api_key": "SUA_CHAVE_FRED", "file_type": "json"})

# BCB — Banco Central do Brasil (sem autenticação)
# Selic diária (série 11)
r = requests.get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.11/dados/ultimos/30?formato=json")

# IPCA mensal (série 433)
r = requests.get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados/ultimos/12?formato=json")

# Câmbio PTAX (série 1)
r = requests.get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.1/dados/ultimos/30?formato=json")
```

---

## 8. Tabela Comparativa Master {#8-tabela}

| API | Ações BR | Ações US/Global | Cripto | Forex | Fundamentos | Indicadores Técnicos | Notícias/Sentimento | Free Tier (Generosidade) |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|---|
| **brapi.dev** | ✅ | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ | ⭐⭐⭐ (4 ações ilimitadas) |
| **HG Brasil** | ✅ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ⭐⭐ (limitado) |
| **Alpha Vantage** | ⚠️ | ✅ | ✅ | ✅ | ✅ | ✅ (60+) | ✅ | ⭐⭐ (25 req/dia) |
| **Finnhub** | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⭐⭐⭐⭐⭐ (60 req/min) |
| **FMP** | ❌ | ✅ | ✅ | ✅ | ✅✅ | ⚠️ | ✅ | ⭐⭐⭐ (250 req/dia) |
| **Twelve Data** | ❌ | ✅ | ✅ | ✅ | ⚠️ | ✅ (100+) | ❌ | ⭐⭐⭐ (800 req/dia) |
| **Tiingo** | ❌ | ✅ | ✅ | ❌ | ⚠️ | ❌ | ✅ | ⭐⭐⭐ (1000 req/hora) |
| **yfinance** | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ⭐⭐⭐⭐⭐ (ilimitado*) |
| **CoinGecko** | ❌ | ❌ | ✅✅ | ❌ | ❌ | ❌ | ❌ | ⭐⭐⭐ (10K/mês) |
| **CoinMarketCap** | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ⭐⭐⭐ (10K/mês) |
| **CryptoCompare** | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ⭐⭐⭐⭐⭐ (100K/mês) |
| **BCB** | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ⭐⭐⭐⭐⭐ (ilimitado) |
| **FRED** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ⭐⭐⭐⭐⭐ (ilimitado) |

*\*yfinance: ilimitado mas não oficial — pode quebrar*

---

## 9. Recomendações por Caso de Uso {#9-recomendacoes}

**📊 Monitorar carteira de ações brasileiras:**
brapi.dev (principal) + yfinance (backup) + BCB (Selic/câmbio)

**📈 Análise fundamentalista de ações americanas:**
FMP (fundamentos profundos) + Finnhub (notícias/calendários) + FRED (macro)

**🤖 Bot de trading de cripto:**
CoinGecko (dados gerais) + Binance API (orderbook/trades) + CryptoCompare (histórico)

**🧪 Backtesting de estratégias:**
yfinance (dados globais, gratuito) + Tiingo (dados limpos US) + brapi.dev (BR)

**📱 App/Dashboard financeiro:**
brapi.dev (BR) + Finnhub (global, WebSocket) + CoinGecko (cripto)

**🎓 Estudante/Aprendizado:**
yfinance (zero configuração) + Alpha Vantage (boa documentação) + CoinGecko (cripto)

**🔬 Modelo de ML/Deep Learning:**
yfinance (coleta massiva) + Alpha Vantage (indicadores técnicos) + BCB/FRED (macro features)

---

## 10. Arquitetura de Produção e Boas Práticas {#10-producao}

**1. Nunca dependa de uma única fonte.** APIs mudam, quebram ou fecham (IEX Cloud fechou em 2024 sem aviso).

**2. Implemente cache local.** Use SQLite, Redis ou CSV para armazenar dados já coletados. Nunca re-busque o que já tem.

**3. Respeite rate limits.** Implemente retry com backoff exponencial. Uma violação pode resultar em ban.

**4. Monitore a saúde das APIs.** Crie alertas para quando uma fonte retornar erros ou dados inconsistentes.

**5. Valide dados cruzando fontes.** Se o preço de uma ação difere muito entre brapi.dev e yfinance, algo está errado.

**6. Leia os termos de uso.** Muitas APIs gratuitas proíbem redistribuição comercial dos dados.

```python
# Exemplo: coleta resiliente com fallback
def get_stock_price(ticker):
    """Tenta brapi.dev, depois yfinance como fallback."""
    try:
        r = requests.get(f"https://brapi.dev/api/quote/{ticker}", timeout=5)
        r.raise_for_status()
        return r.json()["results"][0]["regularMarketPrice"]
    except Exception:
        try:
            import yfinance as yf
            return yf.Ticker(f"{ticker}.SA").info["regularMarketPrice"]
        except Exception:
            return None
```

---

*Este guia cobre as principais opções gratuitas disponíveis em Março/2026. Preços, limites e funcionalidades mudam frequentemente — consulte sempre a documentação oficial de cada API antes de iniciar um projeto.*