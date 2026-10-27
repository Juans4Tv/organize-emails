import { createContext, useCallback, useContext, useState } from 'react'

const ConfirmContext = createContext(() => Promise.resolve(false))

export function ConfirmProvider({ children }) {
  const [state, setState] = useState(null)

  const confirm = useCallback((opts) => new Promise((resolve) => {
    setState(typeof opts === 'string'
      ? { message: opts, resolve }
      : { ...opts, resolve })
  }), [])

  const close = (ok) => {
    if (state) state.resolve(ok)
    setState(null)
  }

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {state && (
        <div className="modal-overlay" onClick={() => close(false)}>
          <div className="modal confirm-modal" onClick={(e) => e.stopPropagation()}>
            <h3>{state.title || 'Confirmar acción'}</h3>
            <p>{state.message}</p>
            <div className="confirm-actions">
              <button onClick={() => close(false)}>Cancelar</button>
              <button
                className={state.danger ? 'danger' : 'primary'}
                onClick={() => close(true)}
              >
                {state.confirmText || 'Confirmar'}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  )
}

export function useConfirm() {
  return useContext(ConfirmContext)
}
