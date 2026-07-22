import { useEffect, useState } from 'react'
import { fetchSearches, runScrape } from '../api'

type ScraperForm = {
  source: string
  keywords: string
  location: string
  country: string
  max_jobs: number
  workplace: string
  job_type: string
  date_posted: string
  experience: string
  company: string
  details: boolean
  sort_recent: boolean
}

const DEFAULT_FORM: ScraperForm = {
  source: 'linkedin',
  keywords: '',
  location: '',
  country: 'in',
  max_jobs: 25,
  workplace: 'Any',
  job_type: 'Any',
  date_posted: 'any',
  experience: 'Any',
  company: '',
  details: false,
  sort_recent: false,
}

function clampMaxJobs(value: unknown): number {
  const n = Number(value)
  if (!Number.isFinite(n)) return 25
  const stepped = Math.round(n / 5) * 5
  return Math.max(5, Math.min(200, stepped))
}

function orAny(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'Any'
  return String(value)
}

function searchToForm(search: Record<string, unknown>): ScraperForm {
  const filters =
    search.filters && typeof search.filters === 'object'
      ? (search.filters as Record<string, unknown>)
      : {}

  return {
    source: String(filters.source || 'linkedin'),
    keywords: String(search.keywords || ''),
    location: String(search.location || ''),
    country: String(filters.country || 'in'),
    max_jobs: clampMaxJobs(filters.max_jobs),
    workplace: orAny(filters.workplace),
    job_type: orAny(filters.job_type),
    date_posted: String(filters.date_posted || 'any'),
    experience: orAny(filters.experience),
    company: String(filters.company || ''),
    details: Boolean(filters.details),
    sort_recent: Boolean(filters.sort_recent),
  }
}

function scrapeBody(form: ScraperForm) {
  return {
    ...form,
    workplace: form.workplace === 'Any' ? null : form.workplace,
    job_type: form.job_type === 'Any' ? null : form.job_type,
    experience: form.experience === 'Any' ? null : form.experience,
  }
}

