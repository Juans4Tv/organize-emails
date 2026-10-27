import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api.js'
import DocRow from '../components/DocRow.jsx'
import PdfReviewModal from '../components/PdfReviewModal.jsx'
import { useAccount } from '../account.jsx'
import { useConfirm } from '../components/Confirm.jsx'
import { fmtMoney as fmt } from '../format.js'

export default function PlaceDetail() {
  const { id } = useParams()
  const [docs, setDocs] = useState([])
  const [selected, setSelected] = useState(new Set())
  const [msg, setMsg] = useState(null)
  const [busy, setBusy] = useState(false)
  const [flowFilter, setFlowFilter] = useState('')
  const [viewerDoc, setViewerDoc] = useState(null)
  const { activeAccount } = useAccount()
  const askConfirm = useConfirm()

  const loadDocs = useCallback(() => {
    const params = { place_id: id, limit: 500 }
    if (activeAccount) params.account = activeAccount
    api.documents(params)
      .then((r) => setDocs(r.items))
      .catch((e) => setMsg({ type: 'error', text: e.message }))
  }, [id, activeAccount])

  useEffect(() => { loadDocs() }, [loadDocs])

  const toggle = (docId) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(docId)) next.delete(docId)
      else next.add(docId)
      return next
    })
  }

  const allSelected = docs.length > 0 && selected.size === docs.length

  const placeName = docs[0]?.place_name || `Lugar #${id}`
  const gastos = docs.filter((d) => d.flow === 'gasto').reduce((a, d) => a + (d.amount ?? 0), 0)
  const ganancias = docs.filter((d) => d.flow === 'ganancia').reduce((a, d) => a + (d.amount ?? 0), 0)
  const verificados = docs.filter((d) => d.verified).length

  const visible = flowFilter ? docs.filter((d) => d.flow === flowFilter) : docs

  const verifySelected = async () => {
    if (selected.size === 0) return
    setBusy(true)
    try {
      await Promise.all([...selected].map((docId) => api.patchDocument(docId, { verified: true })))
      setMsg({ type: 'success', text: `${selected.size} documento(s) verificado(s).` })
      setSelected(new Set())
      loadDocs()
    } catch (e) {
      setMsg({ type: 'error', text: e.message })
    } finally {
      setBusy(false)
    }
  }

  const deleteSelected = async () => {
    if (selected.size === 0) return
    const ok = await askConfirm({
      title: 'Eliminar documentos',
      message: `¿Eliminar ${selected.size} documento(s)? Esta acción no se puede deshacer.`,
      confirmText: 'Eliminar',
      danger: true,
    })
    if (!ok) return
    setBusy(true)
    try {
      const r = await api.deleteBulk([...selected])
      setMsg({ type: 'success', text: `${r.deleted} documento(s) eliminado(s).` })
      setSelected(new Set())
      loadDocs()
    } catch (e) {
      setMsg({ type: 'error', text: e.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <p style={{ margin: '0 0 6px' }}>
        <Link to="/" className="muted">← Volver al dashboard</Link>
      </p>
      <h2>{placeName}</h2>

      {msg && <div className={`alert ${msg.type}`}>{msg.text}</div>}

      <div className="cards">
        <div className="card">
          <div className="label">Gastos</div>
          <div className="value red">${fmt(gastos)}</div>
        </div>
        <div className="card">
          <div className="label">Ganancias</div>
          <div className="value green">${fmt(ganancias)}</div>
        </div>
        <div className="card">
          <div className="label">Verificación de montos</div>
          <div className={`value ${verificados === docs.length && docs.length > 0 ? 'green' : 'amber'}`}>
            {verificados}/{docs.length}
          </div>
        </div>
      </div>

      <div className="row" style={{ marginBottom: 14 }}>
        <button
          disabled={busy || selected.size === 0}
          onClick={verifySelected}
        >Verificar seleccionados ({selected.size})</button>
        <button
          className="danger"
          disabled={busy || selected.size === 0}
          onClick={deleteSelected}
        >Eliminar seleccionados ({selected.size})</button>
        <label className="muted" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <input
            type="checkbox"
            checked={allSelected}
            onChange={() => setSelected(allSelected ? new Set() : new Set(docs.map((d) => d.id)))}
          />
          Seleccionar todos
        </label>
        <div style={{ flex: 1 }} />
        <select value={flowFilter} onChange={(e) => setFlowFilter(e.target.value)}>
          <option value="">Todos los flujos</option>
          <option value="gasto">Gastos</option>
          <option value="ganancia">Ganancias</option>
          <option value="neutral">Neutros</option>
        </select>
      </div>

      <datalist id="places-list">
        <option value={placeName} />
      </datalist>

      <div className="panel" style={{ padding: 0, overflowX: 'auto' }}>
        <table>
          <thead>
            <tr>
              <th></th><th>Archivo</th><th>Fecha</th><th>Flujo</th>
              <th>Monto</th><th>Mon.</th><th>Verificación</th><th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 && (
              <tr><td colSpan={8}><p className="muted" style={{ padding: 16 }}>Sin documentos en este lugar.</p></td></tr>
            )}
            {visible.map((d) => (
              <DocRow key={d.id} doc={d} showPlace={false}
                      selected={selected.has(d.id)} onToggle={toggle}
                      onOpenViewer={setViewerDoc}
                      onSaved={loadDocs} />
            ))}
          </tbody>
        </table>
      </div>

      {viewerDoc && (
        <PdfReviewModal
          doc={viewerDoc}
          onClose={() => setViewerDoc(null)}
          onSaved={loadDocs}
        />
      )}
    </div>
  )
}
