import asyncio
import json
import logging
import time
from datetime import date, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from pytz import timezone

from app.database import Base, SessionLocal, engine, seed_default_configs
from app.models.db_models import Alerta, Ativo, Transacao

logger = logging.getLogger(__name__)

BRT = timezone("America/Sao_Paulo")


def _criar_alerta_falha(tipo: str, mensagem: str):
    """Cria alerta de falha no DB para notificar o usuário."""
    try:
        from app.models.db_models import Alerta
        db = SessionLocal()
        db.add(Alerta(tipo=tipo, mensagem=mensagem, lido=False))
        db.commit()
        db.close()
    except Exception:
        logger.exception("[scheduler] Falha ao criar alerta de erro")


def atualizar_precos():
    """A cada 1h: atualiza preços dos ativos em carteira e cria snapshot."""
    from app.services.market_data import get_crypto_price, get_stock_price, to_crypto_id
    from app.services.portfolio_service import create_snapshot, get_posicoes

    t0 = time.perf_counter()
    logger.info("[scheduler] Atualizando preços...")
    db = SessionLocal()
    try:
        posicoes = get_posicoes(db)
        for pos in posicoes:
            ativo = pos["ativo"]
            if ativo.tipo == "acao":
                get_stock_price(ativo.ticker, db)
            elif ativo.tipo == "crypto":
                get_crypto_price(to_crypto_id(ativo.ticker), db)
        create_snapshot(db)
        elapsed = time.perf_counter() - t0
        logger.info(f"[scheduler] Preços atualizados para {len(posicoes)} ativos em {elapsed:.1f}s")
    except Exception:
        logger.exception("[scheduler] Erro atualizando preços")
    finally:
        db.close()


def verificar_lockups():
    """Diário 08:00: verifica lockups completados e gera alertas."""
    t0 = time.perf_counter()
    logger.info("[scheduler] Verificando lockups...")
    db = SessionLocal()
    try:
        hoje = date.today()
        # Transações de compra cujo lockup expira hoje ou expirou recentemente (últimos 2 dias)
        limite = hoje - timedelta(days=2)
        transacoes = (
            db.query(Transacao)
            .join(Ativo)
            .filter(
                Transacao.tipo_operacao == "compra",
                Transacao.lock_up_ate >= limite,
                Transacao.lock_up_ate <= hoje,
            )
            .all()
        )

        # Pre-load IDs de transações já alertadas (O(M) uma vez, não O(N*M))
        existing_alertas = (
            db.query(Alerta)
            .filter(Alerta.tipo == "lockup_expirado")
            .all()
        )
        alerted_ids: set[int] = set()
        for a in existing_alertas:
            if a.dados_json:
                try:
                    dados = json.loads(a.dados_json)
                    tid = dados.get("transacao_id")
                    if tid is not None:
                        alerted_ids.add(tid)
                except (json.JSONDecodeError, TypeError):
                    continue

        for t in transacoes:
            if t.id in alerted_ids:
                continue

            alerta = Alerta(
                tipo="lockup_expirado",
                mensagem=f"Lock-up expirado: {t.ativo.ticker} — {t.quantidade} unidades compradas em {t.data_operacao} já podem ser vendidas.",
                dados_json=json.dumps({
                    "transacao_id": t.id,
                    "ticker": t.ativo.ticker,
                    "lock_up_ate": str(t.lock_up_ate),
                }),
            )
            db.add(alerta)
            logger.info(f"[scheduler] Alerta lockup: {t.ativo.ticker}")

        db.commit()
        elapsed = time.perf_counter() - t0
        logger.info(f"[scheduler] Lockups verificados em {elapsed:.1f}s")
    except Exception:
        db.rollback()
        logger.exception("[scheduler] Erro verificando lockups")
    finally:
        db.close()


def rodar_analise_semanal():
    """Segunda 07:00: executa análise completa via Orchestrator."""
    t0 = time.perf_counter()
    logger.info("[scheduler] Iniciando análise semanal...")
    db = SessionLocal()
    try:
        from app.agents.orchestrator import Orchestrator

        orch = Orchestrator(db)
        orch.run_full_analysis()
        elapsed = time.perf_counter() - t0
        logger.info(f"[scheduler] Análise semanal concluída em {elapsed:.1f}s")
    except Exception as e:
        logger.exception("[scheduler] Erro na análise semanal")
        _criar_alerta_falha("analise_falhou", f"Análise semanal falhou: {type(e).__name__}: {str(e)[:200]}")
    finally:
        db.close()


