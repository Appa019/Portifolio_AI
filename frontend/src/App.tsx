import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Transacoes from './pages/Transacoes'
import Analises from './pages/Analises'
import Custos from './pages/Custos'
import Alertas from './pages/Alertas'
import Config from './pages/Config'
import { Agentes } from './pages/Agentes'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="transacoes" element={<Transacoes />} />
          <Route path="analises" element={<Analises />} />
          <Route path="agentes" element={<Agentes />} />
          <Route path="custos" element={<Custos />} />
          <Route path="alertas" element={<Alertas />} />
          <Route path="config" element={<Config />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
