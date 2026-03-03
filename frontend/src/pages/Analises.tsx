import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { BrainCircuit, Play, ChevronDown, ChevronUp, Loader2 } from 'lucide-react'
import { getAnalises, executarAnalise, executarAnaliseAporte, formatDataHora } from '../api/client'
import type { ExecutarResponse } from '../api/client'
import { useToast } from '../components/ui/Toast'
import EmptyState from '../components/ui/EmptyState'
import { SkeletonCard } from '../components/ui/Skeleton'

export default function Analises() {
  const qc = useQueryClient()
  const { toast } = useToast()
  const [expandido, setExpandido] = useState<number | null>(null)
  const [valorAporte, setValorAporte] = useState('')

  const { data: analises = [], isLoading } = useQuery({ queryKey: ['analises'], queryFn: getAnalises })

  const notifyDashboard = (jobId: string) => {
    window.dispatchEvent(new CustomEvent('analysis-started', { detail: jobId }))
  }

  const mutAnalise = useMutation({
    mutationFn: executarAnalise,
    onSuccess: (data: ExecutarResponse) => {
      toast('Analise disparada! Acompanhe o progresso em tempo real.', 'success')
      notifyDashboard(data.job_id)
      qc.invalidateQueries({ queryKey: ['analises'] })
    },
    onError: (e: any) => toast(e?.response?.data?.detail ?? 'Erro ao disparar analise', 'error'),
  })

  const mutAporte = useMutation({
    mutationFn: (valor: number) => executarAnaliseAporte(valor),
    onSuccess: (data: ExecutarResponse) => {
      toast('Analise de aporte disparada! Acompanhe o progresso em tempo real.', 'success')
      notifyDashboard(data.job_id)
      qc.invalidateQueries({ queryKey: ['analises'] })
    },
    onError: (e: any) => toast(e?.response?.data?.detail ?? 'Erro ao disparar analise de aporte', 'error'),
  })

  const scoreColor = (s: number | null) => {
    if (s == null) return '#9ca3af'
    if (s >= 0.7) return '#16a34a'
    if (s >= 0.4) return '#b8860b'
    return '#dc2626'
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold" style={{ color: '#111827' }}>Analises IA</h1>
        <p className="text-sm mt-0.5" style={{ color: '#6b7280' }}>Recomendacoes e analises geradas pelos agentes de IA</p>
      </div>

      {/* Actions */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="p-5" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
          <h3 className="text-sm font-semibold mb-1" style={{ color: '#111827' }}>Analise Completa da Carteira</h3>
          <p className="text-xs mb-4" style={{ color: '#6b7280' }}>O orquestrador analisa todos os ativos, mercado e sugere realocacoes</p>
          <button onClick={() => mutAnalise.mutate()} disabled={mutAnalise.isPending}
            className="flex items-center gap-2 px-4 py-2 text-sm font-semibold transition-all duration-150 disabled:opacity-50"
            style={{ background: '#15803d', color: '#ffffff' }}
            onMouseEnter={e => { if (!mutAnalise.isPending) e.currentTarget.style.background = '#166534' }}
            onMouseLeave={e => (e.currentTarget.style.background = '#15803d')}
          >
            {mutAnalise.isPending ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
            Executar Analise Completa
          </button>
        </div>

        <div className="p-5" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
          <h3 className="text-sm font-semibold mb-1" style={{ color: '#111827' }}>Analise de Aporte</h3>
          <p className="text-xs mb-4" style={{ color: '#6b7280' }}>Receba recomendacao de como alocar um novo aporte</p>
          <div className="flex gap-2">
            <input type="number" min="0" step="100" placeholder="Valor em R$"
              className="flex-1 px-3 py-2 text-sm outline-none"
              style={{ background: '#ffffff', border: '1px solid #cbd5e1', color: '#111827' }}
              value={valorAporte} onChange={e => setValorAporte(e.target.value)} />
            <button onClick={() => mutAporte.mutate(parseFloat(valorAporte) || 0)}
              disabled={mutAporte.isPending || !valorAporte}
              className="flex items-center gap-2 px-4 py-2 text-sm font-semibold transition-all duration-150 disabled:opacity-50"
              style={{ background: '#f0fdf4', color: '#15803d', border: '1px solid #15803d' }}>
              {mutAporte.isPending ? <Loader2 size={14} className="animate-spin" /> : <BrainCircuit size={14} />}
              Analisar
            </button>
          </div>
        </div>
      </div>

      {/* List */}
      <div className="space-y-2">
        <h3 className="text-sm font-semibold" style={{ color: '#111827' }}>Historico de Analises</h3>
        {isLoading && (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => <SkeletonCard key={i} lines={2} />)}
          </div>
        )}
        {analises.map(a => (
          <div key={a.id} className="overflow-hidden" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
            <button className="w-full flex items-center gap-4 px-5 py-4 text-left transition-colors"
              style={{ color: '#111827' }}
              onMouseEnter={e => (e.currentTarget.style.background = '#f8f9fa')}
              onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
              onClick={() => setExpandido(expandido === a.id ? null : a.id)}>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium" style={{ color: '#111827' }}>{a.tipo_analise}</span>
                  <span className="text-xs px-2 py-0.5" style={{ background: '#f1f3f5', color: '#6b7280', border: '1px solid #e2e8f0' }}>{a.agente}</span>
                  {a.score_confianca != null && (
                    <span className="text-xs font-semibold" style={{ color: scoreColor(a.score_confianca) }}>
                      Confianca: {(a.score_confianca * 100).toFixed(0)}%
                    </span>
                  )}
                </div>
                {a.input_resumo && <p className="text-xs mt-1 truncate" style={{ color: '#6b7280' }}>{a.input_resumo}</p>}
              </div>
              <span className="text-xs flex-shrink-0" style={{ color: '#9ca3af' }}>{formatDataHora(a.data)}</span>
              {expandido === a.id ? <ChevronUp size={14} style={{ color: '#9ca3af', flexShrink: 0 }} /> : <ChevronDown size={14} style={{ color: '#9ca3af', flexShrink: 0 }} />}
            </button>
            {expandido === a.id && a.output_completo && (
              <div className="px-5 pb-5 border-t" style={{ borderColor: '#e2e8f0' }}>
                <pre className="mt-4 text-xs whitespace-pre-wrap leading-relaxed overflow-x-auto" style={{ color: '#374151', fontFamily: 'Inter, sans-serif' }}>
                  {a.output_completo}
                </pre>
              </div>
            )}
          </div>
        ))}
        {!isLoading && analises.length === 0 && (
          <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
            <EmptyState
              icon={<BrainCircuit size={24} />}
              titulo="Nenhuma analise realizada ainda"
              descricao="Execute sua primeira analise usando os botoes acima"
            />
          </div>
        )}
      </div>
    </div>
  )
}
