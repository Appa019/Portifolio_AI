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

    # Modelos OpenAI (fixos)
    modelo_orquestrador: str = "gpt-5.2"
    modelo_subagente: str = "gpt-5.1"

    # Reasoning effort por agente (Responses API)
    reasoning_effort: dict = {
        "orchestrator": "xhigh",
        "b3_agent": "high",
        "crypto_agent": "high",
        "ticker_analyst": "medium",
        "crypto_analyst": "medium",
        "stats_agent": "none",
        "ticker_resolver": "none",  # gpt-4.1 não suporta reasoning
    }

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
