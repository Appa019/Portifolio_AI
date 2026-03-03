from datetime import date, datetime

from pydantic import BaseModel, Field


# === Ativos ===


class AtivoOut(BaseModel):
    id: int
    ticker: str
    tipo: str
    nome: str
    setor: str | None = None
    exchange: str | None = None

    model_config = {"from_attributes": True}


# === Transacoes ===


class TransacaoCreate(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=20)
    tipo_operacao: str = Field(..., pattern="^(compra|venda)$")
    quantidade: float = Field(..., gt=0)
    preco_unitario: float = Field(..., gt=0)
    data_operacao: date
    observacao: str | None = None


class TransacaoOut(BaseModel):
    id: int
    ativo_id: int
    ticker: str = ""
    nome_ativo: str = ""
    tipo_operacao: str
    quantidade: float
    preco_unitario: float
    data_operacao: date
    lock_up_ate: date | None = None
    observacao: str | None = None
    criado_em: datetime

    model_config = {"from_attributes": True}


# === Portfolio ===


class AlocacaoAtual(BaseModel):
    acoes: float = 0.0
    crypto: float = 0.0
    cdb: float = 0.0


class AlocacaoAlvo(BaseModel):
    acoes: float = 50.0
    crypto: float = 20.0
    cdb: float = 30.0


class PortfolioResumo(BaseModel):
    valor_total_brl: float = 0.0
    valor_investido_brl: float = 0.0
    rentabilidade_pct: float = 0.0
    lucro_prejuizo_brl: float = 0.0
    num_ativos: int = 0
    alocacao: AlocacaoAtual = AlocacaoAtual()


class AtivoPortfolio(BaseModel):
    id: int
    ticker: str
    nome: str
    tipo: str
    setor: str | None = None
    preco_atual: float = 0.0
    preco_medio: float = 0.0
    quantidade: float = 0.0
    valor_total: float = 0.0
    pnl_brl: float = 0.0
    pnl_pct: float = 0.0
    pct_portfolio: float = 0.0
    dias_lockup_restantes: int = 0
    lockup_ativo: bool = False


class PortfolioEvolucaoItem(BaseModel):
    data: datetime
    valor_total: float


class PortfolioAlocacao(BaseModel):
    atual: AlocacaoAtual = AlocacaoAtual()
    alvo: AlocacaoAlvo = AlocacaoAlvo()
    desvio: AlocacaoAtual = AlocacaoAtual()


# === Analises IA ===


class AnaliseExecutarRequest(BaseModel):
    pass


class AnaliseAporteRequest(BaseModel):
    valor: float = Field(..., gt=0)


class AnaliseOut(BaseModel):
    id: int
    data: datetime
    tipo_analise: str
    agente: str
    input_resumo: str
    score_confianca: float | None = None
    acao_recomendada: str | None = None
    executada: bool = False

    model_config = {"from_attributes": True}


class AnaliseDetalheOut(AnaliseOut):
    output_completo: str = ""


# === Alertas ===


class AlertaOut(BaseModel):
    id: int
    tipo: str
    mensagem: str
    dados_json: str | None = None
    data_criacao: datetime
    lido: bool = False

    model_config = {"from_attributes": True}


# === Custos Tokens ===


class CustoTokenOut(BaseModel):
    id: int
    data: datetime
    agente: str
    modelo: str
    tokens_input: int
    tokens_output: int
    custo_usd: float
    cotacao_dolar: float
    custo_brl: float
    descricao: str | None = None

    model_config = {"from_attributes": True}


class CustoAgente(BaseModel):
    agente: str
    total_brl: float
    total_usd: float


class CustoMes(BaseModel):
    mes: str
    total_brl: float


class CustoResumo(BaseModel):
    total_usd: float = 0.0
    total_brl: float = 0.0
    media_por_analise_brl: float = 0.0
    cotacao_dolar_atual: float = 0.0
    por_agente: list[CustoAgente] = []
    por_mes: list[CustoMes] = []


# === Configuracoes ===


class ConfiguracaoOut(BaseModel):
    chave: str
    valor: str
    atualizado_em: datetime

    model_config = {"from_attributes": True}


class ConfiguracaoUpdate(BaseModel):
    configuracoes: dict[str, str]


