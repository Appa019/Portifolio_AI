import { useQuery } from '@tanstack/react-query'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line } from 'recharts'
import { getCustos, getCustosResumo, formatBRL, formatDataHora } from '../api/client'
import { DollarSign } from 'lucide-react'
import EmptyState from '../components/ui/EmptyState'
import { SkeletonCard } from '../components/ui/Skeleton'

const TooltipCustom = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null
  return (
    <div className="px-3 py-2 text-xs" style={{ background: '#ffffff', border: '1px solid #e2e8f0', color: '#111827', boxShadow: '0 4px 12px rgba(0,0,0,0.08)' }}>
      <p style={{ color: '#6b7280' }} className="mb-1">{label}</p>
      {payload.map((p: any) => <p key={p.name} style={{ color: p.color }}>{p.name}: {typeof p.value === 'number' && isFinite(p.value) ? p.value.toFixed(4) : '\u2014'}</p>)}
    </div>
  )
}

export default function Custos() {
  const { data: resumo, isLoading: loadingResumo } = useQuery({ queryKey: ['custos-resumo'], queryFn: getCustosResumo })
  const { data: custos = [] } = useQuery({ queryKey: ['custos'], queryFn: getCustos })

  const porAgente = resumo?.por_agente.map(a => ({ agente: a.agente, total: a.total_usd })) ?? []
  const porMes = resumo?.por_mes ?? []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold" style={{ color: '#111827' }}>Custos de IA</h1>
        <p className="text-sm mt-0.5" style={{ color: '#6b7280' }}>Monitoramento de gastos com modelos OpenAI</p>
      </div>

      {/* Summary cards */}
      {loadingResumo ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} lines={2} />)}
        </div>
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { t: 'Total USD', v: resumo ? `$ ${resumo.total_usd.toFixed(4)}` : '\u2014' },
            { t: 'Total BRL', v: resumo ? formatBRL(resumo.total_brl) : '\u2014' },
            { t: 'Media por Analise', v: resumo ? formatBRL(resumo.media_por_analise_brl) : '\u2014' },
            { t: 'Cotacao Dolar', v: resumo ? formatBRL(resumo.cotacao_dolar_atual) : '\u2014' },
          ].map(c => (
            <div key={c.t} className="p-5" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
              <p className="text-xs font-medium uppercase tracking-widest mb-3" style={{ color: '#6b7280' }}>{c.t}</p>
              <p className="text-xl font-semibold" style={{ color: '#111827' }}>{c.v}</p>
            </div>
          ))}
        </div>
      )}

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="p-5" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
          <h3 className="text-sm font-semibold mb-4" style={{ color: '#111827' }}>Custo por Agente (USD)</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={porAgente}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
              <XAxis dataKey="agente" tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false} tickFormatter={v => typeof v === 'number' && !isNaN(v) ? `$${v.toFixed(3)}` : '$0'} />
              <Tooltip content={<TooltipCustom />} />
              <Bar dataKey="total" fill="#15803d" radius={[0, 0, 0, 0]} name="USD" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="p-5" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
          <h3 className="text-sm font-semibold mb-4" style={{ color: '#111827' }}>Tendencia Mensal (BRL)</h3>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={porMes}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
              <XAxis dataKey="mes" tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false} tickFormatter={v => typeof v === 'number' && !isNaN(v) ? `R$${v.toFixed(2)}` : 'R$0'} />
              <Tooltip content={<TooltipCustom />} />
              <Line type="monotone" dataKey="total_brl" stroke="#2563eb" strokeWidth={2} dot={false} name="BRL" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-hidden" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
        <div className="px-5 py-4 border-b" style={{ borderColor: '#e2e8f0' }}>
          <h3 className="text-sm font-semibold" style={{ color: '#111827' }}>Registro Detalhado</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ background: '#f8f9fa' }}>
                {['Data', 'Agente', 'Modelo', 'Tokens In', 'Tokens Out', 'Custo USD', 'Custo BRL', 'Cotacao'].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider" style={{ color: '#6b7280' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {custos.map((c, i) => (
                <tr key={c.id} style={{ borderBottom: '1px solid #e2e8f0', background: i % 2 !== 0 ? '#f8f9fa' : '#ffffff' }}>
                  <td className="px-4 py-3 text-xs" style={{ color: '#6b7280' }}>{formatDataHora(c.data)}</td>
                  <td className="px-4 py-3 text-xs font-medium" style={{ color: '#15803d' }}>{c.agente}</td>
                  <td className="px-4 py-3 text-xs font-mono" style={{ color: '#6b7280' }}>{c.modelo}</td>
                  <td className="px-4 py-3 text-xs" style={{ color: '#111827' }}>{c.tokens_input.toLocaleString('pt-BR')}</td>
                  <td className="px-4 py-3 text-xs" style={{ color: '#111827' }}>{c.tokens_output.toLocaleString('pt-BR')}</td>
                  <td className="px-4 py-3 text-xs font-medium" style={{ color: '#111827' }}>$ {c.custo_usd.toFixed(6)}</td>
                  <td className="px-4 py-3 text-xs font-medium" style={{ color: '#16a34a' }}>{formatBRL(c.custo_brl)}</td>
                  <td className="px-4 py-3 text-xs" style={{ color: '#6b7280' }}>{formatBRL(c.cotacao_dolar)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {custos.length === 0 && (
            <EmptyState
              icon={<DollarSign size={24} />}
              titulo="Nenhum registro de custo ainda"
              descricao="Custos serao registrados quando analises forem executadas"
            />
          )}
        </div>
      </div>
    </div>
  )
}
