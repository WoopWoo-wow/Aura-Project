export default function RiskCard({ result }) {
  if (!result) {
    return (
      <div className="card">
        <h3>Burnout risk</h3>
        <p className="muted">Waiting for your check-in.</p>
      </div>
    )
  }

  const probs = result.risk_probabilities || {}
  const rows = ['Low', 'Moderate', 'High']

  return (
    <div className="card">
      <div className="row-between">
        <h3>Burnout risk</h3>
        <span className={'pill risk-' + result.risk_label.toLowerCase()}>{result.risk_label}</span>
      </div>

      {rows.map((label) => {
        const pct = Math.round((probs[label] || 0) * 100)
        return (
          <div key={label} className="bar-row">
            <div className="row-between small">
              <span>{label}</span>
              <span>{pct}%</span>
            </div>
            <div className="bar">
              <div className={'bar-fill fill-' + label.toLowerCase()} style={{ width: pct + '%' }} />
            </div>
          </div>
        )
      })}

      <p className="muted small">
        Davao City: {result.temperature_c} C {result.weather_live ? '(live)' : '(default, no live weather)'}
      </p>
    </div>
  )
}
