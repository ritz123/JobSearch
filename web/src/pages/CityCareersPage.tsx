import { useEffect, useState } from 'react'
import {
  fetchCityRuns,
  fetchCompanies,
  fetchJobs,
  fetchOllamaModels,
  runCityPipeline,
  type Job,
} from '../api'

export default function CityCareersPage() {
  const [ollamaUrl, setOllamaUrl] = useState('http://127.0.0.1:11434')
  const [models, setModels] = useState<string[]>([])
  const [model, setModel] = useState('llama3.2')
  const [ollamaMsg, setOllamaMsg] = useState('Click Refresh models to connect.')
  const [ollamaErr, setOllamaErr] = useState('')

  const [city, setCity] = useState('')
  const [preset, setPreset] = useState('tech_corporate')
  const [maxCompanies, setMaxCompanies] = useState(15)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const [companies, setCompanies] = useState<Record<string, unknown>[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
  const [runs, setRuns] = useState<Record<string, unknown>[]>([])
  const [browseDays, setBrowseDays] = useState(14)

  const reloadTables = async () => {
    const [c, j, r] = await Promise.all([
      fetchCompanies(),
      fetchJobs({
        source: 'company_site',
        scraped_within_days: browseDays,
        limit: 200,
      }),
      fetchCityRuns(),
    ])
    setCompanies(c.companies)
    setJobs(j.jobs)
    setRuns(r.runs)
  }

  useEffect(() => {
    void reloadTables().catch(() => undefined)
  }, [browseDays])

  const refreshModels = async () => {
    setOllamaErr('')
    setOllamaMsg('Connecting…')
    try {
      const data = await fetchOllamaModels(ollamaUrl)
      setModels(data.models)
      if (data.models.length) {
        setModel((m) => (data.models.includes(m) ? m : data.models[0]))
        setOllamaMsg(`Connected — ${data.models.length} model(s).`)
      } else {
        setOllamaMsg('Ollama is up but has no models. Run ollama pull llama3.2')
      }
    } catch (e) {
      setModels([])
      setOllamaMsg('')
      setOllamaErr(e instanceof Error ? e.message : String(e))
    }
  }

  const onRun = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const summary = await runCityPipeline({
        city,
        preset,
        max_companies: maxCompanies,
        ollama_base_url: ollamaUrl,
        ollama_model: model,
      })
      setMessage(
        `Run #${summary.run_id} — ${summary.status}: ${summary.companies_found} companies, ${summary.jobs_found} jobs.`,
      )
      await reloadTables()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page">
      <h1>City Careers</h1>
      <p className="muted">
        OSM companies → careers pages → Ollama extract → SQLite (runs on the API server).
      </p>

      <section className="card">
        <h2>Ollama</h2>
        <div className="row">
          <label className="grow">
            Base URL
            <input value={ollamaUrl} onChange={(e) => setOllamaUrl(e.target.value)} />
          </label>
          <button type="button" onClick={() => void refreshModels()}>
            Refresh models
          </button>
        </div>
        {ollamaMsg && <p className="success">{ollamaMsg}</p>}
        {ollamaErr && <p className="error">{ollamaErr}</p>}
        <label>
          Model
          <select value={model} onChange={(e) => setModel(e.target.value)}>
            {(models.length ? models : [model]).map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>
      </section>

      <form className="card form-grid" onSubmit={onRun}>
        <label>
          City *
          <input required value={city} onChange={(e) => setCity(e.target.value)} />
        </label>
        <label>
          Filter preset
          <select value={preset} onChange={(e) => setPreset(e.target.value)}>
            <option value="tech_corporate">tech_corporate</option>
            <option value="seo_marketing">seo_marketing (SEO / digital marketing)</option>
            <option value="broad_with_website">broad_with_website</option>
          </select>
        </label>
        <label>
          Max companies
          <input
            type="number"
            min={5}
            max={50}
            step={5}
            value={maxCompanies}
            onChange={(e) => setMaxCompanies(Number(e.target.value))}
          />
        </label>
        <button type="submit" disabled={busy}>
          {busy ? 'Running…' : 'Start city run'}
        </button>
      </form>

      {message && <p className="success">{message}</p>}
      {error && <p className="error">{error}</p>}

      <label>
        Browse jobs seen in last N days
        <input
          type="number"
          min={1}
          max={365}
          value={browseDays}
          onChange={(e) => setBrowseDays(Number(e.target.value))}
        />
      </label>

      <h2>Companies</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Website</th>
              <th>Careers</th>
              <th>City</th>
            </tr>
          </thead>
          <tbody>
            {companies.map((c) => (
              <tr key={String(c.id)}>
                <td>{String(c.name ?? '')}</td>
                <td>{String(c.website ?? '')}</td>
                <td>{String(c.careers_url ?? '')}</td>
                <td>{String(c.city ?? '')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2>Recent company-site jobs</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Title</th>
              <th>Company</th>
              <th>Location</th>
              <th>Scraped</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((j) => (
              <tr key={String(j.id ?? j.job_id)}>
                <td>{String(j.title ?? '')}</td>
                <td>{String(j.company ?? '')}</td>
                <td>{String(j.location ?? '')}</td>
                <td>{String(j.scraped_at ?? '')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2>Past city runs</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>City</th>
              <th>Status</th>
              <th>Companies</th>
              <th>Jobs</th>
              <th>When</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={String(r.id)}>
                <td>{String(r.id)}</td>
                <td>{String(r.city ?? '')}</td>
                <td>{String(r.status ?? '')}</td>
                <td>{String(r.companies_found ?? '')}</td>
                <td>{String(r.jobs_found ?? '')}</td>
                <td>{String(r.ran_at ?? '')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
