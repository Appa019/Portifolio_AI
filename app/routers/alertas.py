import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.db_models import Alerta
from app.schemas.api_schemas import AlertaOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alertas", tags=["Alertas"])


@router.get("/", response_model=list[AlertaOut])
def listar(
    lido: bool | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(Alerta)
    if lido is not None:
        q = q.filter(Alerta.lido == lido)
    alertas = q.order_by(Alerta.data_criacao.desc()).offset(offset).limit(limit).all()
    return alertas


@router.patch("/{alerta_id}/marcar-lido", response_model=AlertaOut)
def marcar_lido(alerta_id: int, db: Session = Depends(get_db)):
    alerta = db.query(Alerta).filter_by(id=alerta_id).first()
    if not alerta:
        raise HTTPException(status_code=404, detail="Alerta não encontrado")
    alerta.lido = True
    try:
        db.commit()
        db.refresh(alerta)
    except Exception:
        logger.exception(f"Commit falhou ao marcar alerta {alerta_id} como lido")
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro ao atualizar alerta")
    return alerta
