import { useState, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Save, Loader2 } from 'lucide-react'
import { getConfiguracoes, salvarConfiguracoes } from '../api/client'
import { useToast } from '../components/ui/Toast'
import { SkeletonCard } from '../components/ui/Skeleton'

export default function Config() {
  const { data: configs = [], isLoading } = useQuery({ queryKey: ['configuracoes'], queryFn: getConfiguracoes })
  const { toast } = useToast()
  const [form, setForm] = useState<Record<string, string>>({})

  useEffect(() => {
    if (configs.length) setForm(Object.fromEntries(configs.map(c => [c.chave, c.valor])))
  }, [configs])

  const mutacao = useMutation({
    mutationFn: salvarConfiguracoes,
    onSuccess: () => toast('Configuracoes salvas com sucesso!', 'success'),
    onError: () => toast('Erro ao salvar configuracoes', 'error'),
  })

  const labels: Record<string, string> = {
    alocacao_acoes: 'Alocacao Acoes B3 (%)',
    alocacao_crypto: 'Alocacao Cripto (%)',
    alocacao_cdb: 'Alocacao CDB (%)',
    lockup_dias: 'Lock-up (dias)',
    email_destinatario: 'E-mail destinatario',
    intervalo_atualizacao_horas: 'Intervalo de atualizacao (horas)',
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold" style={{ color: '#111827' }}>Configuracoes</h1>
        <p className="text-sm mt-0.5" style={{ color: '#6b7280' }}>Parametros do sistema de gestao</p>
      </div>
      <div className="p-6" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
        {isLoading ? (
          <div className="space-y-4 max-w-lg">
            {Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} lines={1} />)}
          </div>
        ) : (
          <div className="space-y-4 max-w-lg">
            {configs.map(c => (
              <div key={c.chave}>
                <label className="block text-xs font-medium mb-1.5" style={{ color: '#6b7280' }}>
                  {labels[c.chave] ?? c.chave}
                </label>
                <input
                  type={c.chave.includes('email') ? 'email' : 'text'}
                  className="w-full px-3 py-2.5 text-sm outline-none transition-all"
                  style={{ background: '#ffffff', border: '1px solid #cbd5e1', color: '#111827' }}
                  value={form[c.chave] ?? ''}
                  onChange={e => setForm(f => ({ ...f, [c.chave]: e.target.value }))}
                />
              </div>
            ))}
            <button onClick={() => mutacao.mutate(form)} disabled={mutacao.isPending}
              className="flex items-center gap-2 px-5 py-2.5 text-sm font-semibold transition-all disabled:opacity-50 mt-2"
              style={{ background: '#15803d', color: '#ffffff' }}
              onMouseEnter={e => { if (!mutacao.isPending) e.currentTarget.style.background = '#166534' }}
              onMouseLeave={e => (e.currentTarget.style.background = '#15803d')}
            >
              {mutacao.isPending ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
              Salvar Configuracoes
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
