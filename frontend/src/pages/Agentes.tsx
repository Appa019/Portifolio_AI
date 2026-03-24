interface AgentInfo {
  name: string
  cargo: string
  emoji: string
  level: string
  model: string
  reasoning: string
  tom: string
  team: string
}

const AGENTS: AgentInfo[] = [
  // N0
  { name: 'Carlos Mendonça', cargo: 'CIO', emoji: '🏛️', level: 'N0', model: 'gpt-5.2', reasoning: 'xhigh', tom: 'Formal, decisivo. Ex-BTG, fala pouco mas é definitivo.', team: 'CEO' },
  // N1
  { name: 'Marcelo Tavares', cargo: 'Head B3', emoji: '📋', level: 'N1', model: 'gpt-5.1', reasoning: 'high', tom: 'Formal, metódico. 20 anos de bolsa, modera debates.', team: 'B3' },
  { name: 'Luísa Nakamoto', cargo: 'Head Crypto', emoji: '📋', level: 'N1', model: 'gpt-5.1', reasoning: 'high', tom: 'Formal, visionária. Conecta DeFi com TradFi.', team: 'Crypto' },
  { name: 'Fernando Rocha', cargo: 'CRO', emoji: '🛡️', level: 'N1', model: 'gpt-5.1', reasoning: 'high', tom: 'Formal, cético. Advogado do diabo.', team: 'Risk' },
  // N2 B3
  { name: 'Ricardo Moura', cargo: 'Fundamentalista B3', emoji: '🏦', level: 'N2', model: 'gpt-5.1', reasoning: 'medium', tom: 'Informal, professoral. Cita Damodaran, adora múltiplos.', team: 'B3' },
  { name: 'Bruno Kato', cargo: 'Técnico B3', emoji: '📊', level: 'N2', model: 'gpt-4.1', reasoning: '—', tom: 'Informal, direto. Grafista puro, "o preço diz tudo".', team: 'B3' },
  { name: 'Beatriz Almeida', cargo: 'Setorial B3', emoji: '🏭', level: 'N2', model: 'gpt-5.1', reasoning: 'medium', tom: 'Informal, conectora. Liga Selic com setores.', team: 'B3' },
  { name: 'Patrícia Campos', cargo: 'Risk B3', emoji: '⚠️', level: 'N2', model: 'gpt-4.1', reasoning: '—', tom: 'Cautelosa, numérica. Concentração, beta, drawdown.', team: 'B3' },
  { name: 'Diego Lopes', cargo: 'Trade B3', emoji: '🎯', level: 'N2', model: 'gpt-4.1', reasoning: '—', tom: 'Informal, tático. "Divide em 3 lotes".', team: 'B3' },
  // N2 Crypto
  { name: 'Thiago Satoshi', cargo: 'Fundamentalista Crypto', emoji: '🔬', level: 'N2', model: 'gpt-5.1', reasoning: 'medium', tom: 'Informal, entusiasta. Questiona TVL inflado.', team: 'Crypto' },
  { name: 'Juliana Pires', cargo: 'Técnica Crypto', emoji: '📈', level: 'N2', model: 'gpt-4.1', reasoning: '—', tom: 'Informal, pragmática. Opera 24/7, funding rates.', team: 'Crypto' },
  { name: 'Lucas Webb', cargo: 'On-Chain', emoji: '🔗', level: 'N2', model: 'gpt-5.1', reasoning: 'medium', tom: 'Informal, detetive. Rastreia baleias e exchange flows.', team: 'Crypto' },
  { name: 'André Faria', cargo: 'Risk Crypto', emoji: '🚨', level: 'N2', model: 'gpt-4.1', reasoning: '—', tom: 'Cauteloso, alarmista. Smart contract risk.', team: 'Crypto' },
  { name: 'Camila Duarte', cargo: 'Trade Crypto', emoji: '💱', level: 'N2', model: 'gpt-4.1', reasoning: '—', tom: 'Informal, calculista. DCA vs lump sum, gas fees.', team: 'Crypto' },
  // N2 Cross
  { name: 'Helena Bastos', cargo: 'Macro Economist', emoji: '🌍', level: 'N2', model: 'gpt-5.1', reasoning: 'high', tom: 'Formal-informativo. Copom, Focus, IPCA, câmbio.', team: 'Cross' },
  { name: 'Marina Leal', cargo: 'Sentimento', emoji: '📰', level: 'N2', model: 'gpt-4.1', reasoning: '—', tom: 'Informal, antenada. News flow e social sentiment.', team: 'Cross' },
  { name: 'Rafael Tanaka', cargo: 'Compliance', emoji: '⚖️', level: 'N2', model: 'gpt-4.1', reasoning: '—', tom: 'Formal, regulatório. CVM, tributação, marco legal.', team: 'Cross' },
  { name: 'Eduardo Queiroz', cargo: 'Quant', emoji: '🔢', level: 'N2', model: 'gpt-5.1', reasoning: 'medium', tom: 'Técnico, data-driven. Sharpe ratio, correlação.', team: 'Cross' },
]