export default function ScraperPage() {
  const [form, setForm] = useState<ScraperForm>(DEFAULT_FORM)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [searches, setSearches] = useState<Record<string, unknown>[]>([])

  const reload = async () => {
    try {
      const data = await fetchSearches()
      setSearches(data.searches)
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    void reload()
  }, [])

  const runWithForm = async (next: ScraperForm, label?: string) => {
    if (!next.keywords.trim() || !next.location.trim()) {
      setError('Keywords and location are required.')
      return
    }
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const result = await runScrape(scrapeBody(next))
      setMessage(
        label
          ? `${label} — fetched ${result.fetched} jobs.`
          : `Fetched ${result.fetched} jobs.`,
      )
      await reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    await runWithForm(form)
  }

  const onLoad = (search: Record<string, unknown>) => {
    const next = searchToForm(search)
    setForm(next)
    setError('')
    setMessage(
      `Loaded search #${search.id} into the form. Review fields, then Start Scraping — or use Rerun.`,
    )
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const onRerun = async (search: Record<string, unknown>) => {
    const next = searchToForm(search)
    setForm(next)
    await runWithForm(next, `Reran search #${search.id}`)
  }

  return (
    <div className="page">
      <h1>Run Scraper</h1>
      <p className="muted">
        Scrape LinkedIn, Naukri, or Indeed via Apify. Load a past search to edit it, or Rerun
        immediately.
      </p>

      <form className="card form-grid" onSubmit={onSubmit}>
        <label>
          Source
          <select
            value={form.source}
            onChange={(e) => setForm({ ...form, source: e.target.value })}
          >
            <option value="linkedin">linkedin</option>
            <option value="naukri">naukri</option>
            <option value="indeed">indeed</option>
          </select>
        </label>
        <label>
          Keywords *
          <input
            required
            value={form.keywords}
            onChange={(e) => setForm({ ...form, keywords: e.target.value })}
          />
        </label>
        <label>
          Location *
          <input
            required
            value={form.location}
            onChange={(e) => setForm({ ...form, location: e.target.value })}
          />
        </label>
        {form.source === 'indeed' && (
          <label>
            Country (Indeed)
            <select
              value={form.country}
              onChange={(e) => setForm({ ...form, country: e.target.value })}
            >
              <option value="in">India (in)</option>
              <option value="us">United States (us)</option>
              <option value="uk">United Kingdom (uk)</option>
              <option value="ca">Canada (ca)</option>
              <option value="au">Australia (au)</option>
              <option value="sg">Singapore (sg)</option>
              <option value="ae">UAE (ae)</option>
              <option value="de">Germany (de)</option>
            </select>
          </label>
        )}
        <label>
          Max jobs
          <input
            type="number"
            min={5}
            max={200}
            step={5}
            value={form.max_jobs}
            onChange={(e) => setForm({ ...form, max_jobs: Number(e.target.value) })}
          />
        </label>
        <label>
          Workplace
          <select
            value={form.workplace}
            onChange={(e) => setForm({ ...form, workplace: e.target.value })}
          >
            <option>Any</option>
            <option value="remote">remote</option>
            <option value="on_site">on_site</option>
            <option value="hybrid">hybrid</option>
          </select>
        </label>
        <label>
          Job type (LinkedIn)
          <select
            value={form.job_type}
            onChange={(e) => setForm({ ...form, job_type: e.target.value })}
          >
            <option>Any</option>
            <option value="full_time">full_time</option>
            <option value="part_time">part_time</option>
            <option value="contract">contract</option>
            <option value="internship">internship</option>
          </select>
        </label>
        <label>
          Date posted
          <select
            value={form.date_posted}
            onChange={(e) => setForm({ ...form, date_posted: e.target.value })}
          >
            <option value="any">any</option>
            <option value="day">day</option>
            <option value="week">week</option>
            <option value="month">month</option>
          </select>
        </label>
        <label>
          Experience (LinkedIn)
          <select
            value={form.experience}
            onChange={(e) => setForm({ ...form, experience: e.target.value })}
          >
            <option>Any</option>
            <option value="internship">internship</option>
            <option value="entry">entry</option>
            <option value="associate">associate</option>
            <option value="mid_senior">mid_senior</option>
            <option value="director">director</option>
            <option value="executive">executive</option>
          </select>
        </label>
        <label>
          Company (LinkedIn)
          <input
            value={form.company}
            onChange={(e) => setForm({ ...form, company: e.target.value })}
          />
        </label>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={form.details}
            onChange={(e) => setForm({ ...form, details: e.target.checked })}
          />
          Fetch full descriptions
        </label>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={form.sort_recent}
            onChange={(e) => setForm({ ...form, sort_recent: e.target.checked })}
          />
          Sort by most recent
        </label>
        <button type="submit" disabled={busy}>
          {busy ? 'Scraping… (may take 1–3 min)' : 'Start Scraping'}
        </button>
      </form>

      {message && <p className="success">{message}</p>}
      {error && <p className="error">{error}</p>}

      <div className="row" style={{ alignItems: 'center', justifyContent: 'space-between' }}>
        <h2>Recent searches</h2>
        <button type="button" onClick={() => void reload()} disabled={busy}>
          Refresh
        </button>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Source</th>
              <th>Keywords</th>
              <th>Location</th>
              <th>Jobs</th>
              <th>When</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {searches.map((s) => {
              const filters =
                s.filters && typeof s.filters === 'object'
                  ? (s.filters as Record<string, unknown>)
                  : {}
              return (
                <tr key={String(s.id)}>
                  <td>{String(s.id)}</td>
                  <td>{String(filters.source || 'linkedin')}</td>
                  <td>{String(s.keywords ?? '')}</td>
                  <td>{String(s.location ?? '')}</td>
                  <td>{String(s.job_count ?? '')}</td>
                  <td>{String(s.ran_at ?? '')}</td>
                  <td>
                    <div className="row" style={{ gap: '0.4rem' }}>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => onLoad(s)}
                      >
                        Load
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void onRerun(s)}
                      >
                        Rerun
                      </button>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {!searches.length && <p className="muted">No past searches yet.</p>}
      </div>
    </div>
  )
}
