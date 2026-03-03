import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Bell, BellOff, CheckCheck, AlertTriangle, Lock, TrendingDown } from 'lucide-react'
import { getAlertas, marcarAlertaLido, formatDataHora } from '../api/client'
import EmptyState from '../components/ui/EmptyState'
import { SkeletonCard } from '../components/ui/Skeleton'

const iconeTipo = (tipo: string) => {
  if (tipo.includes('lock') || tipo.includes('bloqueio')) return <Lock size={14} />
  if (tipo.includes('desvio') || tipo.includes('alocacao')) return <TrendingDown size={14} />
  return <AlertTriangle size={14} />
}

const corTipo = (tipo: string) => {
  if (tipo.includes('lock')) return { bg: '#fef3c7', color: '#b8860b', border: '#b8860b' }
  if (tipo.includes('desvio')) return { bg: '#fef2f2', color: '#dc2626', border: '#dc2626' }
  return { bg: '#dbeafe', color: '#2563eb', border: '#2563eb' }
}

export default function Alertas() {
  const qc = useQueryClient()
  const { data: naoLidos = [] } = useQuery({ queryKey: ['alertas-nao-lidos'], queryFn: () => getAlertas(false), refetchInterval: 60_000 })
  const { data: todos = [], isLoading } = useQuery({ queryKey: ['alertas-todos'], queryFn: () => getAlertas() })

  const mutLido = useMutation({
    mutationFn: marcarAlertaLido,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['alertas-nao-lidos'] }); qc.invalidateQueries({ queryKey: ['alertas-todos'] }) },
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold flex items-center gap-2" style={{ color: '#111827' }}>
            Alertas
            {naoLidos.length > 0 && (
              <span className="text-xs font-semibold px-2 py-0.5" style={{ background: '#dc2626', color: '#fff' }}>
                {naoLidos.length}
              </span>
            )}
          </h1>
          <p className="text-sm mt-0.5" style={{ color: '#6b7280' }}>Notificacoes sobre lock-up, alocacao e realocacoes</p>
        </div>
      </div>

      {/* Unread */}
      {naoLidos.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-widest mb-3" style={{ color: '#dc2626' }}>
            Nao lidos ({naoLidos.length})
          </h3>
          <div className="space-y-2">
            {naoLidos.map(a => {
              const cor = corTipo(a.tipo)
              return (
                <div key={a.id} className="px-5 py-4 flex items-start gap-4"
                  style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderLeft: `3px solid ${cor.border}`, boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
                  <span className="mt-0.5 flex-shrink-0 p-2" style={{ background: cor.bg, color: cor.color }}>{iconeTipo(a.tipo)}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: cor.color }}>{a.tipo}</span>
                    </div>
                    <p className="text-sm" style={{ color: '#111827' }}>{a.mensagem}</p>
                    <p className="text-xs mt-1" style={{ color: '#9ca3af' }}>{formatDataHora(a.data_criacao)}</p>
                  </div>
                  <button onClick={() => mutLido.mutate(a.id)} disabled={mutLido.isPending}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-all duration-150 flex-shrink-0 disabled:opacity-50"
                    style={{ background: '#dcfce7', color: '#16a34a', border: '1px solid #16a34a' }}>
                    <CheckCheck size={12} /> Marcar lido
                  </button>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* All */}
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-widest mb-3" style={{ color: '#6b7280' }}>Todos os alertas</h3>
        {isLoading && (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => <SkeletonCard key={i} lines={2} />)}
          </div>
        )}
        <div className="space-y-2">
          {todos.map(a => {
            const cor = corTipo(a.tipo)
            return (
              <div key={a.id} className="px-5 py-4 flex items-start gap-4 transition-opacity"
                style={{ background: '#ffffff', border: '1px solid #e2e8f0', opacity: a.lido ? 0.5 : 1, boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
                <span className="mt-0.5 flex-shrink-0 p-2" style={{ background: a.lido ? '#f1f3f5' : cor.bg, color: a.lido ? '#9ca3af' : cor.color }}>
                  {a.lido ? <BellOff size={14} /> : <Bell size={14} />}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: a.lido ? '#9ca3af' : cor.color }}>{a.tipo}</span>
                    {a.lido && <span className="text-xs" style={{ color: '#9ca3af' }}>· Lido</span>}
                  </div>
                  <p className="text-sm" style={{ color: a.lido ? '#6b7280' : '#111827' }}>{a.mensagem}</p>
                  <p className="text-xs mt-1" style={{ color: '#9ca3af' }}>{formatDataHora(a.data_criacao)}</p>
                </div>
                {!a.lido && (
                  <button onClick={() => mutLido.mutate(a.id)} disabled={mutLido.isPending}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-all duration-150 flex-shrink-0 disabled:opacity-50"
                    style={{ background: '#dcfce7', color: '#16a34a', border: '1px solid #16a34a' }}>
                    <CheckCheck size={12} /> Marcar lido
                  </button>
                )}
              </div>
            )
          })}
          {!isLoading && todos.length === 0 && (
            <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
              <EmptyState
                icon={<Bell size={24} />}
                titulo="Nenhum alerta registrado"
                descricao="Alertas de lock-up e desvio de alocacao aparecerão aqui"
              />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
