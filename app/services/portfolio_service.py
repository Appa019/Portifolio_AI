import logging
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.db_models import Ativo, Configuracao, PortfolioSnapshot, Transacao
from app.services.market_data import get_crypto_price, get_stock_price, to_crypto_id

logger = logging.getLogger(__name__)

TIPO_CLASSE = {
    "acao": "acoes",
    "crypto": "crypto",
    "cdb": "cdb",
}


def _get_config_float(db: Session, chave: str, default: float = 0.0) -> float:
    cfg = db.query(Configuracao).filter_by(chave=chave).first()
    return float(cfg.valor) if cfg else default


def get_posicoes(db: Session) -> list[dict]:
    """Calcula posições atuais a partir das transações."""
    ativos = db.query(Ativo).options(joinedload(Ativo.transacoes)).all()
    posicoes = []

    for ativo in ativos:
        transacoes = sorted(ativo.transacoes, key=lambda t: t.data_operacao)

        quantidade = 0.0
        custo_total = 0.0
        lock_up_ate = None

        for t in transacoes:
            if t.tipo_operacao == "compra":
                custo_total += t.quantidade * t.preco_unitario
                quantidade += t.quantidade
                if t.lock_up_ate and (lock_up_ate is None or t.lock_up_ate > lock_up_ate):
                    lock_up_ate = t.lock_up_ate
            elif t.tipo_operacao == "venda":
                if quantidade > 0:
                    preco_medio = custo_total / quantidade
                    custo_total -= t.quantidade * preco_medio
                quantidade -= t.quantidade

        if quantidade <= 0:
            continue

        preco_medio = custo_total / quantidade if quantidade > 0 else 0

        posicoes.append({
            "ativo": ativo,
            "quantidade": quantidade,
            "preco_medio": round(preco_medio, 2),
            "custo_total": round(custo_total, 2),
            "lock_up_ate": lock_up_ate,
        })

    return posicoes


def get_portfolio_assets(db: Session) -> list[dict]:
    """Retorna lista detalhada de ativos no portfólio com preços atuais."""
    posicoes = get_posicoes(db)
    if not posicoes:
        return []

    # Calcular valor total para percentuais
    assets = []
    valor_total = 0.0

    for pos in posicoes:
        ativo = pos["ativo"]
        qtd = pos["quantidade"]
        pm = pos["preco_medio"]

        # Buscar preço atual
        preco_atual = 0.0
        if ativo.tipo == "acao":
            data = get_stock_price(ativo.ticker, db)
            preco_atual = data["preco"] if data else 0
        elif ativo.tipo == "crypto":
            data = get_crypto_price(to_crypto_id(ativo.ticker), db)
            preco_atual = data["preco_brl"] if data else 0
        elif ativo.tipo == "cdb":
            # CDB: valor = custo_total (rendimento calculado separadamente)
            preco_atual = pm

        valor = qtd * preco_atual
        valor_total += valor

        hoje = date.today()
        lockup_ativo = pos["lock_up_ate"] is not None and pos["lock_up_ate"] > hoje
        dias_lockup = (pos["lock_up_ate"] - hoje).days if lockup_ativo else 0

        pnl = valor - pos["custo_total"]
        pnl_pct = (pnl / pos["custo_total"] * 100) if pos["custo_total"] > 0 else 0

        assets.append({
            "id": ativo.id,
            "ticker": ativo.ticker,
            "nome": ativo.nome,
            "tipo": ativo.tipo,
            "setor": ativo.setor,
            "preco_atual": round(preco_atual, 2),
            "preco_medio": pm,
            "quantidade": qtd,
            "custo_total": pos["custo_total"],
            "valor_total": round(valor, 2),
            "pnl_brl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "pct_portfolio": 0.0,  # Calculado abaixo
            "dias_lockup_restantes": max(dias_lockup, 0),
            "lockup_ativo": lockup_ativo,
        })

    # Calcular percentual do portfólio
    if valor_total > 0:
        for a in assets:
            a["pct_portfolio"] = round(a["valor_total"] / valor_total * 100, 2)

    return assets


def get_portfolio_summary(db: Session) -> dict:
    """Resumo geral do portfólio."""
    assets = get_portfolio_assets(db)

    valor_total = sum(a["valor_total"] for a in assets)
    valor_investido = sum(a["custo_total"] for a in assets)
    lucro = valor_total - valor_investido
    rentabilidade = (lucro / valor_investido * 100) if valor_investido > 0 else 0

    # Alocação por classe
    alocacao = {"acoes": 0.0, "crypto": 0.0, "cdb": 0.0}
    if valor_total > 0:
        for a in assets:
            classe = TIPO_CLASSE.get(a["tipo"], "acoes")
            alocacao[classe] += a["valor_total"]
        for k in alocacao:
            alocacao[k] = round(alocacao[k] / valor_total * 100, 2)

    return {
        "valor_total_brl": round(valor_total, 2),
        "valor_investido_brl": round(valor_investido, 2),
        "rentabilidade_pct": round(rentabilidade, 2),
        "lucro_prejuizo_brl": round(lucro, 2),
        "num_ativos": len(assets),
        "alocacao": alocacao,
    }


def get_portfolio_allocation(db: Session) -> dict:
    """Alocação atual vs alvo."""
    summary = get_portfolio_summary(db)
    atual = summary["alocacao"]

    alvo = {
        "acoes": _get_config_float(db, "alocacao_acoes", 0.50) * 100,
        "crypto": _get_config_float(db, "alocacao_crypto", 0.20) * 100,
        "cdb": _get_config_float(db, "alocacao_cdb", 0.30) * 100,
    }

    desvio = {
        k: round(atual.get(k, 0) - alvo.get(k, 0), 2) for k in alvo
    }

    return {"atual": atual, "alvo": alvo, "desvio": desvio}


def get_portfolio_evolution(db: Session, periodo: str = "6m") -> list[dict]:
    """Série temporal de snapshots."""
    dias_map = {"1m": 30, "3m": 90, "6m": 180, "1a": 365, "max": 3650}
    dias = dias_map.get(periodo, 180)
    desde = date.today() - timedelta(days=dias)

    snapshots = (
        db.query(PortfolioSnapshot)
        .filter(PortfolioSnapshot.data >= desde)
        .order_by(PortfolioSnapshot.data)
        .all()
    )

    return [
        {"data": s.data, "valor_total": s.valor_total_brl}
        for s in snapshots
    ]


def check_lockup(db: Session, ativo_id: int, data_venda: date) -> bool:
    """Verifica se o ativo pode ser vendido (lock-up expirado)."""
    lockup_dias = int(_get_config_float(db, "lockup_dias", 30))

    ultima_compra = (
        db.query(Transacao)
        .filter_by(ativo_id=ativo_id, tipo_operacao="compra")
        .order_by(Transacao.data_operacao.desc())
        .first()
    )

    if not ultima_compra:
        return True

    lock_up_ate = ultima_compra.data_operacao + timedelta(days=lockup_dias)
    return data_venda >= lock_up_ate


def create_snapshot(db: Session):
    """Cria um snapshot do portfólio atual."""
    summary = get_portfolio_summary(db)
    alocacao = summary["alocacao"]

    snapshot = PortfolioSnapshot(
        data=func.now(),
        valor_total_brl=summary["valor_total_brl"],
        pct_acoes=alocacao.get("acoes", 0),
        pct_crypto=alocacao.get("crypto", 0),
        pct_cdb=alocacao.get("cdb", 0),
        rentabilidade_total_pct=summary["rentabilidade_pct"],
    )
    db.add(snapshot)
    db.commit()
    return snapshot
