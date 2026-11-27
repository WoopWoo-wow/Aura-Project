import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, clearToken, getToken, setToken, setUnauthorizedHandler } from '../api/client.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  // if a token is already saved we must check it before deciding who is logged in
  const [loading, setLoading] = useState(Boolean(getToken()))

  const logout = useCallback(() => {
    clearToken()
    setUser(null)
  }, [])

  useEffect(() => {
    setUnauthorizedHandler(logout)
  }, [logout])

  useEffect(() => {
    if (!getToken()) return
    api
      .me()
      .then(setUser)
      .catch(() => logout())
      .finally(() => setLoading(false))
  }, [logout])

  async function finishLogin(token) {
    setToken(token)
    try {
      setUser(await api.me())
    } catch (err) {
      clearToken()
      throw err
    }
  }

  async function login(username, password) {
    const data = await api.login({ username, password })
    await finishLogin(data.access_token)
  }

  async function register(form) {
    const data = await api.register(form)
    await finishLogin(data.access_token)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
