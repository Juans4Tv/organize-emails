import { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'

export default function Config() {
  const [settings, setSettings] = useState({ imap_host: 'imap.gmail.com', imap_user: '', own_rfc: '', owner_name: '', base_currency: 'COP', fx_usd_cop: '4000', has_password: false })
  const [password, setPassword] = useState('')
  const [since, setSince] = useState(firstDayOfMonth())
  const [before, setBefore] = useState(today())
  const [job, setJob] = useState(null)
  const [live, setLive] = useState({})
  const [elapsed, setElapsed] = useState(0)
  const [msg, setMsg] = useState(null)
  const [busy, setBusy] = useState(false)
  const [testing, setTesting] = useState(false)
  const pollRef = useRef(null)
  const startRef = useRef(0)

  useEffect(() => {
    api.getSettings().then(setSettings).catch((e) => setMsg({ type: 'error', text: e.message }))
    api.latestJob().then((j) => { if (!j.none) setJob(j) }).catch(() => {})
    return () => clearInterval(pollRef.current)
  }, [])

  const saveSettings = async () => {
    try {
      await api.saveSettings({
        imap_host: settings.imap_host,
        imap_user: settings.imap_user,
        own_rfc: settings.own_rfc,
        owner_name: settings.owner_name,
        base_currency: settings.base_currency,
        fx_usd_cop: settings.fx_usd_cop,
        ...(password ? { imap_password: password } : {})
      })
      setMsg({ type: 'success', text: 'Configuración guardada.' })
      setPassword('')
      const s = await api.getSettings()
      setSettings(s)
    } catch (e) {
      setMsg({ type: 'error', text: e.message })
    }
  }

  const probarConexion = async () => {
    setTesting(true)
    try {
      // guarda primero lo que haya en el formulario para probar lo actual
      await api.saveSettings({
        imap_host: settings.imap_host,
        imap_user: settings.imap_user,
        own_rfc: settings.own_rfc,
        owner_name: settings.owner_name,
        base_currency: settings.base_currency,
        fx_usd_cop: settings.fx_usd_cop,
        ...(password ? { imap_password: password } : {})
      })
      const r = await api.testConnection()
      if (r.ok) {
        setMsg({ type: 'success', text: `Conexión exitosa con ${r.user} vía ${r.host}. ¡Puedes sincronizar!` })
      } else {
        setMsg({ type: 'error', text: `${r.error}` })
      }
    } catch (e) {
      setMsg({ type: 'error', text: e.message })
    } finally {
      setTesting(false)
    }
  }

  const stopPolling = () => {
    clearInterval(pollRef.current)
    pollRef.current = null
    setBusy(false)
  }

  const startSync = async () => {
    if (!since) return
    setBusy(true)
    setLive({})
    setElapsed(0)
    setMsg({ type: 'info', text: 'Sincronización iniciada…' })
    try {
      const { job_id } = await api.startSync(since, before)
      clearInterval(pollRef.current)
      startRef.current = Date.now()
      pollRef.current = setInterval(async () => {
        let j
        try {
          j = await api.job(job_id)
        } catch {
          return
        }
        setJob(j)
        try { setLive(JSON.parse(j.result || '{}')) } catch { /* sin datos */ }
        setElapsed(Math.round((Date.now() - startRef.current) / 1000))

        if (j.status === 'done') {
          stopPolling()
          setMsg({
            type: 'success',
            text: `Listo en ${Math.round((Date.now() - startRef.current) / 1000)}s: ${j.result}`
          })
        } else if (j.status === 'failed') {
          stopPolling()
          setMsg({ type: 'error', text: `Error: ${j.error}` })
        } else if (Date.now() - startRef.current > 15 * 60 * 1000) {
          stopPolling()
          setMsg({
            type: 'info',
            text: 'La sincronización sigue trabajando en segundo plano. Puedes ver los resultados en el Explorador; esta pantalla dejó de esperar.'
          })
        }
      }, 2000)
    } catch (e) {
      setMsg({ type: 'error', text: e.message })
      setBusy(false)
    }
  }

  const scanInbox = async () => {
    try {
      const r = await api.scanInbox()
      setMsg({ type: 'success', text: `Carpeta inbox procesada: ${r.added} archivo(s) en cola.` })
    } catch (e) {
      setMsg({ type: 'error', text: e.message })
    }
  }

  return (
    <div>
      <h2>Configuración</h2>

      {msg && <div className={`alert ${msg.type}`}>{msg.text}</div>}

      <div className="panel" style={{ maxWidth: 640 }}>
        <h3>Conexión Gmail (IMAP)</h3>
        <ol className="muted" style={{ lineHeight: 1.7 }}>
          <li>Activa la verificación en 2 pasos en tu cuenta de Google.</li>
          <li>Ve a <b>myaccount.google.com → Seguridad → Contraseñas de aplicación</b>.</li>
          <li>Crea una llamada «OpenOrganizador» y copia la contraseña de 16 letras.</li>
          <li>Pégala abajo junto con tu correo y guarda.</li>
        </ol>

        <div className="row">
          <div className="field">
            <label>Servidor IMAP</label>
            <input value={settings.imap_host} style={{ width: 220 }}
                   onChange={(e) => setSettings({ ...settings, imap_host: e.target.value })} />
          </div>
          <div className="field">
            <label>Correo</label>
            <input placeholder="tucorreo@gmail.com" value={settings.imap_user} style={{ width: 240 }}
                   onChange={(e) => setSettings({ ...settings, imap_user: e.target.value })} />
          </div>
          <div className="field">
            <label>Contraseña de aplicación {settings.has_password ? '(guardada)' : ''}</label>
            <input type="password" placeholder="xxxx xxxx xxxx xxxx" value={password} style={{ width: 240 }}
                   onChange={(e) => setPassword(e.target.value)} />
          </div>
        </div>

        <div className="row" style={{ marginTop: 14 }}>
          <div className="field">
            <label>Tu nombre (como aparece en tus facturas)</label>
            <input placeholder="Juan Pérez" value={settings.owner_name} style={{ width: 260 }}
                   onChange={(e) => setSettings({ ...settings, owner_name: e.target.value })} />
          </div>
          <div className="field">
            <label>Tu RFC/NIT (opcional)</label>
            <input placeholder="XAXX010101000" value={settings.own_rfc} style={{ width: 220 }}
                   onChange={(e) => setSettings({ ...settings, own_rfc: e.target.value.toUpperCase() })} />
          </div>
          <button className="primary" style={{ height: 38 }} onClick={saveSettings}>Guardar configuración</button>
          <button style={{ height: 38 }} disabled={testing} onClick={probarConexion}>
            {testing ? 'Probando…' : 'Probar conexión'}
          </button>
        </div>

        <div className="row" style={{ marginTop: 14 }}>
          <div className="field">
            <label>Moneda</label>
            <select value={settings.base_currency} style={{ width: 100 }}
                    onChange={(e) => setSettings({ ...settings, base_currency: e.target.value })}>
              <option value="COP">COP</option>
              <option value="USD">USD</option>
            </select>
          </div>
          <div className="field">
            <label>Tasa de cambio (1 USD = ? COP)</label>
            <input placeholder="4000" value={settings.fx_usd_cop} style={{ width: 120 }}
                   onChange={(e) => setSettings({ ...settings, fx_usd_cop: e.target.value.replace(/[^\d.,]/g, '') })} />
          </div>
        </div>
      </div>

      <div className="panel" style={{ maxWidth: 640 }}>
        <h3>Sincronizar correos</h3>
        <p className="muted">Descarga adjuntos PDF/XML/ZIP del rango de fechas indicado.</p>
        <div className="row">
          <div className="field">
            <label>Desde</label>
            <input type="date" value={since} onChange={(e) => setSince(e.target.value)} />
          </div>
          <div className="field">
            <label>Hasta</label>
            <input type="date" value={before} onChange={(e) => setBefore(e.target.value)} />
          </div>
          <button className="primary" style={{ height: 38 }} disabled={busy} onClick={startSync}>
            {busy ? 'Sincronizando…' : '▶ Sincronizar'}
          </button>
        </div>

        {busy && (
          <div className="alert info" style={{ marginTop: 14 }}>
            ⏳ Procesando… {elapsed}s transcurridos ·
            correos: <b>{live.emails ?? 0}</b> ·
            archivos: <b>{live.archivos ?? 0}</b> ·
            ZIPs abiertos: <b>{live.zips ?? 0}</b> ·
            links descargados: <b>{live.links_descargados ?? 0}</b> ·
            links manuales: <b>{live.links_manuales ?? 0}</b>
            {(live.emails_con_error ?? 0) > 0 && <> · correos con problema: <b>{live.emails_con_error}</b></>}
            <div className="muted" style={{ marginTop: 6 }}>
              Los archivos ya van apareciendo en el Explorador mientras termina.
            </div>
          </div>
        )}

        {job && (
          <div style={{ marginTop: 16 }}>
            <span className={`badge ${job.status === 'done' ? 'ok' : job.status === 'failed' ? 'gasto' : 'review'}`}>
              Última sincronización: {job.status}
            </span>
            {job.error && <p className="muted" style={{ color: 'var(--red)' }}>{job.error}</p>}
          </div>
        )}
      </div>

      <div className="panel" style={{ maxWidth: 640 }}>
        <h3>Carpeta manual (inbox)</h3>
        <p className="muted">
          ¿Facturas que solo bajan desde un portal? Guárdalas en{' '}
          <code>&lt;proyecto&gt;\data\inbox</code> y pulsa el botón para procesarlas igual que
          las del correo.
        </p>
        <button className="primary" onClick={scanInbox}>Procesar carpeta inbox</button>
      </div>

    </div>
  )
}

function today() {
  return new Date().toISOString().slice(0, 10)
}

function firstDayOfMonth() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`
}
