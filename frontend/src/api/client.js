// All talking to the backend happens in this one file.
// Change VITE_API_URL in .env to point at a deployed backend.
const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'
const TOKEN_KEY = 'aura_token'

export const getToken = () => localStorage.getItem(TOKEN_KEY)
export const setToken = (token) => localStorage.setItem(TOKEN_KEY, token)
export const clearToken = () => localStorage.removeItem(TOKEN_KEY)

// AuthContext registers a function here so an expired token logs the user out.
let onUnauthorized = () => {}
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn
}

function errorMessage(data, status) {
  if (data && typeof data.detail === 'string') return data.detail
  if (data && Array.isArray(data.detail)) {
    // validation errors (422) come as a list
    return data.detail.map((d) => (d.loc || []).slice(1).join('.') + ': ' + d.msg).join('; ')
  }
  return 'Request failed (' + status + ')'
}

async function request(path, { method = 'GET', body, auth = true } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  const token = getToken()
  if (auth && token) headers.Authorization = 'Bearer ' + token

  let res
  try {
    res = await fetch(API_URL + path, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new Error('Cannot reach the server. Is the backend running?')
  }

  let data = null
  try {
    data = await res.json()
  } catch {
    // empty or non-JSON body
  }

  if (auth && (res.status === 401 || res.status === 403)) onUnauthorized()
  if (!res.ok) throw new Error(errorMessage(data, res.status))
  return data
}

export const api = {
  // accounts
  register: (body) => request('/api/auth/register', { method: 'POST', body, auth: false }),
  login: (body) => request('/api/auth/login', { method: 'POST', body, auth: false }),
  me: () => request('/api/me'),
  // daily use
  dashboard: () => request('/api/dashboard'),
  checkin: (body) => request('/api/checkin', { method: 'POST', body }),
  // smart features (UI for these comes later)
  predict: (body) => request('/api/predict', { method: 'POST', body }),
  whatif: (body) => request('/api/whatif', { method: 'POST', body }),
  recovery: () => request('/api/recovery'),
  insights: () => request('/api/insights'),
}
