import { useCallback, useEffect, useState } from 'react'
import {
  downloadJobsXlsx,
  fetchJobs,
  fetchStats,
  purgeOldJobs,
  type Job,
  type Stats,
} from '../api'
import { formatPublishedAgo } from '../dates'

const emptyFilters = {
  keyword: '',
  company: '',
  location: '',
  workplace: 'All',
  source: 'All',
  posted_within: '',
  limit: 100,
}

type Filters = typeof emptyFilters

function exportParams(f: Filters) {
  return {
    keyword: f.keyword,
    company: f.company,
    location: f.location,
    workplace: f.workplace === 'All' ? undefined : f.workplace,
    source: f.source === 'All' ? undefined : f.source,
    posted_within: f.posted_within || undefined,
    // Export the filtered set generously (not capped by table Max alone).
    limit: Math.max(f.limit, 2000),
  }
}

export default function JobsPage() {
  const [draft, setDraft] = useState(emptyFilters)
  const [filters, setFilters] = useState(emptyFilters)
  const [jobs, setJobs] = useState<Job[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)
  const [purging, setPurging] = useState(false)
  const [downloading, setDownloading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [j, s] = await Promise.all([
        fetchJobs({
          keyword: filters.keyword,
          company: filters.company,
          location: filters.location,
          workplace: filters.workplace === 'All' ? undefined : filters.workplace,
          source: filters.source === 'All' ? undefined : filters.source,
          posted_within: filters.posted_within || undefined,
          limit: filters.limit,
        }),
        fetchStats(),
      ])
      setJobs(j.jobs)
      setStats(s)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [filters])

  useEffect(() => {
    void load()
  }, [load])

  const onPurge = async () => {
    const ok = window.confirm(
      'Delete all jobs posted more than 7 days ago? This cannot be undone.',
    )
    if (!ok) return
    setPurging(true)
    setMessage('')
    setError('')
    try {
      const result = await purgeOldJobs(7)
      setMessage(`Deleted ${result.deleted} job(s) older than ${result.older_than_days} days.`)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setPurging(false)
    }
  }

  const onDownloadXlsx = async () => {
    // Use the form values currently on screen (apply them to the table too).
    setFilters(draft)
    setDownloading(true)
    setError('')
    setMessage('')
    try {
      await downloadJobsXlsx(exportParams(draft), 'jobs_filtered.xlsx')
      setMessage('Downloaded filtered jobs as Excel (.xlsx).')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="page">
      <h1>Jobs Explorer</h1>
      <p className="muted">Browse jobs stored in the local SQLite database.</p>

      <div className="row" style={{ marginBottom: '0.75rem', gap: '0.5rem' }}>
        <button type="button" onClick={() => void onPurge()} disabled={purging}>
          {purging ? 'Cleaning…' : 'Delete jobs older than 1 week'}
        </button>
      </div>

      <form
        className="card filters"
        onSubmit={(e) => {
          e.preventDefault()
          setFilters({ ...draft })
        }}
      >
        <label>
          Keyword
          <input
            value={draft.keyword}
            onChange={(e) => setDraft({ ...draft, keyword: e.target.value })}
          />
        </label>
        <label>
          Company
          <input
            value={draft.company}
            onChange={(e) => setDraft({ ...draft, company: e.target.value })}
          />
        </label>
        <label>
          Location
          <input
            value={draft.location}
            onChange={(e) => setDraft({ ...draft, location: e.target.value })}
          />
        </label>
        <label>
          Workplace
          <select
            value={draft.workplace}
            onChange={(e) => setDraft({ ...draft, workplace: e.target.value })}
          >
            <option>All</option>
            <option>Remote</option>
            <option>On-site</option>
            <option>Hybrid</option>
          </select>
        </label>
        <label>
          Source
          <select
            value={draft.source}
            onChange={(e) => setDraft({ ...draft, source: e.target.value })}
          >
            <option>All</option>
            <option value="linkedin">linkedin</option>
            <option value="naukri">naukri</option>
            <option value="indeed">indeed</option>
            <option value="shine">shine</option>
            <option value="company_site">company_site</option>
          </select>
        </label>
        <label>
          Posted
          <select
            value={draft.posted_within}
            onChange={(e) => setDraft({ ...draft, posted_within: e.target.value })}
          >
            <option value="">Any</option>
            <option value="24h">Past 24 hours</option>
            <option value="3d">Past 3 days</option>
            <option value="week">Past week</option>
            <option value="month">Past month</option>
          </select>
        </label>
        <label>
          Max
          <input
            type="number"
            min={1}
            max={500}
            value={draft.limit}
            onChange={(e) => setDraft({ ...draft, limit: Number(e.target.value) })}
          />
        </label>
        <button type="submit">Apply Filters</button>
        <button
          type="button"
          onClick={() => void onDownloadXlsx()}
          disabled={downloading}
        >
          {downloading ? 'Downloading…' : 'Download .xlsx'}
        </button>
      </form>

      {error && <p className="error">{error}</p>}
      {message && <p className="success">{message}</p>}
      {stats && (
        <div className="stats">
          <div className="stat">
            <strong>{stats.total_jobs}</strong>
            <span>Jobs</span>
          </div>
          <div className="stat">
            <strong>{stats.total_searches}</strong>
            <span>Searches</span>
          </div>
        </div>
      )}

      {loading ? (
        <p>Loading…</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Source</th>
                <th>Title</th>
                <th>Company</th>
                <th>Location</th>
                <th>Published</th>
                <th>Link</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={String(j.id ?? j.job_id)}>
                  <td>{String(j.source ?? '')}</td>
                  <td>{String(j.title ?? '')}</td>
                  <td>{String(j.company ?? '')}</td>
                  <td>{String(j.location ?? '')}</td>
                  <td title={String(j.published_at ?? '')}>
                    {String(j.published_ago ?? formatPublishedAgo(j.published_at))}
                  </td>
                  <td>
                    {j.job_url ? (
                      <a href={String(j.job_url)} target="_blank" rel="noreferrer">
                        Open
                      </a>
                    ) : (
                      '—'
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!jobs.length && <p className="muted">No jobs match these filters.</p>}
        </div>
      )}
    </div>
  )
}
