import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import Base, SessionLocal, engine, seed_default_configs
from app.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando aplicação — criando tabelas e configs padrão")
    logger.info(f"DB: {settings.database_url}")
    logger.info(f"OPENAI_API_KEY: {'configurada' if settings.openai_api_key else 'AUSENTE'}")
    logger.info(f"GMAIL: {'configurado' if settings.gmail_user else 'não configurado'}")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_default_configs(db)
    finally:
        db.close()
    yield
    logger.info("Encerrando aplicação")
    from app.services.yahoo_scraper import close_pool
    await close_pool()


app = FastAPI(
    title="Sistema de Investimentos",
    description="Gestão de portfólio com multi-agentes IA",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Erro não tratado: {request.method} {request.url.path}")
    return JSONResponse(status_code=500, content={"detail": "Erro interno do servidor"})


# Routers
from app.routers import (  # noqa: E402
    alertas,
    analises,
    configuracoes,
    custos,
    market_data_router,
    portfolio,
    transacoes,
)

app.include_router(portfolio.router, prefix="/api")
app.include_router(transacoes.router, prefix="/api")
app.include_router(analises.router, prefix="/api")
app.include_router(alertas.router, prefix="/api")
app.include_router(custos.router, prefix="/api")
app.include_router(configuracoes.router, prefix="/api")
app.include_router(market_data_router.router, prefix="/api")


@app.get("/api/health")
def health_check():
    from datetime import datetime, timedelta

    from fastapi.responses import JSONResponse

    from app.config import settings
    from app.database import SessionLocal
    from app.models.db_models import PortfolioSnapshot

    issues = []

    # DB connectivity
    try:
        db = SessionLocal()
        db.execute("SELECT 1")
        db.close()
    except Exception as e:
        issues.append(f"db: {e}")

    # Dados frescos (último snapshot < 2h)
    try:
        db = SessionLocal()
        cutoff = datetime.now() - timedelta(hours=2)
        ultimo = db.query(PortfolioSnapshot).order_by(PortfolioSnapshot.data.desc()).first()
        db.close()
        if ultimo and ultimo.data < cutoff:
            issues.append(f"dados_stale: último snapshot {ultimo.data.isoformat()}")
    except Exception:
        pass  # não crítico

    # Scheduler ativo
    try:
        from app.scheduler import scheduler as _scheduler
        if _scheduler and not _scheduler.running:
            issues.append("scheduler: não está rodando")
    except Exception:
        pass  # scheduler pode não estar iniciado em dev

    # API key presente
    if not settings.openai_api_key:
        issues.append("openai_api_key: ausente")

    status = "degraded" if issues else "ok"
    code = 503 if issues else 200
    return JSONResponse(
        status_code=code,
        content={"status": status, "issues": issues, "ts": datetime.now().isoformat()},
    )
