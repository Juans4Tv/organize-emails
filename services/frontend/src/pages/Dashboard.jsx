import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  ArcElement,
  Tooltip,
  Legend
} from 'chart.js'
import { Bar, Line, Pie } from 'react-chartjs-2'
import { api } from '../api.js'
import { useAccount } from '../account.jsx'
import { fmtCompact, fmtMoney } from '../format.js'

ChartJS.register(CategoryScale, LinearScale, BarElement, PointElement, LineElement, ArcElement, Tooltip, Legend)

const fmt = fmtMoney

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [sortKey, setSortKey] = useState('total')
  const navigate = useNavigate()
  const { activeAccount, accounts } = useAccount()

  useEffect(() => {
    const params = activeAccount ? { account: activeAccount } : undefined
    setData(null)
    api.dashboard(params).then(setData).catch((e) => setError(e.message))
  }, [activeAccount])

  if (error) return <div className="alert error">{error}</div>
  if (!data) return <p className="muted">Cargando…</p>

  const gasto = data.totals?.gasto?.amount ?? 0
  const ganancia = data.totals?.ganancia?.amount ?? 0
  const docs = Object.values(data.totals || {}).reduce((a, t) => a + t.count, 0)

  const placeRows = [...data.by_place].sort((a, b) => {
    if (sortKey === 'place') return a.place.localeCompare(b.place)
    if (sortKey === 'count') return b.count - a.count
    return (b.gasto + b.ganancia) - (a.gasto + a.ganancia)
  })

  const monthLabels = data.by_month.map((m) => m.month)

  const options = {
    responsive: true,
    plugins: {
      legend: { labels: { color: '#8b96ad' } },
      tooltip: {
        callbacks: {
          label: (ctx) => ` ${ctx.dataset.label}: $${fmtMoney(ctx.parsed.y ?? ctx.parsed)}`
        }
      }
    },
    scales: {
      x: { ticks: { color: '#8b96ad' }, grid: { color: '#2a3550' } },
      y: {
        ticks: {
          color: '#8b96ad',
          callback: (v) => '$' + fmtCompact(v)
        },
        grid: { color: '#2a3550' }
      }
    }
  }

  const chartPlaces = [...data.by_place].sort((a, b) => (b.gasto + b.ganancia) - (a.gasto + a.ganancia)).slice(0, 12)

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 }}>
        <h2>Dashboard{activeAccount ? ` · ${activeAccount}` : ''}</h2>
        <a href={`/api/export.xlsx${activeAccount ? `?account=${encodeURIComponent(activeAccount)}` : ''}`}>
          <button className="primary">Exportar Excel</button>
        </a>
      </div>

      {!activeAccount && accounts.length > 1 && data?.by_account?.length > 1 && (
        <div className="panel" style={{ marginBottom: 18, padding: 14 }}>
          <h3 style={{ marginTop: 0 }}>Por cuenta</h3>
          <table>
            <thead><tr><th>Cuenta</th><th>Documentos</th><th>Monto facturas</th><th>Por revisar</th></tr></thead>
            <tbody>
              {data.by_account.map((a) => (
                <tr key={a.account}>
                  <td>{a.account}{a.current ? '(activa)' : ''}</td>
                  <td>{a.count}</td>
                  <td>${fmt(a.monto)}</td>
                  <td>{a.needs_review > 0 ? <span className="badge review">{a.needs_review} por revisar</span> : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="cards">
        <div className="card">
          <div className="label">Total gastos</div>
          <div className="value red">${fmt(gasto)}</div>
        </div>
        <div className="card">
          <div className="label">Total ganancias</div>
          <div className="value green">${fmt(ganancia)}</div>
        </div>
        <div className="card">
          <div className="label">Documentos</div>
          <div className="value">{docs}</div>
        </div>
        <div className="card">
          <div className="label">Montos verificados</div>
          <div className={`value ${data.verified_count === data.documents_count && docs > 0 ? 'green' : 'amber'}`}>
            {data.verified_count}/{data.documents_count}
          </div>
        </div>
        <div className="card">
          <div className="label">Por revisar</div>
          <div className="value amber">{data.needs_review_count}</div>
        </div>
      </div>

      {data.links_manual_count > 0 && (
        <div className="alert info">
          Hay <b>{data.links_manual_count}</b> enlaces de descarga que requieren atención manual
          (el sitio pide iniciar sesión). Ve a <b>Revisión</b> para abrirlos.
        </div>
      )}

      <div className="panel" style={{ padding: 0, overflowX: 'auto', marginBottom: 22 }}>
        <table>
          <thead>
            <tr>
              <th style={{ cursor: 'pointer' }} onClick={() => setSortKey('place')}>Lugar</th>
              <th style={{ cursor: 'pointer' }} onClick={() => setSortKey('count')}>Docs</th>
              <th>Gastos</th>
              <th>Ganancias</th>
              <th>Montos verificados</th>
            </tr>
          </thead>
          <tbody>
            {placeRows.length === 0 && (
              <tr><td colSpan={5}><p className="muted" style={{ padding: 14 }}>Sin lugares todavía. Sincroniza tus correos primero.</p></td></tr>
            )}
            {placeRows.map((p) => (
              <tr key={p.id} className="clickable"
                  onClick={() => navigate(`/lugar/${p.id}`)}
                  title={`Ver facturas de ${p.place}`}>
                <td><b>{p.place}</b></td>
                <td>{p.count}</td>
                <td style={{ color: p.gasto ? 'var(--red)' : undefined }}>${fmt(p.gasto)}</td>
                <td style={{ color: p.ganancia ? 'var(--green)' : undefined }}>${fmt(p.ganancia)}</td>
                <td>
                  <span className={`badge ${p.verified === p.count ? 'ok' : 'review'}`}>
                    {p.verified}/{p.count} {p.verified === p.count ? '': ''}
                  </span>
                  {p.needs_review > 0 && (
                    <span className="badge review" style={{ marginLeft: 6 }}>{p.needs_review} por revisar</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid-2">
        <div className="panel">
          <h3>Gastos vs ganancias por lugar</h3>
          {chartPlaces.length === 0
            ? <p className="muted">Sin datos aún.</p>
            : <Bar options={options} data={{
                labels: chartPlaces.map((p) => p.place),
                datasets: [
                  { label: 'Gasto', data: chartPlaces.map((p) => p.gasto), backgroundColor: '#ff6b7a' },
                  { label: 'Ganancia', data: chartPlaces.map((p) => p.ganancia), backgroundColor: '#34c98e' }
                ]
              }} />}
        </div>
        <div className="panel">
          <h3>Evolución mensual</h3>
          {monthLabels.length === 0
            ? <p className="muted">Sin datos aún.</p>
            : <Line options={options} data={{
                labels: monthLabels,
                datasets: [
                  { label: 'Gasto', data: data.by_month.map((m) => m.gasto), borderColor: '#ff6b7a', backgroundColor: '#ff6b7a55', tension: .3 },
                  { label: 'Ganancia', data: data.by_month.map((m) => m.ganancia), borderColor: '#34c98e', backgroundColor: '#34c98e55', tension: .3 }
                ]
              }} />}
        </div>
      </div>

      <div className="panel" style={{ maxWidth: 420 }}>
        <h3>Proporción general</h3>
        {docs === 0
          ? <p className="muted">Sin datos aún.</p>
          : <Pie options={{ plugins: { legend: { labels: { color: '#8b96ad' } } } }} data={{
              labels: ['Gasto', 'Ganancia'],
              datasets: [{
                data: [gasto, ganancia],
                backgroundColor: ['#ff6b7a', '#34c98e']
              }]
            }} />}
      </div>
    </div>
  )
}
