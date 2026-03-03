from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    echo=False,
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DEFAULT_CONFIGS = {
    "alocacao_acoes": "0.50",
    "alocacao_crypto": "0.20",
    "alocacao_cdb": "0.30",
    "lockup_dias": "30",
    "perfil_risco": "moderado",
    "email_destinatario": "pedropestana.fgv@gmail.com",
    "intervalo_atualizacao_horas": "1",
}


def seed_default_configs(db_session):
    from app.models.db_models import Configuracao

    for chave, valor in DEFAULT_CONFIGS.items():
        existing = db_session.query(Configuracao).filter_by(chave=chave).first()
        if not existing:
            db_session.add(Configuracao(chave=chave, valor=valor))
    db_session.commit()
