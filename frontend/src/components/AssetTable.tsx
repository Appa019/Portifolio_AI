import type { Ativo } from '../api/client'
import { formatBRL } from '../api/client'
import { Package } from 'lucide-react'
import EmptyState from './ui/EmptyState'

interface Props {
  ativos: Ativo[]
}

function LockupBadge({ ativo }: { ativo: Ativo }) {
  if (!ativo.lockup_ativo) {
    return (
      <span
        className="text-xs font-medium px-2 py-0.5"
        style={{ background: '#dcfce7', color: '#16a34a' }}
      >
        Livre
      </span>
    )
  }
  return (
    <span
      className="text-xs font-medium px-2 py-0.5"
      style={{ background: '#fef3c7', color: '#b8860b' }}
    >
      {ativo.dias_lockup_restantes}d bloqueado
    </span>
  )
}

export default function AssetTable({ ativos }: Props) {
  return (
    <div className="overflow-hidden" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
      <div className="px-5 py-4 border-b" style={{ borderColor: '#e2e8f0' }}>
        <h3 className="text-sm font-semibold" style={{ color: '#111827' }}>
          Ativos na Carteira
        </h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr style={{ background: '#f8f9fa' }}>
              {['Ticker', 'Nome', 'Preco Atual', 'P.M.', 'Qtd', 'Valor', 'L/P %', '% Carteira', 'Lock-up'].map(h => (
                <th
                  key={h}
                  className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider"
                  style={{ color: '#6b7280' }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ativos.map((a, i) => (
              <tr
                key={a.ticker}
                className="transition-colors duration-100"
                style={{
                  background: i % 2 === 0 ? '#ffffff' : '#f8f9fa',
                  borderBottom: '1px solid #e2e8f0',
                }}
                onMouseEnter={e => (e.currentTarget.style.background = '#f0fdf4')}
                onMouseLeave={e => (e.currentTarget.style.background = i % 2 === 0 ? '#ffffff' : '#f8f9fa')}
              >
                <td className="px-4 py-3 font-mono font-semibold text-xs" style={{ color: '#15803d' }}>
                  {a.ticker}
                </td>
                <td className="px-4 py-3" style={{ color: '#111827' }}>
                  <span className="truncate block max-w-[140px]">{a.nome}</span>
                </td>
                <td className="px-4 py-3 font-medium" style={{ color: '#111827' }}>
                  {formatBRL(a.preco_atual)}
                </td>
                <td className="px-4 py-3" style={{ color: '#6b7280' }}>
                  {formatBRL(a.preco_medio)}
                </td>
                <td className="px-4 py-3" style={{ color: '#6b7280' }}>
                  {a.quantidade.toLocaleString('pt-BR')}
                </td>
                <td className="px-4 py-3 font-medium" style={{ color: '#111827' }}>
                  {formatBRL(a.valor_total)}
                </td>
                <td className="px-4 py-3">
                  <span
                    className="font-semibold"
                    style={{ color: a.pnl_pct >= 0 ? '#16a34a' : '#dc2626' }}
                  >
                    {a.pnl_pct >= 0 ? '+' : ''}{a.pnl_pct.toFixed(2)}%
                  </span>
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <div
                      className="h-1"
                      style={{
                        width: `${Math.min(a.pct_portfolio, 100)}%`,
                        maxWidth: '60px',
                        minWidth: '4px',
                        background: '#15803d',
                        opacity: 0.6,
                      }}
                    />
                    <span style={{ color: '#6b7280' }}>{a.pct_portfolio.toFixed(1)}%</span>
                  </div>
                </td>
                <td className="px-4 py-3">
                  <LockupBadge ativo={a} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {ativos.length === 0 && (
          <EmptyState
            icon={<Package size={24} />}
            titulo="Nenhum ativo encontrado"
            descricao="Adicione transacoes para ver seus ativos aqui"
          />
        )}
      </div>
    </div>
  )
}
