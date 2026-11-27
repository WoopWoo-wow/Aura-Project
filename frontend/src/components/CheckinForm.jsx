import { useState } from 'react'

const FIELDS = [
  { name: 'sleep_duration', label: 'Sleep duration', unit: 'hrs', min: 0, max: 14, step: 0.5 },
  { name: 'sleep_quality', label: 'Sleep quality (1 to 10)', unit: '/10', min: 1, max: 10, step: 1 },
  { name: 'study_hours', label: 'Study hours', unit: 'hrs', min: 0, max: 16, step: 0.5 },
  { name: 'screen_time', label: 'Screen time', unit: 'hrs', min: 0, max: 16, step: 0.5 },
  { name: 'caffeine_intake', label: 'Caffeine (cups)', unit: 'cups', min: 0, max: 10, step: 1 },
]

export default function CheckinForm({ onSubmit, busy }) {
  const [values, setValues] = useState({
    sleep_duration: 6.5,
    sleep_quality: 6,
    study_hours: 5,
    screen_time: 4.5,
    caffeine_intake: 2,
  })

  function handleSubmit(e) {
    e.preventDefault()
    // sliders give strings, the backend wants numbers
    const data = {}
    for (const f of FIELDS) data[f.name] = Number(values[f.name])
    onSubmit(data)
  }

  return (
    <form className="card" onSubmit={handleSubmit}>
      <h3>Daily check-in</h3>
      {FIELDS.map((f) => (
        <label key={f.name} className="slider">
          <span>
            {f.label}: <strong>{values[f.name]} {f.unit}</strong>
          </span>
          <input
            type="range"
            min={f.min}
            max={f.max}
            step={f.step}
            value={values[f.name]}
            onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
          />
        </label>
      ))}
      <button type="submit" disabled={busy}>
        {busy ? 'Analyzing...' : 'Analyze my day'}
      </button>
    </form>
  )
}