def enviar_email_semanal():
    """Segunda 10:00: envia email com relatório semanal."""
    t0 = time.perf_counter()
    logger.info("[scheduler] Preparando email semanal...")
    db = SessionLocal()
    try:
        from app.services.email_service import send_weekly_report
        from app.services.portfolio_service import (
            get_portfolio_allocation,
            get_portfolio_assets,
            get_portfolio_summary,
        )

        summary = get_portfolio_summary(db)
        assets = get_portfolio_assets(db)
        allocation = get_portfolio_allocation(db)

        # Alertas não lidos
        alertas_db = db.query(Alerta).filter_by(lido=False).order_by(Alerta.data_criacao.desc()).limit(10).all()

        # Custos da semana
        from sqlalchemy import func

        from app.models.db_models import CustoToken

        semana_atras = datetime.now() - timedelta(days=7)
        total_usd = db.query(func.sum(CustoToken.custo_usd)).filter(CustoToken.data >= semana_atras).scalar() or 0
        total_brl = db.query(func.sum(CustoToken.custo_brl)).filter(CustoToken.data >= semana_atras).scalar() or 0

        data = {
            "data_relatorio": datetime.now().strftime("%d/%m/%Y"),
            "valor_total": summary["valor_total_brl"],
            "rentabilidade": summary["rentabilidade_pct"],
            "alocacao": [
                {"nome": "Ações B3", "atual": allocation["atual"].get("acoes", 0), "alvo": allocation["alvo"].get("acoes", 50), "desvio": allocation["desvio"].get("acoes", 0)},
                {"nome": "Cripto", "atual": allocation["atual"].get("crypto", 0), "alvo": allocation["alvo"].get("crypto", 20), "desvio": allocation["desvio"].get("crypto", 0)},
                {"nome": "CDB", "atual": allocation["atual"].get("cdb", 0), "alvo": allocation["alvo"].get("cdb", 30), "desvio": allocation["desvio"].get("cdb", 0)},
            ],
            "ativos": [
                {
                    "ticker": a["ticker"],
                    "nome": a["nome"],
                    "preco_atual": a["preco_atual"],
                    "pnl_pct": a["pnl_pct"],
                    "lockup_ativo": a["lockup_ativo"],
                    "dias_lockup": a["dias_lockup_restantes"],
                }
                for a in assets
            ],
            "alertas": [
                {"tipo": a.tipo, "mensagem": a.mensagem}
                for a in alertas_db
            ],
            "custos": {"total_usd": round(total_usd, 4), "total_brl": round(total_brl, 2)},
        }

        asyncio.run(send_weekly_report(data))
        elapsed = time.perf_counter() - t0
        logger.info(f"[scheduler] Email semanal enviado em {elapsed:.1f}s")
    except Exception as e:
        logger.exception("[scheduler] Erro enviando email")
        _criar_alerta_falha("email_falhou", f"Email semanal não enviado: {type(e).__name__}: {str(e)[:200]}")
    finally:
        db.close()


def create_scheduler() -> BackgroundScheduler:
    """Cria e configura o scheduler."""
    scheduler = BackgroundScheduler(timezone=BRT)

    # A cada 1 hora: atualizar preços
    scheduler.add_job(atualizar_precos, "interval", hours=1, id="atualizar_precos",
                      next_run_time=datetime.now(BRT) + timedelta(minutes=5))

    # Diário 08:00: verificar lockups
    scheduler.add_job(verificar_lockups, "cron", hour=8, minute=0, id="verificar_lockups")

    # Segunda 07:00: análise completa
    scheduler.add_job(rodar_analise_semanal, "cron", day_of_week="mon", hour=7, minute=0, id="analise_semanal")

    # Segunda 10:00: email semanal
    scheduler.add_job(enviar_email_semanal, "cron", day_of_week="mon", hour=10, minute=0, id="email_semanal")

    return scheduler


# Instância global exportável (usada pelo health check em main.py)
scheduler: BackgroundScheduler | None = None


if __name__ == "__main__":
    from app.logging_config import setup_logging
    setup_logging()

    # Inicializar banco
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    seed_default_configs(db)
    db.close()

    scheduler = create_scheduler()
    scheduler.start()
    globals()["scheduler"] = scheduler  # expor para health check
    logger.info("Scheduler iniciado. Pressione Ctrl+C para parar.")

    try:
        import time as _time
        while True:
            _time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("Scheduler encerrado.")
