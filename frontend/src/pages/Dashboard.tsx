import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Wallet, TrendingUp, TrendingDown, Package } from 'lucide-react'
import StatsCard from '../components/StatsCard'
import AllocationChart from '../components/AllocationChart'
import EvolutionChart from '../components/EvolutionChart'
import AssetTable from '../components/AssetTable'
import PerformanceSection from '../components/PerformanceSection'
import { SkeletonCard, SkeletonTable } from '../components/ui/Skeleton'
import {
  getPortfolioResumo, getPortfolioAtivos, getPortfolioAlocacao,
  getPortfolioEvolucao, getMacro, formatBRL, formatPct,
} from '../api/client'

export default function Dashboard() {
  const [periodo, setPeriodo] = useState('6m')

  const { data: resumo, isLoading: loadingResumo } = useQuery({ queryKey: ['portfolio-resumo'], queryFn: getPortfolioResumo, refetchInterval: 60_000 })
  const { data: ativos = [], isLoading: loadingAtivos } = useQuery({ queryKey: ['portfolio-ativos'], queryFn: getPortfolioAtivos, refetchInterval: 60_000 })
  const { data: alocacao } = useQuery({ queryKey: ['portfolio-alocacao'], queryFn: getPortfolioAlocacao })
  const { data: evolucao = [], refetch: refetchEvolucao } = useQuery({ queryKey: ['portfolio-evolucao', periodo], queryFn: () => getPortfolioEvolucao(periodo) })
  const { data: macro } = useQuery({ queryKey: ['macro'], queryFn: getMacro, staleTime: 300_000 })

  const handlePeriodo = (p: string) => { setPeriodo(p); refetchEvolucao() }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold" style={{ color: '#111827' }}>Dashboard</h1>
        <p className="text-sm mt-0.5" style={{ color: '#6b7280' }}>Visao geral do portfolio de investimentos</p>
      </div>

      {/* Stats Cards */}
      {loadingResumo ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} lines={2} />)}
        </div>
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatsCard titulo="Valor Total" valor={resumo ? formatBRL(resumo.valor_total_brl) : '\u2014'} icone={<Wallet size={15} />} destaque />
          <StatsCard
            titulo="Rentabilidade"
            valor={resumo ? formatPct(resumo.rentabilidade_pct) : '\u2014'}
            variacao={resumo ? `${Math.abs(resumo.rentabilidade_pct).toFixed(2)}%` : undefined}
            variacaoPositiva={resumo ? resumo.rentabilidade_pct >= 0 : undefined}
            icone={<TrendingUp size={15} />}
          />
          <StatsCard
            titulo="Lucro / Prejuizo"
            valor={resumo ? formatBRL(resumo.lucro_prejuizo_brl) : '\u2014'}
            variacaoPositiva={resumo ? resumo.lucro_prejuizo_brl >= 0 : undefined}
            icone={(resumo?.lucro_prejuizo_brl ?? 0) >= 0 ? <TrendingUp size={15} /> : <TrendingDown size={15} />}
          />
          <StatsCard titulo="Ativos" valor={resumo ? String(resumo.num_ativos) : '\u2014'} icone={<Package size={15} />} sub={`Investido: ${resumo ? formatBRL(resumo.valor_investido_brl) : '\u2014'}`} />
        </div>
      )}

      {/* Charts + Macro */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <EvolutionChart data={evolucao} onPeriodoChange={handlePeriodo} />
        </div>
        <div className="space-y-4">
          <AllocationChart data={alocacao} />
          <div className="p-5 space-y-3" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
            <h3 className="text-sm font-semibold" style={{ color: '#111827' }}>Indicadores Macro</h3>
            {[
              { label: 'Selic', value: typeof macro?.selic === 'number' && isFinite(macro.selic) ? `${macro.selic.toFixed(2)}% a.a.` : '\u2014' },
              { label: 'CDI', value: typeof macro?.cdi === 'number' && isFinite(macro.cdi) ? `${macro.cdi.toFixed(2)}% a.a.` : '\u2014' },
              { label: 'IPCA', value: typeof macro?.ipca === 'number' && isFinite(macro.ipca) ? `${macro.ipca.toFixed(2)}%` : '\u2014' },
              { label: 'PTAX (USD)', value: typeof macro?.ptax === 'number' && isFinite(macro.ptax) ? `R$ ${macro.ptax.toFixed(4)}` : '\u2014' },
            ].map(row => (
              <div key={row.label} className="flex justify-between items-center text-sm">
                <span style={{ color: '#6b7280' }}>{row.label}</span>
                <span className="font-medium" style={{ color: '#111827' }}>{row.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Performance Section */}
      <PerformanceSection ativos={ativos} resumo={resumo} />

      {/* Asset Table */}
      {loadingAtivos ? <SkeletonTable rows={5} cols={6} /> : <AssetTable ativos={ativos} />}
    </div>
  )
}
