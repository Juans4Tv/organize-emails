async function request(path, options = {}) {
  const resp = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options
  })
  if (!resp.ok) {
    let detail = resp.statusText
    try {
      const body = await resp.json()
      detail = body.detail || JSON.stringify(body)
    } catch { /* sin cuerpo */ }
    throw new Error(detail)
  }
  return resp.json()
}

export const api = {
  getSettings: () => request('/settings'),
  saveSettings: (data) => request('/settings', { method: 'PUT', body: JSON.stringify(data) }),
  testConnection: () => request('/test-connection', { method: 'POST' }),
  startSync: (since, before) => request('/sync', { method: 'POST', body: JSON.stringify({ since, before: before || null }) }),
  latestJob: (kind) => request(`/jobs/latest?kind=${encodeURIComponent(kind || 'email_sync')}`),
  job: (id) => request(`/jobs/${id}`),
  scanInbox: () => request('/inbox/scan', { method: 'POST' }),
  localFolderList: () => request('/local-folder/list'),
  localFolderProcess: (files, account) => request('/local-folder/process', { method: 'POST', body: JSON.stringify({ files, account }) }),
  localFolderOpen: () => request('/local-folder/open'),
  localFolderUpload: (file) => {
    const form = new FormData()
    form.append('file', file)
    return fetch('/api/local-folder/upload', { method: 'POST', body: form }).then(async (resp) => {
      if (!resp.ok) {
        let detail = resp.statusText
        try { detail = (await resp.json()).detail || detail } catch { /* */ }
        throw new Error(detail)
      }
      return resp.json()
    })
  },
  localFolderDownload: (name) => `/api/local-folder/download/${encodeURIComponent(name)}`,
  places: () => request('/places'),
  accounts: () => request('/accounts'),
  documents: (params) => request(`/documents?${new URLSearchParams(params)}`),
  patchDocument: (id, data) => request(`/documents/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  relatedDocument: (id) => request(`/documents/${id}/related`),
  deleteDocument: (id) => request(`/documents/${id}`, { method: 'DELETE' }),
  deleteBulk: (ids) => request('/documents/delete-bulk', { method: 'POST', body: JSON.stringify({ ids }) }),
  bulkVerify: (ids) => request('/documents/bulk-verify', { method: 'POST', body: JSON.stringify({ ids }) }),
  dashboard: (params) => request(`/dashboard${params ? `?${new URLSearchParams(params)}` : ''}`)
}
