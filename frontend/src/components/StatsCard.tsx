import type { ReactNode } from 'react'

interface StatsCardProps {
  titulo: string
  valor: string
  variacao?: string
  variacaoPositiva?: boolean
  icone?: ReactNode
  destaque?: boolean
  sub?: string
}

export default function StatsCard({
  titulo,
  valor,
  variacao,
  variacaoPositiva,
  icone,
  destaque,
  sub,
}: StatsCardProps) {
  return (
    <div
      className="p-5 flex flex-col gap-3 transition-all duration-200"
      style={{
        background: destaque ? '#f0fdf4' : '#ffffff',
        border: `1px solid #e2e8f0`,
        borderLeft: destaque ? '3px solid #15803d' : '1px solid #e2e8f0',
        boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
      }}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-medium uppercase tracking-widest" style={{ color: '#6b7280' }}>
          {titulo}
        </p>
        {icone && (
          <span style={{ color: destaque ? '#15803d' : '#9ca3af' }}>
            {icone}
          </span>
        )}
      </div>

      <div>
        <p
          className="text-2xl font-semibold leading-none tracking-tight"
          style={{ color: destaque ? '#15803d' : '#111827' }}
        >
          {valor}
        </p>
        {sub && (
          <p className="text-xs mt-1.5" style={{ color: '#6b7280' }}>
            {sub}
          </p>
        )}
      </div>

      {variacao !== undefined && (
        <div
          className="flex items-center gap-1.5 text-xs font-medium px-2 py-1 w-fit"
          style={{
            background: variacaoPositiva ? '#dcfce7' : '#fef2f2',
            color: variacaoPositiva ? '#16a34a' : '#dc2626',
          }}
        >
          <span>{variacaoPositiva ? '\u25B2' : '\u25BC'}</span>
          <span>{variacao}</span>
        </div>
      )}
    </div>
  )
}
