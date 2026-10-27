import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import DocRow from '../components/DocRow.jsx'
import PdfReviewModal from '../components/PdfReviewModal.jsx'
import { useAccount } from '../account.jsx'

export default function Review() {
  const [docs, setDocs] = useState([])
  const [links, setLinks] = useState([])
  const [places, setPlaces] = useState([])
  const [msg, setMsg] = useState('')
  const [viewerDoc, setViewerDoc] = useState(null)
  const { activeAccount } = useAccount()

  const loadAll = useCallback(() => {
    const base = activeAccount ? { account: activeAccount } : {}
    api.documents({ needs_review: 'true', ...base }).then((r) => setDocs(r.items)).catch(() => {})
    api.documents({ status: 'link_manual', limit: 200, ...base }).then((r) => setLinks(r.items)).catch(() => {})
    api.places().then(setPlaces).catch(() => {})
  }, [activeAccount])

  useEffect(() => {
    loadAll()
  }, [loadAll])

  return (
    <div>
      <h2>Revisión</h2>

      <datalist id="places-list">
        {places.map((p) => <option key={p.id} value={p.name} />)}
      </datalist>

      <div className="panel">
        <h3>Documentos por revisar ({docs.length})</h3>
        <p className="muted">
          Corrige lugar, flujo (gasto/ganancia) o monto y guarda. Usa el boton «Ver» para leer la
          factura y confirmar el monto en la misma ventana.
        </p>

        <div style={{ overflowX: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th>Lugar</th><th>Archivo</th><th>Fecha</th><th>Flujo</th>
                <th>Monto</th><th>Mon.</th><th>Confianza</th><th>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {docs.length === 0 && (
                <tr><td colSpan={8}><p className="muted">Nada por revisar.</p></td></tr>
              )}
              {docs.map((d) => (
                <DocRow key={d.id} doc={d} onSaved={loadAll} onOpenViewer={setViewerDoc} />
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel">
        <h3>Enlaces que requieren descarga manual ({links.length})</h3>
        <p className="muted">
          Estos correos traen la factura como enlace y el sitio pide iniciar sesión para
          descargarla. Ábrelos, descarga el PDF/XML y suéltalo en la carpeta{' '}
          <code>data\inbox</code>, luego pulsa «Procesar carpeta inbox» en Configuración.
        </p>
        {msg && <div className="alert success">{msg}</div>}
        <table>
          <thead><tr><th>Enlace</th><th>Acciones</th></tr></thead>
          <tbody>
            {links.length === 0 && (
              <tr><td colSpan={2}><p className="muted">Sin enlaces pendientes.</p></td></tr>
            )}
            {links.map((l) => (
              <tr key={l.id}>
                <td style={{ maxWidth: 600, overflowWrap: 'anywhere' }}>{l.link_url}</td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  <button className="small primary" onClick={() => window.open(l.link_url, '_blank')}>
                    Abrir ↗
                  </button>{' '}
                  <button
                    className="small danger"
                    onClick={async () => {
                      await api.deleteDocument(l.id)
                      setMsg('Enlace marcado como resuelto.')
                      setTimeout(() => setMsg(''), 3000)
                      loadAll()
                    }}
                  >Listo</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {viewerDoc && (
        <PdfReviewModal
          doc={viewerDoc}
          onClose={() => setViewerDoc(null)}
          onSaved={loadAll}
        />
      )}
    </div>
  )
}
