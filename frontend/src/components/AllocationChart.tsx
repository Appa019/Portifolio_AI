import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import type { PortfolioAlocacao } from '../api/client'

interface Props {
  data: PortfolioAlocacao | undefined
}

const CATEGORIAS = [
  { key: 'acoes', label: 'Acoes', cor: '#15803d' },
  { key: 'crypto', label: 'Crypto', cor: '#2563eb' },
  { key: 'cdb', label: 'CDB', cor: '#b8860b' },
] as const

type CategoriaKey = typeof CATEGORIAS[number]['key']

interface ChartItem {
  categoria: string
  cor: string
  percentual_atual: number
  percentual_alvo: number
  desvio: number
  name: string
  value: number
}

const CustomTooltip = ({ active, payload }: any) => {
  if (!active || !payload?.length) return null
  const item = payload[0].payload as ChartItem
  return (
    <div
      className="px-3 py-2.5 text-xs"
      style={{ background: '#ffffff', border: '1px solid #e2e8f0', color: '#111827', boxShadow: '0 4px 12px rgba(0,0,0,0.08)' }}
    >
      <p className="font-semibold capitalize mb-1">{item.categoria}</p>
      <p style={{ color: '#6b7280' }}>
        {item.percentual_atual.toFixed(1)}% (alvo {item.percentual_alvo.toFixed(1)}%)
      </p>
      <p style={{ color: item.desvio > 0 ? '#16a34a' : '#dc2626' }}>
        Desvio: {item.desvio > 0 ? '+' : ''}{item.desvio.toFixed(1)}%
      </p>
    </div>
  )
}

export default function AllocationChart({ data }: Props) {
  if (!data) return null

  const chartData: ChartItem[] = CATEGORIAS.map(cat => {
    const k = cat.key as CategoriaKey
    return {
      categoria: cat.label,
      cor: cat.cor,
      percentual_atual: data.atual[k] ?? 0,
      percentual_alvo: data.alvo[k] ?? 0,
      desvio: data.desvio[k] ?? 0,
      name: cat.label,
      value: data.atual[k] ?? 0,
    }
  }).filter(item => item.value > 0)

  if (!chartData.length) return null

  return (
    <div className="p-5" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
      <h3 className="text-sm font-semibold mb-4" style={{ color: '#111827' }}>
        Alocacao Atual
      </h3>
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Pie
            data={chartData}
            cx="50%"
            cy="50%"
            innerRadius={60}
            outerRadius={90}
            paddingAngle={3}
            dataKey="value"
          >
            {chartData.map((entry, index) => (
              <Cell key={index} fill={entry.cor} stroke="transparent" />
            ))}
          </Pie>
          <Tooltip content={<CustomTooltip />} />
          <Legend
            formatter={(value) => (
              <span style={{ color: '#6b7280', fontSize: '12px' }}>{value}</span>
            )}
          />
        </PieChart>
      </ResponsiveContainer>

      {/* Desvios vs alvo */}
      <div className="mt-3 space-y-2">
        {CATEGORIAS.map(cat => {
          const k = cat.key as CategoriaKey
          const pctAtual = data.atual[k] ?? 0
          const pctAlvo = data.alvo[k] ?? 0
          const desvio = data.desvio[k] ?? 0
          return (
            <div key={cat.key} className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <span
                  className="w-2 h-2 flex-shrink-0"
                  style={{ background: cat.cor }}
                />
                <span style={{ color: '#6b7280' }}>
                  {cat.label}
                </span>
              </div>
              <div className="flex items-center gap-3">
                <span style={{ color: '#111827' }}>{pctAtual.toFixed(1)}%</span>
                <span
                  className="font-medium"
                  style={{ color: desvio > 2 ? '#16a34a' : desvio < -2 ? '#dc2626' : '#6b7280' }}
                >
                  {desvio > 0 ? '+' : ''}{desvio.toFixed(1)}% vs {pctAlvo.toFixed(1)}%
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
