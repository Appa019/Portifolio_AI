import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { PlusCircle, Search, ArrowLeftRight } from 'lucide-react'
import { getTransacoes, criarTransacao, searchTickers, formatBRL, formatData } from '../api/client'
import type { NovaTransacao } from '../api/client'
import { useToast } from '../components/ui/Toast'
import EmptyState from '../components/ui/EmptyState'

const campoBase = 'w-full px-3 py-2.5 text-sm outline-none transition-all duration-150'
const campoStyle = { background: '#ffffff', border: '1px solid #cbd5e1', color: '#111827' }

export default function Transacoes() {
  const qc = useQueryClient()
  const { toast } = useToast()
  const [filtroTipo, setFiltroTipo] = useState('')
  const [filtroTicker, setFiltroTicker] = useState('')
  const [form, setForm] = useState<NovaTransacao>({ ticker: '', tipo_operacao: 'compra', quantidade: 0, preco_unitario: 0, data_operacao: new Date().toISOString().split('T')[0] })
  const [busca, setBusca] = useState('')
  const [sugestoes, setSugestoes] = useState<Array<{ ticker: string; nome: string; origem: string }>>([])
  const [mostrarSugestoes, setMostrarSugestoes] = useState(false)
  const [erro, setErro] = useState('')
  const timerRef = useRef<ReturnType<typeof setTimeout>>()

  const { data: transacoes = [] } = useQuery({
    queryKey: ['transacoes', filtroTipo, filtroTicker],
    queryFn: () => getTransacoes({ tipo: filtroTipo || undefined, ticker: filtroTicker || undefined }),
  })

  const mutacao = useMutation({
    mutationFn: criarTransacao,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['transacoes'] })
      qc.invalidateQueries({ queryKey: ['portfolio-ativos'] })
      qc.invalidateQueries({ queryKey: ['portfolio-resumo'] })
      toast('Transacao registrada com sucesso!', 'success')
      setErro('')
      setForm({ ticker: '', tipo_operacao: 'compra', quantidade: 0, preco_unitario: 0, data_operacao: new Date().toISOString().split('T')[0] })
      setBusca('')
    },
    onError: (e: any) => {
      const msg = e?.response?.data?.detail ?? 'Erro ao registrar transacao'
      setErro(msg)
      toast(msg, 'error')
    },
  })

  useEffect(() => {
    if (busca.length < 2) { setSugestoes([]); return }
    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(async () => {
      try { const r = await searchTickers(busca); setSugestoes(r) } catch (err) { console.warn('Ticker search failed:', err); setSugestoes([]) }
    }, 300)
    return () => clearTimeout(timerRef.current)
  }, [busca])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setErro('')
    if (!form.ticker) return setErro('Informe o ticker')
    if (form.quantidade <= 0) return setErro('Quantidade deve ser maior que zero')
    if (form.preco_unitario <= 0) return setErro('Preco deve ser maior que zero')
    mutacao.mutate(form)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold" style={{ color: '#111827' }}>Transacoes</h1>
        <p className="text-sm mt-0.5" style={{ color: '#6b7280' }}>Registre compras e vendas de ativos</p>
      </div>

      {/* Form */}
      <div className="p-6" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
        <h2 className="text-sm font-semibold mb-5 flex items-center gap-2" style={{ color: '#111827' }}>
          <PlusCircle size={15} style={{ color: '#15803d' }} /> Nova Transacao
        </h2>
        <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: '#6b7280' }}>Operacao</label>
            <select className={campoBase} style={campoStyle} value={form.tipo_operacao}
              onChange={e => setForm(f => ({ ...f, tipo_operacao: e.target.value as 'compra' | 'venda' }))}>
              <option value="compra">Compra</option>
              <option value="venda">Venda</option>
            </select>
          </div>

          <div className="relative">
            <label className="block text-xs font-medium mb-1.5" style={{ color: '#6b7280' }}>Ticker</label>
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: '#9ca3af' }} />
              <input
                className={campoBase} style={{ ...campoStyle, paddingLeft: '2rem' }}
                placeholder="Ex: PETR4, bitcoin..."
                value={busca}
                onChange={e => { setBusca(e.target.value); setForm(f => ({ ...f, ticker: e.target.value.trim().toUpperCase() })); setMostrarSugestoes(true) }}
                onBlur={() => setTimeout(() => setMostrarSugestoes(false), 200)}
              />
            </div>
            {mostrarSugestoes && sugestoes.length > 0 && (
              <div className="absolute z-10 w-full mt-1 overflow-hidden" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 4px 12px rgba(0,0,0,0.08)' }}>
                {sugestoes.map(s => (
                  <button key={s.ticker} type="button" className="w-full text-left px-3 py-2 text-xs transition-colors"
                    style={{ color: '#111827' }}
                    onMouseEnter={e => (e.currentTarget.style.background = '#f0fdf4')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                    onClick={() => { setBusca(s.ticker); setForm(f => ({ ...f, ticker: s.ticker })); setMostrarSugestoes(false) }}>
                    <span className="font-mono font-semibold" style={{ color: '#15803d' }}>{s.ticker}</span>
                    <span className="ml-2" style={{ color: '#6b7280' }}>{s.nome}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: '#6b7280' }}>Quantidade</label>
            <input type="number" min="0" step="0.00000001" className={campoBase} style={campoStyle}
              placeholder="0" value={form.quantidade || ''}
              onChange={e => setForm(f => ({ ...f, quantidade: parseFloat(e.target.value) || 0 }))} />
          </div>

          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: '#6b7280' }}>Preco Unitario (R$)</label>
            <input type="number" min="0" step="0.01" className={campoBase} style={campoStyle}
              placeholder="0,00" value={form.preco_unitario || ''}
              onChange={e => setForm(f => ({ ...f, preco_unitario: parseFloat(e.target.value) || 0 }))} />
          </div>

          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: '#6b7280' }}>Data da Operacao</label>
            <input type="date" className={campoBase} style={campoStyle} value={form.data_operacao}
              onChange={e => setForm(f => ({ ...f, data_operacao: e.target.value }))} />
          </div>

          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: '#6b7280' }}>Observacao (opcional)</label>
            <input type="text" className={campoBase} style={campoStyle} placeholder="Notas..."
              value={form.observacao ?? ''}
              onChange={e => setForm(f => ({ ...f, observacao: e.target.value || undefined }))} />
          </div>

          {form.quantidade > 0 && form.preco_unitario > 0 && (
            <div className="md:col-span-2 lg:col-span-3 flex items-center gap-2 text-sm">
              <span style={{ color: '#6b7280' }}>Valor total estimado:</span>
              <span className="font-semibold" style={{ color: '#15803d' }}>{formatBRL(form.quantidade * form.preco_unitario)}</span>
            </div>
          )}

          {erro && <p className="md:col-span-2 lg:col-span-3 text-xs" style={{ color: '#dc2626' }}>{erro}</p>}

          <div className="md:col-span-2 lg:col-span-3">
            <button type="submit" disabled={mutacao.isPending}
              className="px-5 py-2.5 text-sm font-semibold transition-all duration-150 disabled:opacity-50"
              style={{ background: '#15803d', color: '#ffffff' }}
              onMouseEnter={e => { if (!mutacao.isPending) e.currentTarget.style.background = '#166534' }}
              onMouseLeave={e => (e.currentTarget.style.background = '#15803d')}
            >
              {mutacao.isPending ? 'Registrando...' : 'Registrar Transacao'}
            </button>
          </div>
        </form>
      </div>

      {/* Filters + History */}
      <div className="overflow-hidden" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
        <div className="px-5 py-4 flex items-center gap-3 border-b" style={{ borderColor: '#e2e8f0' }}>
          <h3 className="text-sm font-semibold flex-1" style={{ color: '#111827' }}>Historico</h3>
          <select className="text-xs px-3 py-1.5 outline-none" style={{ background: '#ffffff', border: '1px solid #cbd5e1', color: '#6b7280' }}
            value={filtroTipo} onChange={e => setFiltroTipo(e.target.value)}>
            <option value="">Todos os tipos</option>
            <option value="compra">Compra</option>
            <option value="venda">Venda</option>
          </select>
          <input type="text" placeholder="Filtrar ticker..." className="text-xs px-3 py-1.5 outline-none w-28"
            style={{ background: '#ffffff', border: '1px solid #cbd5e1', color: '#111827' }}
            value={filtroTicker} onChange={e => setFiltroTicker(e.target.value.toUpperCase())} />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ background: '#f8f9fa' }}>
                {['Data', 'Ticker', 'Tipo', 'Quantidade', 'Preco Unit.', 'Total', 'Obs.'].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider" style={{ color: '#6b7280' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {transacoes.map((t, i) => (
                <tr key={t.id} style={{ borderBottom: '1px solid #e2e8f0', background: i % 2 !== 0 ? '#f8f9fa' : '#ffffff' }}>
                  <td className="px-4 py-3 text-xs" style={{ color: '#6b7280' }}>{formatData(t.data_operacao)}</td>
                  <td className="px-4 py-3 font-mono font-semibold text-xs" style={{ color: '#15803d' }}>{t.ticker}</td>
                  <td className="px-4 py-3">
                    <span className="text-xs px-2 py-0.5 font-medium"
                      style={{ background: t.tipo_operacao === 'compra' ? '#dcfce7' : '#fef2f2', color: t.tipo_operacao === 'compra' ? '#16a34a' : '#dc2626' }}>
                      {t.tipo_operacao === 'compra' ? 'Compra' : 'Venda'}
                    </span>
                  </td>
                  <td className="px-4 py-3" style={{ color: '#111827' }}>{t.quantidade.toLocaleString('pt-BR')}</td>
                  <td className="px-4 py-3" style={{ color: '#111827' }}>{formatBRL(t.preco_unitario)}</td>
                  <td className="px-4 py-3 font-medium" style={{ color: '#111827' }}>{formatBRL(t.quantidade * t.preco_unitario)}</td>
                  <td className="px-4 py-3 text-xs" style={{ color: '#9ca3af' }}>{t.observacao ?? '\u2014'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {transacoes.length === 0 && (
            <EmptyState
              icon={<ArrowLeftRight size={24} />}
              titulo="Nenhuma transacao registrada"
              descricao="Registre sua primeira compra ou venda acima"
            />
          )}
        </div>
      </div>
    </div>
  )
}
