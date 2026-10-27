import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { useAccount } from '../account.jsx'
import { useConfirm } from '../components/Confirm.jsx'

function fmtSize(bytes) {
  if (!bytes && bytes !== 0) return '?'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function fmtDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString('es-CO', { dateStyle: 'short', timeStyle: 'short' })
}

export default function LocalFolder() {
  const { accounts, activeAccount } = useAccount()
  const [folder, setFolder] = useState('')
  const [windowsPath, setWindowsPath] = useState('')
  const [items, setItems] = useState([])
  const [selected, setSelected] = useState(new Set())
  const [targetAccount, setTargetAccount] = useState('')
  const [customAccount, setCustomAccount] = useState('')
  const [useCustom, setUseCustom] = useState(false)
  const [busy, setBusy] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [msg, setMsg] = useState(null)
  const fileInputRef = useRef(null)
  const askConfirm = useConfirm()

  useEffect(() => {
    setTargetAccount(activeAccount || (accounts[0]?.account ?? ''))
  }, [activeAccount, accounts])

  const load = useCallback(() => {
    api.localFolderList()
      .then((r) => {
        setFolder(r.folder)
        setItems(r.items)
        setSelected(new Set())
      })
      .catch((e) => setMsg({ type: 'error', text: e.message }))
    api.localFolderOpen()
      .then((r) => setWindowsPath(r.windows_path || ''))
      .catch(() => {})
  }, [])

  useEffect(() => { load() }, [load])

  const toggle = (name) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  const allVisible = items.length > 0 && items.every((i) => selected.has(i.name))
  const toggleAll = () => {
    setSelected((prev) => {
      const next = new Set(prev)
      items.forEach((i) => (allVisible ? next.delete(i.name) : next.add(i.name)))
      return next
    })
  }

  const uploadFiles = async (fileList) => {
    const files = [...(fileList || [])]
    if (files.length === 0) return
    setUploading(true)
    setMsg(null)
    let ok = 0
    let fail = 0
    for (const file of files) {
      try {
        await api.localFolderUpload(file)
        ok += 1
      } catch (e) {
        fail += 1
        setMsg({ type: 'error', text: `${file.name}: ${e.message}` })
      }
    }
    setUploading(false)
    if (ok > 0) setMsg({ type: 'success', text: `${ok} archivo(s) subido(s). Ya aparecen en la lista.` })
    load()
  }

  const onDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    uploadFiles(e.dataTransfer.files)
  }

  const openFolder = async () => {
    if (windowsPath) {
      // intenta abrir en el Explorador vía ruta de red/archivo
      window.open(`file:///${windowsPath.replace(/\\/g, '/')}`, '_self')
    } else {
      setMsg({ type: 'error', text: 'No se pudo determinar la ruta de la carpeta' })
    }
  }

  const processSelected = async () => {
    const names = [...selected]
    if (names.length === 0) return
    const finalAccount = useCustom ? customAccount.trim() : targetAccount
    const ok = await askConfirm({
      title: 'Procesar archivos de la carpeta local',
      message: `¿Procesar ${names.length} archivo(s)?\nCuenta destino: ${finalAccount || '(sin cuenta)'}\n\nLos archivos se moverán a "procesados" tras procesarlos.`,
      confirmText: 'Procesar'
    })
    if (!ok) return
    setBusy(true)
    setMsg(null)
    try {
      const r = await api.localFolderProcess(names, finalAccount)
      const parts = [`Agregados: ${r.added}`, r.zips ? `ZIPs: ${r.zips}` : '']
      if (r.errors && r.errors.length > 0) parts.push(`Con error: ${r.errors.length}`)
      setMsg({ type: 'success', text: parts.filter(Boolean).join(' · ') })
      load()
    } catch (e) {
      setMsg({ type: 'error', text: e.message })
    } finally {
      setBusy(false)
    }
  }

  const accountOptions = accounts.filter((a) => a.account && a.account !== '(sin cuenta)')

  return (
    <div>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ margin: 0 }}>Carpeta local</h2>
        <div className="row" style={{ gap: 8 }}>
          <button onClick={openFolder} title="Abrir la carpeta en el Explorador de Windows">Abrir carpeta</button>
          <button onClick={load} disabled={busy || uploading}>Refrescar</button>
        </div>
      </div>

      {msg && <div className={`alert ${msg.type === 'error' ? 'error' : 'success'}`} style={{ marginTop: 12 }}>{msg.text}</div>}

      <div
        className={dragOver ? 'dropzone active' : 'dropzone'}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        onClick={() => fileInputRef.current && fileInputRef.current.click()}
        style={{ marginTop: 14 }}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.xml,.zip,.rar,.7z"
          style={{ display: 'none' }}
          onChange={(e) => { uploadFiles(e.target.files); e.target.value = '' }}
        />
        <div>
          <b>{uploading ? 'Subiendo…' : 'Arrastra tus archivos aquí'}</b>
          <div className="muted" style={{ marginTop: 4 }}>
            o haz clic para elegir. PDF, XML, ZIP, RAR o 7Z — se guardan en la carpeta local sin procesarlos.
          </div>
        </div>
      </div>

      <p className="muted" style={{ fontSize: 12, marginTop: 10 }}>
        Ruta en tu PC: <code>{windowsPath || 'C:\\Users\\cjuan\\Downloads\\OpenOrganizador\\data\\local-scan\\'}</code>
      </p>

      <div className="panel" style={{ marginTop: 14 }}>
        <div className="row" style={{ alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
          <div className="field">
            <label>Cuenta destino</label>
            <select
              style={{ width: 260 }}
              value={useCustom ? '' : targetAccount}
              disabled={useCustom}
              onChange={(e) => setTargetAccount(e.target.value)}
            >
              <option value="">(sin cuenta)</option>
              {accountOptions.map((a) => (
                <option key={a.account} value={a.account}>{a.account}{a.current ? ' (activa)' : ''}</option>
              ))}
            </select>
          </div>
          <label className="row" style={{ alignItems: 'center', gap: 6 }}>
            <input type="checkbox" checked={useCustom} onChange={(e) => setUseCustom(e.target.checked)} />
            Cuenta aparte
          </label>
          {useCustom && (
            <input
              placeholder="nueva.cuenta@email.com"
              value={customAccount}
              onChange={(e) => setCustomAccount(e.target.value)}
              style={{ width: 240 }}
            />
          )}
          <button className="primary" disabled={busy || selected.size === 0} onClick={processSelected}>
            {busy ? 'Procesando…' : `Procesar ${selected.size ? selected.size : ''} seleccionados`}
          </button>
        </div>
      </div>

      {items.length === 0 ? (
        <p className="muted" style={{ marginTop: 20 }}>
          La carpeta está vacía. Arrastra aquí tus PDF, XML o ZIP, o cópialos a la ruta indicada.
        </p>
      ) : (
        <div style={{ marginTop: 14, overflowX: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th style={{ width: 34 }}>
                  <input type="checkbox" checked={allVisible} onChange={toggleAll} />
                </th>
                <th>Archivo</th>
                <th>Tipo</th>
                <th>Tamaño</th>
                <th>Modificado</th>
                <th>Contenido ZIP</th>
                <th>Estado</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {items.map((it) => (
                <tr key={it.name} className={it.already ? 'muted' : ''}>
                  <td>
                    <input type="checkbox" checked={selected.has(it.name)} onChange={() => toggle(it.name)} />
                  </td>
                  <td>{it.name}</td>
                  <td><span className="badge doc-type">{it.ext.replace('.', '').toUpperCase()}</span></td>
                  <td>{fmtSize(it.size)}</td>
                  <td>{fmtDate(it.mtime)}</td>
                  <td>
                    {it.zip_members === null ? '-' :
                      it.zip_members === -1 ? 'requiere contraseña' :
                      it.zip_members === -2 ? 'no se pudo abrir' :
                      `${it.zip_members} archivo(s)`}
                  </td>
                  <td>{it.already ? 'ya registrado' : 'nuevo'}</td>
                  <td>
                    <a href={api.localFolderDownload(it.name)} download>Descargar</a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
