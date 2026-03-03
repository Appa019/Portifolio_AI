import type { ReactNode } from 'react'

interface EmptyStateProps {
  icon: ReactNode
  titulo: string
  descricao?: string
  acao?: { label: string; onClick: () => void }
}

export default function EmptyState({ icon, titulo, descricao, acao }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-6">
      <div
        className="w-14 h-14 flex items-center justify-center mb-4"
        style={{ background: '#dcfce7', color: '#15803d' }}
      >
        {icon}
      </div>
      <h3 className="text-sm font-semibold mb-1" style={{ color: '#111827' }}>
        {titulo}
      </h3>
      {descricao && (
        <p className="text-xs text-center max-w-xs" style={{ color: '#6b7280' }}>
          {descricao}
        </p>
      )}
      {acao && (
        <button
          onClick={acao.onClick}
          className="mt-4 px-4 py-2 text-sm font-medium transition-colors"
          style={{ background: '#15803d', color: '#ffffff' }}
          onMouseEnter={e => (e.currentTarget.style.background = '#166534')}
          onMouseLeave={e => (e.currentTarget.style.background = '#15803d')}
        >
          {acao.label}
        </button>
      )}
    </div>
  )
}
