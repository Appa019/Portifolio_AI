import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.ensemble import progress as progress_mod
from app.models.db_models import AnaliseIA
from app.schemas.api_schemas import (
    AnaliseAporteRequest,
    AnaliseDetalheOut,
    AnaliseOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analises", tags=["Análises IA"])


@router.get("/", response_model=list[AnaliseOut])
def listar(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    analises = (
        db.query(AnaliseIA)
        .order_by(AnaliseIA.data.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return analises


def _run_analysis(executor_fn, db_factory, job_id: str | None = None, error_msg: str = "Erro na análise"):
    """Executa uma análise em background via executor_fn(orch, job_id)."""
    from app.agents.orchestrator import Orchestrator
    from app.logging_config import set_job_id

    set_job_id(job_id)
    db = None
    try:
        db = db_factory()
        orch = Orchestrator(db, job_id=job_id)
        executor_fn(orch, job_id)
    except Exception as e:
        logger.exception(f"{error_msg}: {e}")
        progress_mod.emit(job_id, "error", f"Erro: {str(e)}", 0)
    finally:
        progress_mod.done(job_id)
        set_job_id(None)
        if db:
            db.close()


@router.post("/executar", status_code=202)
async def executar_analise(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    from app.database import SessionLocal

    job_id = str(uuid.uuid4())
    loop = asyncio.get_running_loop()
    progress_mod.register_job(job_id, loop)

    background_tasks.add_task(
        _run_analysis,
        lambda orch, jid: orch.run_full_analysis(job_id=jid),
        SessionLocal,
        job_id,
        "Erro na análise completa",
    )
    return {"mensagem": "Análise completa iniciada em background", "job_id": job_id}


@router.post("/aporte", status_code=202)
async def analise_aporte(
    payload: AnaliseAporteRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    from app.database import SessionLocal

    job_id = str(uuid.uuid4())
    loop = asyncio.get_running_loop()
    progress_mod.register_job(job_id, loop)

    valor = payload.valor
    background_tasks.add_task(
        _run_analysis,
        lambda orch, jid: orch.run_aporte_analysis(valor, job_id=jid),
        SessionLocal,
        job_id,
        f"Erro na análise de aporte R${valor:,.2f}",
    )
    return {
        "mensagem": f"Análise de aporte de R${payload.valor:,.2f} iniciada em background",
        "job_id": job_id,
    }


@router.get("/stream/{job_id}")
async def stream_progress(job_id: str):
    """SSE endpoint para acompanhar progresso ao vivo."""
    queue = progress_mod.get_queue(job_id)
    if not queue:
        raise HTTPException(404, "Job não encontrado ou já concluído")

    async def event_generator():
        yield f"data: {json.dumps({'step': 'connected', 'message': 'Conectado ao stream'})}\n\n"
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'step': 'heartbeat', 'message': 'alive'})}\n\n"
                    continue

                yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"

                if event.get("step") == "done":
                    break
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/{analise_id}", response_model=AnaliseDetalheOut)
def detalhe(analise_id: int, db: Session = Depends(get_db)):
    analise = db.query(AnaliseIA).filter_by(id=analise_id).first()
    if not analise:
        raise HTTPException(status_code=404, detail="Análise não encontrada")
    return analise
