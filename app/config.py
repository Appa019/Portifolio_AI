from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # OpenAI
    openai_api_key: str = ""

    # Email
    gmail_user: str = ""
    gmail_app_password: str = ""
    email_destinatario: str = ""

    # Database
    database_url: str = "sqlite:///./portfolio.db"

    # Telegram (3 bots via BotFather)
    telegram_ceo_token: str = ""          # Chat privado com Carlos Mendonça (CIO)
    telegram_mesa_b3_token: str = ""      # Grupo Mesa B3
    telegram_mesa_crypto_token: str = ""  # Grupo Mesa Crypto
    telegram_mesa_b3_chat_id: str = ""    # Chat ID do grupo Mesa B3
    telegram_mesa_crypto_chat_id: str = ""  # Chat ID do grupo Mesa Crypto

    # Modelos OpenAI — default por tier
    modelo_orquestrador: str = "gpt-5.2"
    modelo_subagente: str = "gpt-5.1"
    modelo_utility: str = "gpt-4.1"

    # Modelo por agente (override do default)
    agent_models: dict = {
        # N0
        "cio": "gpt-5.2",
        # N1
        "head_b3": "gpt-5.1",
        "head_crypto": "gpt-5.1",
        "cro": "gpt-5.1",
        # N2 — B3 team
        "fundamentalista_b3": "gpt-5.1",
        "tecnico_b3": "gpt-4.1",
        "setorial_b3": "gpt-5.1",
        "risk_b3": "gpt-4.1",
        "trade_b3": "gpt-4.1",
        # N2 — Crypto team
        "fundamentalista_crypto": "gpt-5.1",
        "tecnico_crypto": "gpt-4.1",
        "onchain_analyst": "gpt-5.1",
        "risk_crypto": "gpt-4.1",
        "trade_crypto": "gpt-4.1",
        # N2 — Cross-team staff
        "macro_economist": "gpt-5.1",
        "sentiment_analyst": "gpt-4.1",
        "compliance_officer": "gpt-4.1",
        "quant_analyst": "gpt-5.1",
        # N3 (dynamic)
        "ticker_analyst": "gpt-5.1",
        "crypto_analyst": "gpt-5.1",
        # Utility
        "ticker_resolver": "gpt-4.1",
    }

    # Reasoning effort por agente (Responses API)
    reasoning_effort: dict = {
        # N0
        "cio": "xhigh",
        # N1
        "head_b3": "high",
        "head_crypto": "high",
        "cro": "high",
        # N2 — B3 team
        "fundamentalista_b3": "medium",
        "tecnico_b3": "none",       # gpt-4.1: no reasoning
        "setorial_b3": "medium",
        "risk_b3": "none",
        "trade_b3": "none",
        # N2 — Crypto team
        "fundamentalista_crypto": "medium",
        "tecnico_crypto": "none",
        "onchain_analyst": "medium",
        "risk_crypto": "none",
        "trade_crypto": "none",
        # N2 — Cross-team staff
        "macro_economist": "high",
        "sentiment_analyst": "none",
        "compliance_officer": "none",
        "quant_analyst": "medium",
        # N3 (dynamic)
        "ticker_analyst": "medium",
        "crypto_analyst": "medium",
        # Utility
        "ticker_resolver": "none",
        # Legacy aliases (backward compat)
        "orchestrator": "xhigh",
        "b3_agent": "high",
        "crypto_agent": "high",
    }

    # Budget cap per analysis run (USD)
    max_cost_per_run_usd: float = 5.0

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
