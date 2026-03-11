"""Configuração central de logging com RotatingFileHandler e correlação por job_id."""

import logging
import logging.handlers
import os
import threading

_job_ctx = threading.local()


def set_job_id(job_id: str | None):
    """Define job_id no contexto da thread atual (propagado automaticamente para logs)."""
    _job_ctx.job_id = job_id


def get_job_id() -> str | None:
    return getattr(_job_ctx, "job_id", None)


class JobIdFilter(logging.Filter):
    def filter(self, record):
        record.job_id = getattr(_job_ctx, "job_id", None) or "-"
        return True


def setup_logging():
    os.makedirs("logs", exist_ok=True)
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    fmt = "%(asctime)s [%(levelname)s] %(name)s [%(job_id)s]: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    job_filter = JobIdFilter()

    # Console
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(fmt, datefmt))
    console.addFilter(job_filter)
    root.addHandler(console)

    # Arquivo rotativo
    file_h = logging.handlers.RotatingFileHandler(
        "logs/app.log", maxBytes=10_000_000, backupCount=5, encoding="utf-8"
    )
    file_h.setFormatter(logging.Formatter(fmt, datefmt))
    file_h.addFilter(job_filter)
    root.addHandler(file_h)

    # Override por módulo via env vars (ex: LOG_LEVEL_SERVICES.YAHOO_SCRAPER=DEBUG)
    for key, val in os.environ.items():
        if key.startswith("LOG_LEVEL_"):
            module = key[10:].lower().replace("_", ".")
            logging.getLogger(f"app.{module}").setLevel(val.upper())
