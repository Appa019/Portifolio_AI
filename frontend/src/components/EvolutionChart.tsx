import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import type { EvolucaoPonto } from '../api/client'
import { formatBRL } from '../api/client'
import { useState } from 'react'

interface Props {
  data: EvolucaoPonto[]
  onPeriodoChange?: (periodo: string) => void
}

const periodos = [
  { label: '1M', value: '1m' },
  { label: '3M', value: '3m' },
  { label: '6M', value: '6m' },
  { label: '1A', value: '1a' },
]

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null
  return (
    <div
      className="px-3 py-2.5 text-xs"
      style={{ background: '#ffffff', border: '1px solid #e2e8f0', color: '#111827', boxShadow: '0 4px 12px rgba(0,0,0,0.08)' }}
    >
      <p style={{ color: '#6b7280' }} className="mb-1">{label}</p>
      <p className="font-semibold">{formatBRL(payload[0].value)}</p>
    </div>
  )
}

export default function EvolutionChart({ data, onPeriodoChange }: Props) {
  const [periodoAtivo, setPeriodoAtivo] = useState('6m')

  const handlePeriodo = (p: string) => {
    setPeriodoAtivo(p)
    onPeriodoChange?.(p)
  }

  const chartData = data.map(p => ({
    data: new Date(p.data).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' }),
    valor: p.valor_total,
  }))

  const valores = data.map(d => d.valor_total)
  const min = valores.length > 0 ? Math.min(...valores) : 0
  const max = valores.length > 0 ? Math.max(...valores) : 0

  return (
    <div className="p-5" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
      <div className="flex items-center justify-between mb-5">
        <h3 className="text-sm font-semibold" style={{ color: '#111827' }}>
          Evolucao do Portfolio
        </h3>
        <div className="flex gap-1">
          {periodos.map(p => (
            <button
              key={p.value}
              onClick={() => handlePeriodo(p.value)}
              className="px-2.5 py-1 text-xs font-medium transition-all duration-150"
              style={{
                background: periodoAtivo === p.value ? '#dcfce7' : 'transparent',
                color: periodoAtivo === p.value ? '#15803d' : '#6b7280',
                border: `1px solid ${periodoAtivo === p.value ? '#15803d' : 'transparent'}`,
              }}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={chartData} margin={{ top: 5, right: 5, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
          <XAxis
            dataKey="data"
            tick={{ fontSize: 11, fill: '#9ca3af' }}
            axisLine={false}
            tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fontSize: 11, fill: '#9ca3af' }}
            axisLine={false}
            tickLine={false}
            tickFormatter={v => `R$${(v / 1000).toFixed(0)}k`}
            domain={valores.length > 0 ? [min * 0.97, max * 1.03] : ['auto', 'auto']}
            width={60}
          />
          <Tooltip content={<CustomTooltip />} />
          <Area
            type="monotone"
            dataKey="valor"
            stroke="#15803d"
            strokeWidth={2}
            fill="rgba(21,128,61,0.08)"
            dot={false}
            activeDot={{ r: 4, fill: '#15803d', stroke: '#ffffff', strokeWidth: 2 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
