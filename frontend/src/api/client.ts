import axios from 'axios'

export const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

// --- Tipos (alinhados com api_schemas.py) ---

export interface AlocacaoAtual {
  acoes: number
  crypto: number
  cdb: number
}

export interface AlocacaoAlvo {
  acoes: number
  crypto: number
  cdb: number
}

export interface PortfolioResumo {
  valor_total_brl: number
  valor_investido_brl: number
  rentabilidade_pct: number
  lucro_prejuizo_brl: number
  num_ativos: number
  alocacao: AlocacaoAtual
}

export interface Ativo {
  id: number
  ticker: string
  nome: string
  tipo: string
  setor: string | null
  preco_atual: number
  preco_medio: number
  quantidade: number
  valor_total: number
  pnl_brl: number
  pnl_pct: number
  pct_portfolio: number
  dias_lockup_restantes: number
  lockup_ativo: boolean
}

export interface PortfolioAlocacao {
  atual: AlocacaoAtual
  alvo: AlocacaoAlvo
  desvio: AlocacaoAtual
}

export interface EvolucaoPonto {
  data: string
  valor_total: number
}

export interface Transacao {
  id: number
  ativo_id: number
  ticker: string
  nome_ativo: string
  tipo_operacao: 'compra' | 'venda'
  quantidade: number
  preco_unitario: number
  data_operacao: string
  lock_up_ate: string | null
  observacao: string | null
  criado_em: string
}

export interface NovaTransacao {
  ticker: string
  tipo_operacao: 'compra' | 'venda'
  quantidade: number
  preco_unitario: number
  data_operacao: string
  observacao?: string
}

export interface Analise {
  id: number
  tipo_analise: string
  agente: string
  score_confianca: number | null
  data: string
  input_resumo: string
  acao_recomendada: string | null
  executada: boolean
  output_completo?: string
}

export interface Alerta {
  id: number
  tipo: string
  mensagem: string
  dados_json: string | null
  data_criacao: string
  lido: boolean
}

export interface CustoToken {
  id: number
  data: string
  agente: string
  modelo: string
  tokens_input: number
  tokens_output: number
  custo_usd: number
  custo_brl: number
  cotacao_dolar: number
  descricao: string | null
}

export interface CustoAgente {
  agente: string
  total_brl: number
  total_usd: number
}

export interface CustoMes {
  mes: string
  total_brl: number
}

export interface CustoResumo {
  total_usd: number
  total_brl: number
  media_por_analise_brl: number
  cotacao_dolar_atual: number
  por_agente: CustoAgente[]
  por_mes: CustoMes[]
}

export interface MacroData {
  selic: number | null
  cdi: number | null
  ipca_acumulado_12m: number | null
  ptax: number | null
}

export interface Configuracao {
  chave: string
  valor: string
  atualizado_em: string
}

export interface ProgressEvent {
  step: string
  message: string
  percent?: number
  agent?: string
  function?: string
  round?: number
  data?: Record<string, unknown>
}

export interface ExecutarResponse {
  mensagem: string
  job_id: string
}

// --- Funcoes de API ---
export const getHealth = () => api.get<{ status: string }>('/health').then(r => r.data)

export const getPortfolioResumo = () => api.get<PortfolioResumo>('/portfolio/').then(r => r.data)
export const getPortfolioAtivos = () => api.get<Ativo[]>('/portfolio/ativos').then(r => r.data)
export const getPortfolioAlocacao = () => api.get<PortfolioAlocacao>('/portfolio/alocacao').then(r => r.data)
export const getPortfolioEvolucao = (periodo = '6m') =>
  api.get<EvolucaoPonto[]>(`/portfolio/evolucao?periodo=${periodo}`).then(r => r.data)

export const getTransacoes = (params?: { tipo?: string; ticker?: string }) =>
  api.get<Transacao[]>('/transacoes/', { params }).then(r => r.data)
export const criarTransacao = (data: NovaTransacao) =>
  api.post<Transacao>('/transacoes/', data).then(r => r.data)

export const getAnalises = () => api.get<Analise[]>('/analises/').then(r => r.data)
export const getAnalise = (id: number) => api.get<Analise>(`/analises/${id}`).then(r => r.data)
export const executarAnalise = () =>
  api.post<ExecutarResponse>('/analises/executar').then(r => r.data)
export const executarAnaliseAporte = (valor: number) =>
  api.post<ExecutarResponse>('/analises/aporte', { valor }).then(r => r.data)

export const getAlertas = (lido?: boolean) =>
  api.get<Alerta[]>('/alertas/', { params: lido !== undefined ? { lido } : {} }).then(r => r.data)
export const marcarAlertaLido = (id: number) =>
  api.patch<Alerta>(`/alertas/${id}/marcar-lido`).then(r => r.data)

export const getCustos = () => api.get<CustoToken[]>('/custos/').then(r => r.data)
export const getCustosResumo = () => api.get<CustoResumo>('/custos/resumo').then(r => r.data)
export const getCustosPorAgente = () =>
  api.get<CustoAgente[]>('/custos/por-agente').then(r => r.data)

export const getMacro = () => api.get<MacroData>('/market/macro').then(r => r.data)
export const searchTickers = (q: string) =>
  api.get<Array<{ ticker: string; nome: string; origem: string }>>('/market/search', { params: { q } }).then(r => r.data)

export const getConfiguracoes = () => api.get<Configuracao[]>('/configuracoes/').then(r => r.data)
export const salvarConfiguracoes = (configuracoes: Record<string, string>) =>
  api.patch('/configuracoes/', { configuracoes }).then(r => r.data)

// --- Formatadores ---
export const formatBRL = (valor: number) =>
  new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(valor)

export const formatPct = (valor: number) =>
  new Intl.NumberFormat('pt-BR', { style: 'percent', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(valor / 100)

export const formatData = (iso: string) => {
  const d = new Date(iso)
  return d.toLocaleDateString('pt-BR')
}

export const formatDataHora = (iso: string) => {
  const d = new Date(iso)
  return d.toLocaleString('pt-BR')
}
