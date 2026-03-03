import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, SessionLocal, engine, seed_default_configs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando aplicação — criando tabelas e configs padrão")
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
    return {"status": "ok"}
