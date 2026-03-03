import { NavLink } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  LayoutDashboard,
  ArrowLeftRight,
  BrainCircuit,
  DollarSign,
  Bell,
  Settings,
  TrendingUp,
} from 'lucide-react'
import { getAlertas } from '../api/client'

const links = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/transacoes', label: 'Transacoes', icon: ArrowLeftRight },
  { to: '/analises', label: 'Analises IA', icon: BrainCircuit },
  { to: '/alertas', label: 'Alertas', icon: Bell },
  { to: '/custos', label: 'Custos IA', icon: DollarSign },
  { to: '/config', label: 'Configuracoes', icon: Settings },
]

export default function Sidebar() {
  const { data: alertas } = useQuery({
    queryKey: ['alertas-nao-lidos'],
    queryFn: () => getAlertas(false),
    refetchInterval: 60_000,
  })

  const numNaoLidos = alertas?.length ?? 0

  return (
    <aside
      className="fixed left-0 top-0 h-full w-56 flex flex-col z-20"
      style={{
        background: '#0f172a',
        boxShadow: '2px 0 8px rgba(0,0,0,0.1)',
      }}
    >
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-5 py-5 border-b" style={{ borderColor: 'rgba(255,255,255,0.08)' }}>
        <div
          className="w-8 h-8 flex items-center justify-center flex-shrink-0"
          style={{ background: 'rgba(21,128,61,0.15)' }}
        >
          <TrendingUp size={16} style={{ color: '#15803d' }} />
        </div>
        <div>
          <p className="text-sm font-semibold leading-none" style={{ color: '#ffffff' }}>
            Portfolio
          </p>
          <p className="text-xs mt-0.5" style={{ color: '#94a3b8' }}>
            Investimentos
          </p>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {links.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 text-sm font-medium transition-all duration-150 relative group ${
                isActive ? 'text-white' : ''
              }`
            }
            style={({ isActive }) => ({
              background: isActive ? 'rgba(21,128,61,0.15)' : 'transparent',
              color: isActive ? '#ffffff' : '#94a3b8',
            })}
            onMouseEnter={e => {
              const el = e.currentTarget
              if (!el.classList.contains('active')) {
                el.style.color = '#e2e8f0'
              }
            }}
            onMouseLeave={e => {
              const el = e.currentTarget
              const isActive = el.getAttribute('aria-current') === 'page'
              if (!isActive) {
                el.style.color = '#94a3b8'
              }
            }}
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <span
                    className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5"
                    style={{ background: '#15803d' }}
                  />
                )}
                <Icon size={16} style={{ color: isActive ? '#4ade80' : 'inherit', flexShrink: 0 }} />
                <span className="flex-1">{label}</span>
                {label === 'Alertas' && numNaoLidos > 0 && (
                  <span
                    className="text-xs font-semibold px-1.5 py-0.5"
                    style={{ background: '#dc2626', color: '#fff', fontSize: '10px' }}
                  >
                    {numNaoLidos}
                  </span>
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-5 py-4 border-t" style={{ borderColor: 'rgba(255,255,255,0.08)' }}>
        <p className="text-xs" style={{ color: '#475569' }}>
          Sistema local — localhost
        </p>
        <p className="text-xs mt-0.5" style={{ color: '#475569' }}>
          Dados em tempo real
        </p>
      </div>
    </aside>
  )
}
