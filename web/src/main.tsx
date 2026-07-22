import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import App from './App'
import CityCareersPage from './pages/CityCareersPage'
import JobsPage from './pages/JobsPage'
import ScraperPage from './pages/ScraperPage'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<App />}>
          <Route path="/" element={<JobsPage />} />
          <Route path="/scraper" element={<ScraperPage />} />
          <Route path="/city-careers" element={<CityCareersPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
