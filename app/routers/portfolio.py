from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.api_schemas import (
    AtivoPortfolio,
    PortfolioAlocacao,
    PortfolioEvolucaoItem,
    PortfolioResumo,
)
from app.services.portfolio_service import (
    get_portfolio_allocation,
    get_portfolio_assets,
    get_portfolio_evolution,
    get_portfolio_summary,
)

router = APIRouter(prefix="/portfolio", tags=["Portfolio"])


@router.get("/", response_model=PortfolioResumo)
def resumo(db: Session = Depends(get_db)):
    return get_portfolio_summary(db)


@router.get("/ativos", response_model=list[AtivoPortfolio])
def ativos(db: Session = Depends(get_db)):
    return get_portfolio_assets(db)


@router.get("/alocacao", response_model=PortfolioAlocacao)
def alocacao(db: Session = Depends(get_db)):
    return get_portfolio_allocation(db)


@router.get("/evolucao", response_model=list[PortfolioEvolucaoItem])
def evolucao(
    periodo: str = Query("6m", pattern="^(1m|3m|6m|1a|max)$"),
    db: Session = Depends(get_db),
):
    return get_portfolio_evolution(db, periodo)
