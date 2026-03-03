from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.db_models import CustoToken
from app.schemas.api_schemas import CustoAgente, CustoMes, CustoResumo, CustoTokenOut
from app.services.market_data import get_ptax

router = APIRouter(prefix="/custos", tags=["Custos Tokens"])


@router.get("/", response_model=list[CustoTokenOut])
def listar(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    custos = (
        db.query(CustoToken)
        .order_by(CustoToken.data.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return custos


@router.get("/resumo", response_model=CustoResumo)
def resumo(db: Session = Depends(get_db)):
    total_usd = db.query(func.sum(CustoToken.custo_usd)).scalar() or 0.0
    total_brl = db.query(func.sum(CustoToken.custo_brl)).scalar() or 0.0
    count = db.query(func.count(CustoToken.id)).scalar() or 0

    # Por agente
    por_agente_q = (
        db.query(
            CustoToken.agente,
            func.sum(CustoToken.custo_brl).label("total_brl"),
            func.sum(CustoToken.custo_usd).label("total_usd"),
        )
        .group_by(CustoToken.agente)
        .all()
    )
    por_agente = [
        CustoAgente(agente=row.agente, total_brl=round(row.total_brl, 4), total_usd=round(row.total_usd, 6))
        for row in por_agente_q
    ]

    # Por mês
    por_mes_q = (
        db.query(
            func.strftime("%Y-%m", CustoToken.data).label("mes"),
            func.sum(CustoToken.custo_brl).label("total_brl"),
        )
        .group_by(func.strftime("%Y-%m", CustoToken.data))
        .order_by(func.strftime("%Y-%m", CustoToken.data).desc())
        .all()
    )
    por_mes = [CustoMes(mes=row.mes, total_brl=round(row.total_brl, 4)) for row in por_mes_q]

    return CustoResumo(
        total_usd=round(total_usd, 6),
        total_brl=round(total_brl, 4),
        media_por_analise_brl=round(total_brl / count, 4) if count > 0 else 0.0,
        cotacao_dolar_atual=get_ptax(),
        por_agente=por_agente,
        por_mes=por_mes,
    )


@router.get("/por-agente", response_model=list[CustoAgente])
def por_agente(db: Session = Depends(get_db)):
    rows = (
        db.query(
            CustoToken.agente,
            func.sum(CustoToken.custo_brl).label("total_brl"),
            func.sum(CustoToken.custo_usd).label("total_usd"),
        )
        .group_by(CustoToken.agente)
        .all()
    )
    return [
        CustoAgente(agente=row.agente, total_brl=round(row.total_brl, 4), total_usd=round(row.total_usd, 6))
        for row in rows
    ]
