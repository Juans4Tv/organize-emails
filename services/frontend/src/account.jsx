import { createContext, useContext, useEffect, useState } from 'react'
import { api } from './api.js'

const AccountContext = createContext({ accounts: [], activeAccount: '' })
const STORAGE_KEY = 'oo_account'

export function AccountProvider({ children }) {
  const [accounts, setAccounts] = useState([])
  const [activeAccount, setActiveAccountState] = useState(
    () => localStorage.getItem(STORAGE_KEY) || ''
  )

  const refreshAccounts = () => api.accounts().then(setAccounts).catch(() => {})

  useEffect(() => { refreshAccounts() }, [])

  useEffect(() => {
    if (activeAccount && accounts.length > 0 &&
        !accounts.some((a) => a.account === activeAccount)) {
      setActiveAccountState('')
      localStorage.removeItem(STORAGE_KEY)
    }
  }, [accounts, activeAccount])

  const setActiveAccount = (value) => {
    setActiveAccountState(value)
    if (value) localStorage.setItem(STORAGE_KEY, value)
    else localStorage.removeItem(STORAGE_KEY)
  }

  return (
    <AccountContext.Provider value={{ accounts, activeAccount, setActiveAccount, refreshAccounts }}>
      {children}
    </AccountContext.Provider>
  )
}

export function useAccount() {
  return useContext(AccountContext)
}
