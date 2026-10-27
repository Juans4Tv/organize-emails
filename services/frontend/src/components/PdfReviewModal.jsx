import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { useConfirm } from './Confirm.jsx'
import MoneyInput from './MoneyInput.jsx'

export default function PdfReviewModal({ doc, onClose, onSaved }) {
  const [edit, setEdit] = useState({
    amount: doc.amount ?? '',
    flow: doc.flow,
    place_name: doc.place_name,
    doc_date: (doc.doc_date || '').slice(0, 10)
  })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [relatedId, setRelatedId] = useState(null)
  const [relatedLoading, setRelatedLoading] = useState(false)
  const askConfirm = useConfirm()

  const isXml = doc.ext === '.xml'

  useEffect(() => {
    if (!isXml) return
    let alive = true
    setRelatedLoading(true)
    api.relatedDocument(doc.id)
      .then((r) => { if (alive) setRelatedId(r.related_id ?? null) })
      .catch(() => {})
      .finally(() => { if (alive) setRelatedLoading(false) })
    return () => { alive = false }
  }, [doc.id, isXml])

  const save = async (extra = {}) => {
    setBusy(true)
    setErr('')
    try {
      await api.patchDocument(doc.id, { ...edit, ...extra })
      onSaved()
      onClose()
    } catch (e) {
      setErr(e.message)
      setBusy(false)
    }
  }

  const markNotInvoice = async () => {
    const ok = await askConfirm({
      title: 'Marcar como no factura',
      message: `"${doc.original_name}" saldrá de la lista de revisión y no contará en los totales.`,
      confirmText: 'Marcar',
    })
    if (!ok) return
    setBusy(true)
    setErr('')
    try {
      await api.patchDocument(doc.id, { doc_kind: 'no_factura', needs_review: false })
      onSaved()
      onClose()
    } catch (e) {
      setErr(e.message)
      setBusy(false)
    }
  }

  const remove = async () => {
    const ok = await askConfirm({
      title: 'Eliminar documento',
      message: `¿Eliminar "${doc.original_name}"? Esta acción no se puede deshacer.`,
      confirmText: 'Eliminar',
      danger: true,
    })
    if (!ok) return
    setBusy(true)
    try {
      await api.deleteDocument(doc.id)
      onSaved()
      onClose()
    } catch (e) {
      setErr(e.message)
      setBusy(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal-review" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <span title={doc.original_name}>{doc.original_name}</span>
          <button className="small" onClick={onClose}>Cerrar</button>
        </div>
        <div className="modal-review-body">
          <div className="modal-pdf">
            {isXml ? (
              relatedLoading ? (
                <p className="muted" style={{ padding: 16 }}>Buscando el PDF asociado…</p>
              ) : relatedId ? (
                <>
                  <div className="related-note">
                    Mostrando el PDF adjunto de esta factura ({doc.original_name})
                  </div>
                  <iframe src={`/api/files/${relatedId}`} title={doc.original_name} />
                </>
              ) : (
                <div className="no-pdf-note">
                  <div className="related-note">
                    No hay un PDF adjunto. Vista generada desde el XML de la factura.
                  </div>
                  <iframe src={`/api/documents/${doc.id}/preview-html`} title={doc.original_name} />
                </div>
              )
            ) : (
              <iframe src={`/api/files/${doc.id}`} title={doc.original_name} />
            )}
          </div>
          <div className="modal-form">
            {err && <div className="alert error">{err}</div>}
            {doc.error && !err && <div className="alert error">{doc.error}</div>}
            <div className="field">
              <label>Monto total</label>
              <MoneyInput
                value={edit.amount}
                onChange={(raw) => setEdit({ ...edit, amount: raw })}
                autoFocus
              />
            </div>
            <div className="field">
              <label>Flujo</label>
              <select value={edit.flow} onChange={(e) => setEdit({ ...edit, flow: e.target.value })}>
                <option value="gasto">Gasto</option>
                <option value="ganancia">Ganancia</option>
                <option value="neutral">Neutro</option>
              </select>
            </div>
            <div className="field">
              <label>Lugar</label>
              <input
                list="places-list"
                value={edit.place_name}
                onChange={(e) => setEdit({ ...edit, place_name: e.target.value })}
              />
            </div>
            <div className="field">
              <label>Fecha del documento</label>
              <input
                type="date"
                value={edit.doc_date}
                onChange={(e) => setEdit({ ...edit, doc_date: e.target.value })}
              />
            </div>
            <p className="muted" style={{ fontSize: 12 }}>
              Lee el monto en la factura y escríbelo aquí. Con «Monto OK» queda verificado.
            </p>
            <div style={{ display: 'grid', gap: 8 }}>
              <button className="primary" disabled={busy} onClick={() => save()}>Guardar cambios</button>
              {!doc.verified && (
                <button className="primary" disabled={busy}
                        onClick={() => save({ verified: true })}>Monto OK — verificar</button>
              )}
              <button disabled={busy} onClick={markNotInvoice}>No es factura</button>
              <button className="danger" disabled={busy} onClick={remove}>Eliminar documento</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
