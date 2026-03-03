import { useState, useEffect, useCallback } from 'react'
import { Outlet } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import Sidebar from './Sidebar'
import AnalysisLiveWidget from './AnalysisLiveWidget'

export default function Layout() {
  const qc = useQueryClient()
  const [jobId, setJobId] = useState<string | null>(null)

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<string>).detail
      setJobId(detail)
    }
    window.addEventListener('analysis-started', handler)
    return () => window.removeEventListener('analysis-started', handler)
  }, [])

  const handleDone = useCallback(() => {
    setJobId(null)
    qc.invalidateQueries({ queryKey: ['analises'] })
    qc.invalidateQueries({ queryKey: ['portfolio-resumo'] })
    qc.invalidateQueries({ queryKey: ['portfolio-ativos'] })
    qc.invalidateQueries({ queryKey: ['portfolio-alocacao'] })
  }, [qc])

  return (
    <div className="flex min-h-screen" style={{ background: '#f8f9fa' }}>
      <Sidebar />
      <main className="flex-1 ml-56 min-h-screen">
        <div className="max-w-7xl mx-auto px-6 py-8">
          <AnalysisLiveWidget jobId={jobId} onDone={handleDone} />
          <Outlet />
        </div>
      </main>
    </div>
  )
}
