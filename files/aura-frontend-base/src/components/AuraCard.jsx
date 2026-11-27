import { MOODS, tierFor } from '../utils/affection.js'

export default function AuraCard({ mood, message, points }) {
  const cfg = MOODS[mood] || MOODS.neutral
  const safePoints = points ?? 0

  return (
    <div className="card aura-card">
      <div className="aura-top">
        <div className="aura-face">{cfg.face}</div>
        <div>
          <h2>AURA</h2>
          <span className="pill">{cfg.label}</span>
          <p className="muted small">
            Affection: <strong>{safePoints} pts</strong> ({tierFor(safePoints)})
          </p>
        </div>
      </div>
      <div className="bubble">
        <p>{message || 'Hmph. Log your day so I can see how badly you are doing.'}</p>
      </div>
    </div>
  )
}
