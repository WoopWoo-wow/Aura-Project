import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'

export default function RegisterPage() {
  const { user, register } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({
    username: '',
    password: '',
    display_name: '',
    target_sleep_hours: 8,
    worst_habit: 'all-nighters',
  })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to="/" replace />

  function update(field, value) {
    setForm((f) => ({ ...f, [field]: value }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await register({ ...form, target_sleep_hours: Number(form.target_sleep_hours) })
      navigate('/')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-wrap">
      <form className="card auth-card" onSubmit={handleSubmit}>
        <h1>New here?</h1>
        <p className="muted">Tell me the basics so I can track your terrible sleep.</p>

        <label>
          What should I call you?
          <input
            value={form.display_name}
            onChange={(e) => update('display_name', e.target.value)}
            maxLength={40}
            required
          />
        </label>
        <label>
          Username (3 to 30 characters)
          <input
            value={form.username}
            onChange={(e) => update('username', e.target.value)}
            minLength={3}
            maxLength={30}
            required
          />
        </label>
        <label>
          Password (at least 8 characters)
          <input
            type="password"
            value={form.password}
            onChange={(e) => update('password', e.target.value)}
            minLength={8}
            maxLength={72}
            required
          />
        </label>
        <label>
          Daily sleep target: <strong>{Number(form.target_sleep_hours).toFixed(1)} hours</strong>
          <input
            type="range"
            min="6"
            max="10"
            step="0.5"
            value={form.target_sleep_hours}
            onChange={(e) => update('target_sleep_hours', e.target.value)}
          />
        </label>
        <label>
          Your worst study habit
          <select value={form.worst_habit} onChange={(e) => update('worst_habit', e.target.value)}>
            <option value="all-nighters">Last-minute all-nighters</option>
            <option value="caffeine">Replacing sleep with coffee</option>
            <option value="scrolling">Scrolling in bed until 3 AM</option>
          </select>
        </label>

        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={busy}>
          {busy ? 'Creating...' : 'Start tracking'}
        </button>
        <p className="muted small">
          Already have an account? <Link to="/login">Log in</Link>
        </p>
      </form>
    </div>
  )
}
