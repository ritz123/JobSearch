/** Format ISO published_at as relative age for the UI. */
export function formatPublishedAgo(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'Unknown'
  const text = String(value).trim()
  const parsed = Date.parse(text)
  if (Number.isNaN(parsed)) return 'Unknown'

  const ageSec = Math.max(0, (Date.now() - parsed) / 1000)
  if (ageSec < 60) return 'just now'
  const minutes = Math.floor(ageSec / 60)
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? '' : 's'} ago`
  const hours = Math.floor(ageSec / 3600)
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`
  const days = Math.floor(ageSec / 86400)
  if (days < 14) return `${days} day${days === 1 ? '' : 's'} ago`
  const weeks = Math.floor(days / 7)
  if (weeks < 8) return `${weeks} week${weeks === 1 ? '' : 's'} ago`
  const months = Math.max(1, Math.floor(days / 30))
  if (months < 24) return `${months} month${months === 1 ? '' : 's'} ago`
  const years = Math.max(1, Math.floor(days / 365))
  return `${years} year${years === 1 ? '' : 's'} ago`
}
