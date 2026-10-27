import { useState } from 'react'
import { api } from '../api.js'
import { fmtMoney } from '../format.js'
import MoneyInput from './MoneyInput.jsx'

const FLOW_LABEL = { gasto: 'Gasto', ganancia: 'Ganancia', neutral: 'Neutro' }
const TYPE_LABEL = (doc) => (doc.source_type === 'link' ? 'LINK' : doc.ext === '.xml' ? 'XML' : 'PDF')

export default function DocRow({ doc, onSaved, showPlace = true, selected, onToggle, onOpenViewer, compact = false }) {
  const [edit, setEdit] = useState({
    flow: doc.flow,
    amount: doc.amount ?? '',
    place_name: doc.place_name,
    doc_date: (doc.doc_date || '').slice(0, 10)
  })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const viewable = doc.ext === '.pdf' || doc.ext === '.xml'

  const openViewer = () => {
    if (onOpenViewer) onOpenViewer(doc)
    else window.open(`/api/files/${doc.id}`, '_blank')
  }

  const save = async (extra = {}) => {
    setBusy(true)
    setErr('')
    try {
      await api.patchDocument(doc.id, { ...edit, ...extra })
      onSaved()
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  if (compact) {
    return (
      <tr className="doc-row-compact" onClick={() => viewable && openViewer()} title={doc.sender}>
        {onToggle && (
          <td onClick={(e) => e.stopPropagation()}>
            <input type="checkbox" checked={!!selected} onChange={() => onToggle(doc.id)} />
          </td>
        )}
        <td>
          <span className="doc-type">{TYPE_LABEL(doc)}</span>{' '}
          <span className="doc-name">{doc.original_name}</span>
          {doc.account && <div className="muted" style={{ fontSize: 11 }}>Cuenta: {doc.account}</div>}
          {doc.error && <div className="muted" style={{ color: 'var(--red)', fontSize: 11 }}>{doc.error}</div>}
        </td>
        <td>{(doc.doc_date || '').slice(0, 10)}</td>
        <td><span className={`badge flow-${doc.flow}`}>{FLOW_LABEL[doc.flow] || doc.flow}</span></td>
        <td className="num">{doc.amount != null && doc.amount !== '' ? `$${fmtMoney(doc.amount)}` : '—'}</td>
        <td>
          {doc.verified
            ? <span className="badge ok">Verificado</span>
            : doc.status === 'link_manual'
              ? <span className="badge review">Link manual</span>
              : <span className="badge review">Sin verificar</span>}
        </td>
        <td style={{ whiteSpace: 'nowrap' }} onClick={(e) => e.stopPropagation()}>
          {viewable && <button className="small" onClick={openViewer}>Ver</button>}
        </td>
        {err && <td style={{ color: 'var(--red)' }}>{err}</td>}
      </tr>
    )
  }

  return (
    <tr>
      {onToggle && (
        <td>
          <input type="checkbox" checked={!!selected} onChange={() => onToggle(doc.id)} />
        </td>
      )}
      {showPlace && (
        <td>
          <input
            list="places-list"
            value={edit.place_name}
            onChange={(e) => setEdit({ ...edit, place_name: e.target.value })}
            style={{ width: 150 }}
          />
        </td>
      )}
      <td title={doc.sender}>
        <span className="doc-type">{TYPE_LABEL(doc)}</span>{' '}
        <span
          style={{ cursor: viewable ? 'pointer' : 'default', textDecoration: viewable ? 'underline dotted' : 'none' }}
          onClick={() => viewable && openViewer()}
        >
          {doc.original_name}
        </span>
        {doc.error && <div className="muted" style={{ color: 'var(--red)' }}>{doc.error}</div>}
        {doc.account && <div className="muted" style={{ fontSize: 11 }}>Cuenta: {doc.account}</div>}
      </td>
      <td>{(doc.doc_date || '').slice(0, 10)}</td>
      <td>
        <select value={edit.flow} onChange={(e) => setEdit({ ...edit, flow: e.target.value })}>
          <option value="gasto">Gasto</option>
          <option value="ganancia">Ganancia</option>
          <option value="neutral">Neutro</option>
        </select>
      </td>
      <td>
        <MoneyInput
          value={edit.amount}
          onChange={(raw) => setEdit({ ...edit, amount: raw })}
          style={{ width: 130 }}
        />
      </td>
      <td>{doc.currency}</td>
      <td>
        {doc.verified
          ? <span className="badge ok">Verificado</span>
          : <span className="badge review">Sin verificar</span>}
        {(doc.needs_review || doc.confidence < 0.55) && (
          <div style={{ marginTop: 4 }}>
            <span className="badge review">Revisar {Math.round((doc.confidence ?? 0) * 100)}%</span>
          </div>
        )}
      </td>
      <td style={{ whiteSpace: 'nowrap' }}>
        <button className="small primary" disabled={busy} onClick={() => save()}>Guardar</button>{' '}
        {!doc.verified && (
          <button className="small" disabled={busy} onClick={() => save({ verified: true })}>Monto OK</button>
        )}{' '}
        {viewable && (
          <button className="small" onClick={openViewer}>Ver</button>
        )}
      </td>
      {err && <td style={{ color: 'var(--red)' }}>{err}</td>}
    </tr>
  )
}
