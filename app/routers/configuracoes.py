from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.db_models import Configuracao
from app.schemas.api_schemas import ConfiguracaoOut, ConfiguracaoUpdate

router = APIRouter(prefix="/configuracoes", tags=["Configurações"])


@router.get("/", response_model=list[ConfiguracaoOut])
def listar(db: Session = Depends(get_db)):
    return db.query(Configuracao).order_by(Configuracao.chave).all()


@router.patch("/", response_model=list[ConfiguracaoOut])
def atualizar(payload: ConfiguracaoUpdate, db: Session = Depends(get_db)):
    for chave, valor in payload.configuracoes.items():
        cfg = db.query(Configuracao).filter_by(chave=chave).first()
        if cfg:
            cfg.valor = valor
        else:
            db.add(Configuracao(chave=chave, valor=valor))
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro ao salvar configurações")
    return db.query(Configuracao).order_by(Configuracao.chave).all()
