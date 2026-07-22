const JSON_HEADERS = { 'Content-Type': 'application/json' }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = (data as { detail?: string }).detail || res.statusText
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return data as T
}

export type Job = Record<string, unknown>
export type Stats = {
  total_jobs: number
  total_searches: number
  top_companies: { company: string; n: number }[]
  top_locations: { location: string; n: number }[]
  workplace_distribution: { workplace_type: string; n: number }[]
  recent_searches: Record<string, unknown>[]
}

export function fetchJobs(params: Record<string, string | number | undefined>) {
  const q = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== '' && v !== 'All') q.set(k, String(v))
  })
  return request<{ jobs: Job[] }>(`/api/jobs?${q}`)
}

export function fetchStats() {
  return request<Stats>('/api/stats')
}

export function fetchSearches() {
  return request<{ searches: Record<string, unknown>[] }>('/api/searches')
}

export function runScrape(body: Record<string, unknown>) {
  return request<{ fetched: number }>('/api/scrape', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  })
}

export function fetchOllamaModels(baseUrl: string) {
  const q = new URLSearchParams({ base_url: baseUrl })
  return request<{ ok: boolean; models: string[] }>(`/api/ollama/models?${q}`)
}

export function runCityPipeline(body: Record<string, unknown>) {
  return request<Record<string, unknown>>('/api/city-runs', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  })
}

export function fetchCityRuns() {
  return request<{ runs: Record<string, unknown>[] }>('/api/city-runs')
}

export function fetchCompanies(city?: string) {
  const q = new URLSearchParams()
  if (city) q.set('city', city)
  return request<{ companies: Record<string, unknown>[] }>(`/api/companies?${q}`)
}

export function purgeOldJobs(olderThanDays = 7) {
  return request<{ deleted: number; older_than_days: number }>('/api/jobs/purge', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ older_than_days: olderThanDays }),
  })
}

export function jobsExportUrl(params: Record<string, string | number | undefined>) {
  const q = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== '' && v !== 'All') q.set(k, String(v))
  })
  const qs = q.toString()
  return qs ? `/api/jobs/export.xlsx?${qs}` : '/api/jobs/export.xlsx'
}

/** Fetch filtered jobs as Excel (.xlsx) and trigger a browser download. */
export async function downloadJobsXlsx(
  params: Record<string, string | number | undefined>,
  filename = 'jobs_filtered.xlsx',
) {
  const url = jobsExportUrl(params)
  const res = await fetch(url)
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    const detail = (data as { detail?: string }).detail || res.statusText
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  const blob = await res.blob()
  const objectUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = objectUrl
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(objectUrl)
}
