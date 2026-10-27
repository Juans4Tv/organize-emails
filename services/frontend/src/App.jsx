import { NavLink, Route, Routes } from 'react-router-dom'
import Dashboard from './pages/Dashboard.jsx'
import Explorer from './pages/Explorer.jsx'
import Review from './pages/Review.jsx'
import Config from './pages/Config.jsx'
import LocalFolder from './pages/LocalFolder.jsx'
import PlaceDetail from './pages/PlaceDetail.jsx'
import { AccountProvider, useAccount } from './account.jsx'
import { ConfirmProvider } from './components/Confirm.jsx'

function AccountSelector() {
  const { accounts, activeAccount, setActiveAccount } = useAccount()
  return (
    <div className="account-switch">
      <label>Cuenta activa</label>
      <select value={activeAccount} onChange={(e) => setActiveAccount(e.target.value)}>
        <option value="">Todas las cuentas</option>
        {accounts.map((a) => (
          <option key={a.account} value={a.account}>
            {a.account}{a.current ? ' (activa)' : ''} · {a.count}
          </option>
        ))}
      </select>
    </div>
  )
}

export default function App() {
  return (
    <ConfirmProvider>
      <AccountProvider>
        <div className="layout">
          <aside className="sidebar">
            <div className="brand">
              <div>
                <h1>OpenOrganizador</h1>
                <p>Facturas desde Gmail</p>
              </div>
            </div>
            <nav>
              <NavLink to="/" end>Dashboard</NavLink>
              <NavLink to="/explorador">Explorador</NavLink>
              <NavLink to="/revision">Revisión</NavLink>
              <NavLink to="/carpeta-local">Carpeta local</NavLink>
              <NavLink to="/config">Configuración</NavLink>
            </nav>
            <AccountSelector />
          </aside>
          <main className="content">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/explorador" element={<Explorer />} />
              <Route path="/revision" element={<Review />} />
              <Route path="/carpeta-local" element={<LocalFolder />} />
              <Route path="/config" element={<Config />} />
              <Route path="/lugar/:id" element={<PlaceDetail />} />
            </Routes>
          </main>
        </div>
      </AccountProvider>
    </ConfirmProvider>
  )
}
