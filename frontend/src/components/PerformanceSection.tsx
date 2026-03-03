import type { Ativo, PortfolioResumo } from '../api/client'
import { formatBRL } from '../api/client'

interface Props {
  ativos: Ativo[]
  resumo: PortfolioResumo | undefined
}

interface CategoriaData {
  label: string
  pnlBrl: number
  pnlPct: number
  investido: number
  atual: number
}

function calcCategoria(ativos: Ativo[], tipo: string): CategoriaData {
  const filtered = ativos.filter(a => a.tipo === tipo)
  const pnlBrl = filtered.reduce((acc, a) => acc + a.pnl_brl, 0)
  const atual = filtered.reduce((acc, a) => acc + a.valor_total, 0)
  const investido = atual - pnlBrl
  const pnlPct = investido > 0 ? (pnlBrl / investido) * 100 : 0
  const labels: Record<string, string> = { acao: 'Acoes B3', crypto: 'Crypto', cdb: 'CDB' }
  return { label: labels[tipo] ?? tipo, pnlBrl, pnlPct, investido, atual }
}

function CategoryCard({ data, active }: { data: CategoriaData; active?: boolean }) {
  const isPositive = data.pnlBrl >= 0
  return (
    <div
      className="p-4 flex flex-col gap-1 transition-all"
      style={{
        background: active ? '#f0fdf4' : '#ffffff',
        border: `1px solid ${active ? '#15803d' : '#e2e8f0'}`,
        boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
      }}
    >
      <p className="text-xs font-medium uppercase tracking-wider" style={{ color: '#6b7280' }}>
        {data.label}
      </p>
      <p
        className="text-lg font-semibold"
        style={{ color: isPositive ? '#16a34a' : '#dc2626' }}
      >
        {isPositive ? '+' : ''}{data.pnlPct.toFixed(1)}%
      </p>
      <p className="text-xs" style={{ color: isPositive ? '#16a34a' : '#dc2626' }}>
        {isPositive ? '+' : ''}{formatBRL(data.pnlBrl)}
      </p>
      <p className="text-xs mt-1" style={{ color: '#9ca3af' }}>
        Investido: {formatBRL(data.investido)}
      </p>
    </div>
  )
}

export default function PerformanceSection({ ativos, resumo }: Props) {
  if (!resumo || ativos.length === 0) return null

  const totalData: CategoriaData = {
    label: 'Total',
    pnlBrl: resumo.lucro_prejuizo_brl,
    pnlPct: resumo.rentabilidade_pct,
    investido: resumo.valor_investido_brl,
    atual: resumo.valor_total_brl,
  }

  const categorias = ['acao', 'crypto', 'cdb'].map(t => calcCategoria(ativos, t))

  const sortedAtivos = [...ativos].sort((a, b) => Math.abs(b.pnl_brl) - Math.abs(a.pnl_brl))

  const maxAbsPnl = Math.max(...ativos.map(a => Math.abs(a.pnl_pct)), 1)

  return (
    <div
      className="p-5"
      style={{
        background: '#ffffff',
        border: '1px solid #e2e8f0',
        boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
      }}
    >
      <h3 className="text-sm font-semibold mb-4" style={{ color: '#111827' }}>
        Desempenho
      </h3>

      {/* Category cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
        <CategoryCard data={totalData} active />
        {categorias.map(c => (
          <CategoryCard key={c.label} data={c} />
        ))}
      </div>

      {/* Per-asset bars */}
      <div className="space-y-2">
        {sortedAtivos.map(a => {
          const isPositive = a.pnl_pct >= 0
          const barWidth = Math.max((Math.abs(a.pnl_pct) / maxAbsPnl) * 100, 2)
          return (
            <div key={a.ticker} className="flex items-center gap-3 text-sm">
              <span
                className="w-20 font-mono font-semibold text-xs flex-shrink-0"
                style={{ color: '#15803d' }}
              >
                {a.ticker}
              </span>
              <span
                className="w-28 text-xs truncate flex-shrink-0"
                style={{ color: '#6b7280' }}
              >
                {a.nome}
              </span>
              <div className="flex-1 h-5 relative" style={{ background: '#f8f9fa' }}>
                <div
                  className="h-full transition-all duration-300"
                  style={{
                    width: `${barWidth}%`,
                    background: isPositive ? '#16a34a' : '#dc2626',
                    opacity: 0.8,
                  }}
                />
              </div>
              <span
                className="w-16 text-xs font-semibold text-right flex-shrink-0"
                style={{ color: isPositive ? '#16a34a' : '#dc2626' }}
              >
                {isPositive ? '+' : ''}{a.pnl_pct.toFixed(1)}%
              </span>
              <span
                className="w-24 text-xs text-right flex-shrink-0"
                style={{ color: isPositive ? '#16a34a' : '#dc2626' }}
              >
                {isPositive ? '+' : ''}{formatBRL(a.pnl_brl)}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