const LEVEL_COLORS: Record<string, string> = {
  N0: '#b8860b',
  N1: '#15803d',
  N2: '#2563eb',
  N3: '#6b7280',
}

const TEAM_COLORS: Record<string, string> = {
  CEO: '#b8860b',
  B3: '#15803d',
  Crypto: '#2563eb',
  Risk: '#dc2626',
  Cross: '#6b7280',
}

export function Agentes() {
  const teams = ['CEO', 'B3', 'Crypto', 'Risk', 'Cross']

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold" style={{ color: '#111827' }}>Equipe de Agentes</h1>
        <p className="text-sm mt-0.5" style={{ color: '#6b7280' }}>
          20 agentes IA organizados em hierarquia Goldman Sachs — 4 níveis, 2 equipes + staff
        </p>
      </div>

      {/* Level legend */}
      <div className="flex gap-4 flex-wrap">
        {Object.entries(LEVEL_COLORS).map(([level, color]) => (
          <div key={level} className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5" style={{ background: color }} />
            <span className="text-xs font-medium" style={{ color: '#6b7280' }}>{level}</span>
          </div>
        ))}
      </div>

      {/* Teams */}
      {teams.map(team => {
        const teamAgents = AGENTS.filter(a => a.team === team)
        if (teamAgents.length === 0) return null
        return (
          <div key={team}>
            <div className="flex items-center gap-2 mb-3">
              <span className="w-3 h-3" style={{ background: TEAM_COLORS[team] }} />
              <h2 className="text-sm font-semibold uppercase tracking-widest" style={{ color: TEAM_COLORS[team] }}>
                {team === 'Cross' ? 'Cross-Team Staff' : team === 'CEO' ? 'C-Suite' : `Equipe ${team}`}
              </h2>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
              {teamAgents.map(agent => (
                <div key={agent.name} className="p-4" style={{
                  background: '#ffffff',
                  border: '1px solid #e2e8f0',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
                  borderLeft: `3px solid ${LEVEL_COLORS[agent.level]}`,
                }}>
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="text-lg">{agent.emoji}</span>
                      <div>
                        <p className="text-sm font-semibold" style={{ color: '#111827' }}>{agent.name}</p>
                        <p className="text-xs" style={{ color: '#6b7280' }}>{agent.cargo}</p>
                      </div>
                    </div>
                    <span className="px-1.5 py-0.5 text-[10px] font-semibold"
                          style={{ background: `${LEVEL_COLORS[agent.level]}15`, color: LEVEL_COLORS[agent.level] }}>
                      {agent.level}
                    </span>
                  </div>
                  <p className="text-xs italic mb-2" style={{ color: '#9ca3af' }}>"{agent.tom}"</p>
                  <div className="flex gap-3 text-[10px]" style={{ color: '#6b7280' }}>
                    <span className="font-mono">{agent.model}</span>
                    {agent.reasoning !== '—' && (
                      <span>reasoning: <span className="font-medium">{agent.reasoning}</span></span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )
      })}

      {/* N3 note */}
      <div className="p-4" style={{ background: '#f8f9fa', border: '1px solid #e2e8f0' }}>
        <div className="flex items-center gap-2 mb-1">
          <span className="text-lg">🔍</span>
          <p className="text-sm font-semibold" style={{ color: '#111827' }}>Analistas N3 (dinâmicos)</p>
        </div>
        <p className="text-xs" style={{ color: '#6b7280' }}>
          TickerAnalyst e CryptoAnalyst são criados sob demanda — um por ativo analisado
          (ex: ticker_analyst_PETR4, crypto_analyst_bitcoin). Usam gpt-5.1 com reasoning medium.
        </p>
      </div>
    </div>
  )
}
