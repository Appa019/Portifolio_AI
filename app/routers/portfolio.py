from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.api_schemas import (
    AtivoPortfolio,
    PortfolioAlocacao,
    PortfolioEvolucaoItem,
    PortfolioResumo,
)
from app.services.portfolio_service import (
    _get_config_float,
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


@router.get("/benchmark")
def benchmark_passivo(
    inicio: str = Query("2021-01-01", description="Data de início YYYY-MM-DD"),
    rebalancear: bool = Query(True, description="Rebalancear mensalmente para o alvo"),
    db: Session = Depends(get_db),
):
    """Simula benchmark passivo (BOVA11 + BTC + CDI) com a mesma alocação-alvo do portfólio.

    Resposta inclui série diária + métricas (retorno total, CAGR, Sharpe, max drawdown).
    Use para comparar se a carteira ativa supera a alocação passiva equivalente.
    """
    from app.services.backtest import run_passive_benchmark

    alloc_acoes = _get_config_float(db, "alocacao_acoes", 0.50)
    alloc_crypto = _get_config_float(db, "alocacao_crypto", 0.20)
    alloc_cdb = _get_config_float(db, "alocacao_cdb", 0.30)

    result = run_passive_benchmark(
        start_date=inicio,
        alloc_acoes=alloc_acoes,
        alloc_crypto=alloc_crypto,
        alloc_cdb=alloc_cdb,
        rebalance_monthly=rebalancear,
    )

    if "erro" in result:
        raise HTTPException(status_code=503, detail=result["erro"])

    return result
