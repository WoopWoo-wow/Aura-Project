// Same thresholds as the backend (cold 0-4, neutral 5-14, warm 15+).
export function tierFor(points) {
  if (points <= 4) return 'Cold'
  if (points <= 14) return 'Neutral'
  return 'Warm'
}

export const MOODS = {
  flustered_praise: { face: '😳', label: 'flustered' },
  neutral: { face: '😒', label: 'neutral' },
  worried: { face: '😟', label: 'worried' },
  annoyed: { face: '😤', label: 'annoyed' },
  strict: { face: '💢', label: 'strict' },
}
