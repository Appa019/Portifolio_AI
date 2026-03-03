"""
Ticker Resolver — agente leve de IA que resolve tickers B3 via web search.

Quando um ticker falha no Yahoo Finance (ex: ELET3 → virou AXIA3),
este agente pesquisa na web para encontrar o ticker correto atual.
Usa gpt-4.1 (barato, rápido) com web_search.
"""

import json
import logging
import threading
from datetime import datetime, timedelta

from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)

# Client singleton — evitar overhead de connection setup a cada chamada
_client: OpenAI | None = None
_client_lock = threading.Lock()


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = OpenAI(api_key=settings.openai_api_key)
    return _client


# Cache em memória para evitar chamadas repetidas
_cache: dict[str, dict] = {}
_CACHE_TTL_HOURS = 24


def _get_cached(ticker: str) -> dict | None:
    entry = _cache.get(ticker)
    if entry and entry["expira"] > datetime.now():
        return entry["data"]
    return None


def _set_cached(ticker: str, data: dict):
    _cache[ticker] = {
        "data": data,
        "expira": datetime.now() + timedelta(hours=_CACHE_TTL_HOURS),
    }


def resolve_ticker(ticker: str, db=None) -> dict | None:
    """Resolve um ticker B3 que pode ter mudado de nome.

    Usa OpenAI web_search para pesquisar o ticker correto na B3/Yahoo Finance.

    Args:
        ticker: Ticker original (ex: "ELET3", "JBSS3")
        db: Session SQLAlchemy opcional para logging de custos

    Returns:
        Dict com:
            - ticker_original: ticker pedido
            - ticker_atual: ticker correto atual na B3
            - ticker_yahoo: ticker no Yahoo Finance (com .SA)
            - nome_empresa: nome da empresa
            - motivo: explicação da mudança (se houve)
        Ou None se não encontrou.
    """
    cached = _get_cached(ticker)
    if cached:
        logger.debug(f"Ticker resolver cache hit: {ticker} → {cached.get('ticker_atual')}")
        return cached

    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY não configurada — ticker resolver indisponível")
        return None

    try:
        client = _get_client()

        response = client.responses.create(
            model="gpt-4.1",
            tools=[{
                "type": "web_search",
                "user_location": {
                    "type": "approximate",
                    "country": "BR",
                    "city": "São Paulo",
                    "timezone": "America/Sao_Paulo",
                },
            }],
            input=f"""Você é um assistente especializado em ações da B3 (bolsa brasileira).

O ticker "{ticker}" não está sendo encontrado no Yahoo Finance com o sufixo .SA.

Pesquise na web e responda APENAS com um JSON válido (sem markdown, sem texto extra):
{{
    "ticker_original": "{ticker}",
    "ticker_atual": "TICKER_CORRETO_NA_B3",
    "ticker_yahoo": "TICKER.SA",
    "nome_empresa": "Nome da Empresa",
    "motivo": "explicação breve da mudança ou situação"
}}

Possíveis situações:
- Empresa mudou de nome/ticker (ex: ELET3 → AXIA3)
- Ticker é BDR e usa formato diferente (ex: JBSS3 → JBSS32)
- Empresa fez cisão, fusão ou incorporação
- Ticker foi deslistado
- Ticker nunca existiu

Se o ticker não existe e não há equivalente, retorne:
{{
    "ticker_original": "{ticker}",
    "ticker_atual": null,
    "ticker_yahoo": null,
    "nome_empresa": null,
    "motivo": "explicação"
}}

Data atual: {datetime.now().strftime('%Y-%m-%d')}""",
        )

        # Log de custos
        if db and response.usage:
            try:
                from app.services.token_cost import log_token_cost
                log_token_cost(
                    db=db,
                    agente="ticker_resolver",
                    modelo="gpt-4.1",
                    tokens_input=response.usage.input_tokens,
                    tokens_output=response.usage.output_tokens,
                    descricao=f"Resolver ticker {ticker}",
                )
            except Exception as e:
                logger.debug(f"Erro ao logar custo: {e}")

        # Extrair resposta de texto
        text = response.output_text
        if not text:
            logger.warning(f"Ticker resolver sem resposta para {ticker}")
            return None

        # Limpar possíveis marcadores markdown
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        result = json.loads(text)
        _set_cached(ticker, result)

        logger.info(
            f"Ticker resolvido: {ticker} → {result.get('ticker_atual')} "
            f"({result.get('motivo', '')})"
        )
        return result

    except json.JSONDecodeError as e:
        logger.warning(f"Ticker resolver JSON inválido para {ticker}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Erro ticker resolver {ticker}: {e}")
        return None


def resolve_multiple(tickers: list[str], db=None) -> dict[str, dict | None]:
    """Resolve múltiplos tickers de uma vez.

    Returns:
        Dict ticker_original → resultado (ou None se não resolveu)
    """
    results = {}
    for ticker in tickers:
        results[ticker] = resolve_ticker(ticker, db)
    return results
