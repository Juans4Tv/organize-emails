import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import DocRow from '../components/DocRow.jsx'
import PdfReviewModal from '../components/PdfReviewModal.jsx'
import { useConfirm } from '../components/Confirm.jsx'
import { useAccount } from '../account.jsx'

const PAGE_SIZE = 50

export default function Explorer() {
  const [places, setPlaces] = useState([])
  const [selectedPlace, setSelectedPlace] = useState(null)
  const [docs, setDocs] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [q, setQ] = useState('')
  const [flowFilter, setFlowFilter] = useState('')
  const [viewerDoc, setViewerDoc] = useState(null)
  const [selectedIds, setSelectedIds] = useState(new Set())
  const [busySel, setBusySel] = useState(false)
  const [msg, setMsg] = useState(null)
  const { activeAccount } = useAccount()
  const askConfirm = useConfirm()

  const loadPlaces = () => api.places().then(setPlaces).catch(() => {})

  useEffect(() => { loadPlaces() }, [])

  useEffect(() => {
    setPage(1)
    setSelectedIds(new Set())
  }, [selectedPlace, q, flowFilter, activeAccount])

  const loadDocs = useCallback(() => {
    const params = { limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE }
    if (selectedPlace) params.place_id = selectedPlace.id
    if (q) params.q = q
    if (flowFilter) params.flow = flowFilter
    if (activeAccount) params.account = activeAccount
    api.documents(params)
      .then((r) => {
        setDocs(r.items)
        setTotal(r.total ?? r.items.length)
        if ((page - 1) * PAGE_SIZE >= (r.total ?? 0) && page > 1) setPage(page - 1)
      })
      .catch(() => {})
  }, [selectedPlace, q, flowFilter, activeAccount, page])

  useEffect(() => { loadDocs() }, [loadDocs])

  const toggleSelect = (id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const allVisibleSelected = docs.length > 0 && docs.every((d) => selectedIds.has(d.id))
  const toggleAllVisible = () => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      docs.forEach((d) => (allVisibleSelected ? next.delete(d.id) : next.add(d.id)))
      return next
    })
  }

  const bulkAction = async (kind) => {
    const ids = [...selectedIds]
    if (ids.length === 0) return
    const ok = await askConfirm(kind === 'verify'
      ? { title: 'Verificar documentos',
          message: `¿Marcar ${ids.length} documento(s) como verificados?`,
          confirmText: 'Verificar' }
      : { title: 'Eliminar documentos',
          message: `¿Eliminar ${ids.length} documento(s)? Esta acción no se puede deshacer.`,
          confirmText: 'Eliminar', danger: true })
    if (!ok) return
    setBusySel(true)
    setMsg(null)
    try {
      if (kind === 'verify') await api.bulkVerify(ids)
      else await api.deleteBulk(ids)
      setSelectedIds(new Set())
      loadDocs()
      loadPlaces()
    } catch (e) {
      setMsg({ type: 'error', text: e.message })
    } finally {
      setBusySel(false)
    }
  }

  const from = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1
  const to = Math.min(page * PAGE_SIZE, total)

  return (
    <div>
      <h2>Explorador</h2>

      <datalist id="places-list">
        {places.map((p) => <option key={p.id} value={p.name} />)}
      </datalist>

      <div className="explorer-grid">
        <div className="panel" style={{ padding: 10 }}>
          <ul className="place-list">
            <li className={!selectedPlace ? 'active' : ''} onClick={() => setSelectedPlace(null)}>
              <b>Todos los lugares</b>
            </li>
            {places.map((p) => (
              <li key={p.id} className={selectedPlace?.id === p.id ? 'active' : ''}
                  onClick={() => setSelectedPlace(p)}>
                <span>{p.name}</span>
                <span className="count">{p.documents}</span>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <div className="row" style={{ marginBottom: 12 }}>
            <input placeholder="Buscar archivo, texto, link…" value={q}
                   onChange={(e) => setQ(e.target.value)} style={{ flex: 1 }} />
            <select value={flowFilter} onChange={(e) => setFlowFilter(e.target.value)} style={{ width: 130 }}>
              <option value="">Todo el flujo</option>
              <option value="gasto">Gasto</option>
              <option value="ganancia">Ganancia</option>
              <option value="neutral">Neutro</option>
            </select>
          </div>

          {selectedIds.size > 0 && (
            <div className="sel-bar">
              <b>{selectedIds.size} seleccionado(s)</b>
              <button className="small primary" disabled={busySel} onClick={() => bulkAction('verify')}>
                Verificar
              </button>
              <button className="small danger" disabled={busySel} onClick={() => bulkAction('delete')}>
                Eliminar
              </button>
              <button className="small" onClick={() => setSelectedIds(new Set())}>Cancelar</button>
              {msg && <span className="muted" style={{ color: 'var(--red)' }}>{msg.text}</span>}
            </div>
          )}

          <div className="panel" style={{ padding: 0, overflowX: 'auto' }}>
            <table>
              <thead>
                <tr>
                  <th style={{ width: 30 }}>
                    <input type="checkbox" checked={allVisibleSelected} onChange={toggleAllVisible} />
                  </th>
                  <th>Archivo</th><th>Fecha</th><th>Flujo</th>
                  <th>Monto</th><th>Estado</th><th></th>
                </tr>
              </thead>
              <tbody>
                {docs.length === 0 && (
                  <tr><td colSpan={7}><p className="muted" style={{ padding: 16 }}>Sin documentos.</p></td></tr>
                )}
                {docs.map((d) => (
                  <DocRow key={d.id} doc={d} compact
                          selected={selectedIds.has(d.id)} onToggle={toggleSelect}
                          onOpenViewer={setViewerDoc}
                          onSaved={loadDocs} />
                ))}
              </tbody>
            </table>
          </div>

          <div className="pager">
            <button className="small" disabled={page <= 1} onClick={() => setPage(page - 1)}>‹ Anterior</button>
            <span className="muted">{from}–{to} de {total}</span>
            <button className="small" disabled={page * PAGE_SIZE >= total} onClick={() => setPage(page + 1)}>
              Siguiente ›
            </button>
          </div>
        </div>
      </div>

      {viewerDoc && (
        <PdfReviewModal
          doc={viewerDoc}
          onClose={() => setViewerDoc(null)}
          onSaved={() => { loadDocs(); loadPlaces() }}
        />
      )}
    </div>
  )
}
