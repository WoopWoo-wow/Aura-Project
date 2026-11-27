// Simple table for now. A chart (Chart.js or Recharts) can replace this later.
export default function HistoryList({ history }) {
  if (!history || history.length === 0) {
    return (
      <div className="card">
        <h3>Last 7 days</h3>
        <p className="muted">No check-ins yet.</p>
      </div>
    )
  }

  return (
    <div className="card">
      <h3>Last 7 days</h3>
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Sleep (h)</th>
            <th>Sleep debt (h)</th>
          </tr>
        </thead>
        <tbody>
          {history.map((h) => (
            <tr key={h.log_date}>
              <td>{h.log_date}</td>
              <td>{h.hours_slept}</td>
              <td>{h.calculated_sleep_debt}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
