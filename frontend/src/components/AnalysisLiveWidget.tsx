import { useState, useEffect, useRef, useCallback } from 'react'
import { Minimize2, Maximize2 } from 'lucide-react'
import type { ProgressEvent } from '../api/client'

const STEP_LABELS: Record<string, string> = {
  connected: 'Conectado',
  pipeline_start: 'Pipeline',
  pipeline_done: 'Concluído',
  phase_start: 'Fase',
  orchestrator_start: 'Orquestrador',
  agent_start: 'Agente',
  agent_thinking: 'Pensando',
  function_call: 'Executando',
  prefetch: 'Pre-carregando',
  done: 'Concluído',
  error: 'Erro',
  warning: 'Aviso',
  agent_timeout: 'Timeout',
}

const AGENT_NAMES: Record<string, string> = {
  cio: 'Carlos Mendonça (CIO)',
  head_b3: 'Marcelo Tavares (Head B3)',
  head_crypto: 'Luísa Nakamoto (Head Crypto)',
  cro: 'Fernando Rocha (CRO)',
  fundamentalista_b3: 'Ricardo Moura (Fundamentalista)',
  tecnico_b3: 'Bruno Kato (Técnico)',
  setorial_b3: 'Beatriz Almeida (Setorial)',
  risk_b3: 'Patrícia Campos (Risk)',
  trade_b3: 'Diego Lopes (Trade)',
  fundamentalista_crypto: 'Thiago Satoshi (Fundamentalista)',
  tecnico_crypto: 'Juliana Pires (Técnica)',
  onchain_analyst: 'Lucas Webb (On-Chain)',
  risk_crypto: 'André Faria (Risk)',
  trade_crypto: 'Camila Duarte (Trade)',
  macro_economist: 'Helena Bastos (Macro)',
  sentiment_analyst: 'Marina Leal (Sentimento)',
  compliance_officer: 'Rafael Tanaka (Compliance)',
  quant_analyst: 'Eduardo Queiroz (Quant)',
}

function resolveAgentLabel(agentName?: string): string {
  if (!agentName) return ''
  if (AGENT_NAMES[agentName]) return AGENT_NAMES[agentName]
  if (agentName.startsWith('ticker_analyst_')) return `Analista ${agentName.replace('ticker_analyst_', '')}`
  if (agentName.startsWith('crypto_analyst_')) return `Analista ${agentName.replace('crypto_analyst_', '').replace(/^\w/, c => c.toUpperCase())}`
  return agentName
}

interface Props {
  jobId: string | null
  onDone: () => void
}

export default function AnalysisLiveWidget({ jobId, onDone }: Props) {
  const [events, setEvents] = useState<ProgressEvent[]>([])
  const [percent, setPercent] = useState(0)
  const [collapsed, setCollapsed] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const doneTimerRef = useRef<ReturnType<typeof setTimeout>>()
  const stableOnDone = useCallback(onDone, [onDone])

  useEffect(() => {
    if (!jobId) { setEvents([]); setPercent(0); return }

    clearTimeout(doneTimerRef.current)
    const es = new EventSource(`/api/analises/stream/${jobId}`)

    es.onmessage = (e) => {
      let event: ProgressEvent
      try {
        event = JSON.parse(e.data)
      } catch {
        setEvents(prev => [...prev, { step: 'error', message: 'Evento SSE malformado recebido.' }])
        return
      }
      if (event.step === 'heartbeat') return
      setEvents(prev => [...prev.slice(-100), event])
      if (event.percent && event.percent > 0) setPercent(event.percent)
      if (event.step === 'done') {
        es.close()
        doneTimerRef.current = setTimeout(stableOnDone, 3000)
      }
    }

    es.onerror = () => {
      es.close()
      setEvents(prev => [...prev, { step: 'error', message: 'Conexao com o servidor perdida.' }])
    }

    return () => { es.close(); clearTimeout(doneTimerRef.current) }
  }, [jobId, stableOnDone])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [events])

  if (!jobId) return null

  const lastEvent = events[events.length - 1]
  const isDone = lastEvent?.step === 'done'
  const isError = lastEvent?.step === 'error'

  const barColor = isDone ? '#16a34a' : isError ? '#dc2626' : '#15803d'
  const statusText = isDone ? 'Analise concluida' : isError ? 'Erro na analise' : 'Analise em andamento...'

  return (
    <div className="overflow-hidden" style={{
      background: '#ffffff', border: '1px solid #e2e8f0',
      boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
    }}>
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3"
           style={{ borderBottom: '1px solid #e2e8f0' }}>
        <div className="flex items-center gap-2">
          {!isDone && !isError && <div className="w-2 h-2 bg-yellow-400 animate-pulse" />}
          {isDone && <div className="w-2 h-2 bg-green-500" />}
          {isError && <div className="w-2 h-2 bg-red-500" />}
          <span className="text-sm font-semibold" style={{ color: '#111827' }}>
            {statusText}
          </span>
          {percent > 0 && (
            <span className="text-xs font-medium ml-2" style={{ color: '#6b7280' }}>
              {percent}%
            </span>
          )}
        </div>
        <button onClick={() => setCollapsed(!collapsed)}
          className="p-1 transition-colors"
          style={{ color: '#6b7280' }}
          onMouseEnter={e => (e.currentTarget.style.background = '#f1f3f5')}
          onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
        >
          {collapsed ? <Maximize2 size={14} /> : <Minimize2 size={14} />}
        </button>
      </div>

      {/* Progress bar */}
      <div className="h-1" style={{ background: '#f1f3f5' }}>
        <div className="h-full transition-all duration-500"
             style={{ width: `${percent}%`, background: barColor }} />
      </div>

      {/* Event timeline */}
      {!collapsed && (
        <div ref={scrollRef} className="px-5 py-3 space-y-1.5 max-h-64 overflow-y-auto"
             style={{ scrollbarWidth: 'thin' }}>
          {events.filter(e => e.step !== 'connected').map((e, i) => {
            const isPhase = e.step === 'phase_start' || e.step === 'pipeline_start' || e.step === 'pipeline_done'
            const agentLabel = e.agent ? resolveAgentLabel(e.agent) : ''
            return (
              <div key={i} className={`flex items-start gap-2 text-xs ${isPhase ? 'mt-2 mb-1' : ''}`}
                   style={{ color: e.step === 'error' ? '#dc2626' : '#6b7280' }}>
                <span className="flex-shrink-0 px-1.5 py-0.5 text-[10px] font-medium"
                      style={{
                        background: e.step === 'done' || e.step === 'pipeline_done' ? '#dcfce7' :
                                    e.step === 'error' ? '#fef2f2' :
                                    isPhase ? 'rgba(37,99,235,0.1)' :
                                    'rgba(21,128,61,0.1)',
                        color: e.step === 'done' || e.step === 'pipeline_done' ? '#16a34a' :
                               e.step === 'error' ? '#dc2626' :
                               isPhase ? '#2563eb' :
                               '#15803d',
                        fontWeight: isPhase ? 700 : 500,
                      }}>
                  {STEP_LABELS[e.step] || e.step}
                </span>
                <span className="leading-relaxed">
                  {agentLabel && <span className="font-medium" style={{ color: '#111827' }}>{agentLabel} </span>}
                  {e.message}
                </span>
              </div>
            )
          })}
          {!isDone && !isError && events.length > 0 && (
            <div className="flex items-center gap-2 text-xs animate-pulse"
                 style={{ color: '#15803d' }}>
              <span className="w-1.5 h-1.5 bg-green-500" />
              <span>Processando...</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
