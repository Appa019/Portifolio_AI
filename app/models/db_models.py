from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Ativo(Base):
    __tablename__ = "ativos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    tipo: Mapped[str] = mapped_column(String(10), nullable=False)  # "acao", "crypto", "cdb"
    nome: Mapped[str] = mapped_column(String(100), default="")
    setor: Mapped[str | None] = mapped_column(String(100), nullable=True)
    exchange: Mapped[str | None] = mapped_column(String(20), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    transacoes: Mapped[list["Transacao"]] = relationship(back_populates="ativo")


class Transacao(Base):
    __tablename__ = "transacoes"
    __table_args__ = (
        Index("ix_transacao_ativo_data", "ativo_id", "data_operacao"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ativo_id: Mapped[int] = mapped_column(Integer, ForeignKey("ativos.id"), nullable=False)
    tipo_operacao: Mapped[str] = mapped_column(String(10), nullable=False)  # "compra" ou "venda"
    quantidade: Mapped[float] = mapped_column(Float, nullable=False)
    preco_unitario: Mapped[float] = mapped_column(Float, nullable=False)
    data_operacao: Mapped[date] = mapped_column(Date, nullable=False)
    lock_up_ate: Mapped[date | None] = mapped_column(Date, nullable=True)
    observacao: Mapped[str | None] = mapped_column(String(500), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    ativo: Mapped["Ativo"] = relationship(back_populates="transacoes")


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshot"
    __table_args__ = (
        Index("ix_snapshot_data", "data"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    valor_total_brl: Mapped[float] = mapped_column(Float, nullable=False)
    pct_acoes: Mapped[float | None] = mapped_column(Float, nullable=True)
    pct_crypto: Mapped[float | None] = mapped_column(Float, nullable=True)
    pct_cdb: Mapped[float | None] = mapped_column(Float, nullable=True)
    rentabilidade_total_pct: Mapped[float | None] = mapped_column(Float, nullable=True)


class AnalysisRun(Base):
    """Groups all agent executions within a single analysis pipeline run."""
    __tablename__ = "analysis_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running, completed, failed, budget_exceeded
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    total_cost_brl: Mapped[float] = mapped_column(Float, default=0.0)
    total_agents: Mapped[int] = mapped_column(Integer, default=0)
    phases_completed: Mapped[int] = mapped_column(Integer, default=0)
    trigger: Mapped[str] = mapped_column(String(20), default="manual")  # scheduled, manual, telegram, aporte

    analises: Mapped[list["AnaliseIA"]] = relationship(back_populates="run")
    custos: Mapped[list["CustoToken"]] = relationship(back_populates="run")


class AnaliseIA(Base):
    __tablename__ = "analises_ia"
    __table_args__ = (
        Index("ix_analise_data", "data"),
        Index("ix_analise_agente", "agente"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    tipo_analise: Mapped[str] = mapped_column(String(30), nullable=False)
    agente: Mapped[str] = mapped_column(String(100), nullable=False)
    input_resumo: Mapped[str] = mapped_column(Text, default="")
    output_completo: Mapped[str] = mapped_column(Text, default="")
    score_confianca: Mapped[float | None] = mapped_column(Float, nullable=True)
    acao_recomendada: Mapped[str | None] = mapped_column(Text, nullable=True)
    executada: Mapped[bool] = mapped_column(Boolean, default=False)
    run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("analysis_runs.id"), nullable=True)

    run: Mapped["AnalysisRun | None"] = relationship(back_populates="analises")


class CustoToken(Base):
    __tablename__ = "custos_tokens"
    __table_args__ = (
        Index("ix_custo_agente_data", "agente", "data"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    agente: Mapped[str] = mapped_column(String(100), nullable=False)
    modelo: Mapped[str] = mapped_column(String(20), nullable=False)
    tokens_input: Mapped[int] = mapped_column(Integer, nullable=False)
    tokens_output: Mapped[int] = mapped_column(Integer, nullable=False)
    custo_usd: Mapped[float] = mapped_column(Float, nullable=False)
    cotacao_dolar: Mapped[float] = mapped_column(Float, nullable=False)
    custo_brl: Mapped[float] = mapped_column(Float, nullable=False)
    descricao: Mapped[str | None] = mapped_column(String(200), nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("analysis_runs.id"), nullable=True)

    run: Mapped["AnalysisRun | None"] = relationship(back_populates="custos")


class Configuracao(Base):
    __tablename__ = "configuracoes"

    chave: Mapped[str] = mapped_column(String(50), primary_key=True)
    valor: Mapped[str] = mapped_column(String(200), nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Alerta(Base):
    __tablename__ = "alertas"
    __table_args__ = (
        Index("ix_alerta_lido_data", "lido", "data_criacao"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    mensagem: Mapped[str] = mapped_column(Text, nullable=False)
    dados_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_criacao: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    lido: Mapped[bool] = mapped_column(Boolean, default=False)


class CachePreco(Base):
    __tablename__ = "cache_precos"
    __table_args__ = (
        Index("ix_cache_precos_lookup", "ticker", "fonte", "tipo_dado", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    fonte: Mapped[str] = mapped_column(String(20), nullable=False)
    tipo_dado: Mapped[str] = mapped_column(String(20), nullable=False)
    dados_json: Mapped[str] = mapped_column(Text, nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expira_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class AgentContext(Base):
    __tablename__ = "agent_contexts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    last_response_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_execution: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resumo_contexto: Mapped[str | None] = mapped_column(Text, nullable=True)
    dados_persistentes: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_count: Mapped[int] = mapped_column(Integer, default=0)


class TelegramConversation(Base):
    """Logs all Telegram bot interactions for audit and context."""
    __tablename__ = "telegram_conversations"
    __table_args__ = (
        Index("ix_telegram_chat_bot", "chat_id", "bot_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(Integer, nullable=False)
    bot_type: Mapped[str] = mapped_column(String(20), nullable=False)  # ceo, mesa_b3, mesa_crypto
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    message_text: Mapped[str] = mapped_column(Text, default="")
    response_text: Mapped[str] = mapped_column(Text, default="")
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
