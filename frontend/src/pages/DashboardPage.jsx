import { useEffect, useState } from 'react'
import { api } from '../api/client.js'
import { useAuth } from '../context/AuthContext.jsx'
import AuraCard from '../components/AuraCard.jsx'
import CheckinForm from '../components/CheckinForm.jsx'
import HistoryList from '../components/HistoryList.jsx'
import RiskCard from '../components/RiskCard.jsx'

export default function DashboardPage() {
  const { user, logout } = useAuth()
  const [dash, setDash] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api
      .dashboard()
      .then(setDash)
      .catch((err) => setError(err.message))
  }, [])

  async function handleCheckin(data) {
    setBusy(true)
    setError('')
    try {
      const res = await api.checkin(data)
      setResult(res)
      setDash(res.dashboard)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  // after a check-in show AURA's reaction to the result, otherwise her daily line
  const message = result ? result.aura_message : dash?.companion_message

  return (
    <div className="page">
      <header className="topbar">
        <h1>AURA</h1>
        <div className="topbar-right">
          <span>Hi, {user.display_name || user.username}</span>
          <button className="secondary" onClick={logout}>
            Log out
          </button>
        </div>
      </header>

      {error && <p className="error">{error}</p>}

      <div className="grid">
        <div>
          <AuraCard
            mood={dash?.current_mood_state}
            message={message}
            points={dash?.affection_points}
          />
          <RiskCard result={result} />
        </div>
        <div>
          <CheckinForm onSubmit={handleCheckin} busy={busy} />
          <HistoryList history={dash?.history} />
        </div>
      </div>
    </div>
  )
}
