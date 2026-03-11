import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

logger = logging.getLogger(__name__)

from app.database import get_db
from app.models.db_models import Ativo, Transacao
from app.routers.market_data_router import _CRYPTO_TICKERS
from app.schemas.api_schemas import TransacaoCreate, TransacaoOut
from app.services.market_data import is_crypto
from app.services.portfolio_service import check_lockup

router = APIRouter(prefix="/transacoes", tags=["Transações"])

CDB_KEYWORDS = ("CDB", "LCI", "LCA", "TESOURO")


def _detect_tipo(ticker: str) -> str:
    upper = ticker.upper()
    if is_crypto(ticker) or ticker.lower() in _CRYPTO_TICKERS:
        return "crypto"
    if any(kw in upper for kw in CDB_KEYWORDS):
        return "cdb"
    return "acao"


def _to_out(t: Transacao) -> TransacaoOut:
    return TransacaoOut(
        id=t.id,
        ativo_id=t.ativo_id,
        ticker=t.ativo.ticker if t.ativo else "",
        nome_ativo=t.ativo.nome if t.ativo else "",
        tipo_operacao=t.tipo_operacao,
        quantidade=t.quantidade,
        preco_unitario=t.preco_unitario,
        data_operacao=t.data_operacao,
        lock_up_ate=t.lock_up_ate,
        observacao=t.observacao,
        criado_em=t.criado_em,
    )


@router.get("/", response_model=list[TransacaoOut])
def listar(
    tipo: str | None = Query(None, pattern="^(compra|venda)$"),
    ticker: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(Transacao).options(joinedload(Transacao.ativo))
    if tipo:
        q = q.filter(Transacao.tipo_operacao == tipo)
    if ticker:
        q = q.join(Ativo).filter(Ativo.ticker == ticker.upper())
    transacoes = q.order_by(Transacao.data_operacao.desc()).offset(offset).limit(limit).all()
    return [_to_out(t) for t in transacoes]


@router.post("/", response_model=TransacaoOut, status_code=201)
def criar(payload: TransacaoCreate, db: Session = Depends(get_db)):
    ticker_upper = payload.ticker.upper()
    tipo_ativo = _detect_tipo(ticker_upper)

    # Find or create ativo
    ativo = db.query(Ativo).filter_by(ticker=ticker_upper).first()
    if not ativo:
        ativo = Ativo(ticker=ticker_upper, tipo=tipo_ativo, nome=ticker_upper)
        db.add(ativo)
        try:
            db.flush()
        except Exception:
            logger.exception(f"Flush falhou para ativo '{ticker_upper}' — possível race condition")
            db.rollback()
            # Race condition: outro request criou o mesmo ticker — re-query
            ativo = db.query(Ativo).filter_by(ticker=ticker_upper).first()
            if not ativo:
                raise HTTPException(status_code=400, detail=f"Erro ao criar ativo '{ticker_upper}' no banco de dados")

    # Validar lockup em vendas
    if payload.tipo_operacao == "venda":
        if not check_lockup(db, ativo.id, payload.data_operacao):
            raise HTTPException(
                status_code=400,
                detail=f"Lock-up ativo: {ticker_upper} ainda está no período de 30 dias após a última compra.",
            )

    # Calcular lock_up_ate para compras
    lock_up_ate = None
    if payload.tipo_operacao == "compra":
        lock_up_ate = payload.data_operacao + timedelta(days=30)

    transacao = Transacao(
        ativo_id=ativo.id,
        tipo_operacao=payload.tipo_operacao,
        quantidade=payload.quantidade,
        preco_unitario=payload.preco_unitario,
        data_operacao=payload.data_operacao,
        lock_up_ate=lock_up_ate,
        observacao=payload.observacao,
    )
    db.add(transacao)
    try:
        db.commit()
    except Exception:
        logger.exception(f"Commit falhou para transação {ticker_upper}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro ao salvar transação no banco de dados")
    db.refresh(transacao)
    return _to_out(transacao)


@router.get("/{transacao_id}", response_model=TransacaoOut)
def detalhe(transacao_id: int, db: Session = Depends(get_db)):
    t = db.query(Transacao).options(joinedload(Transacao.ativo)).filter_by(id=transacao_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Transação não encontrada")
    return _to_out(t)
