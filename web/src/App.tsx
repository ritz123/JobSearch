import { Link, NavLink, Outlet } from 'react-router-dom'
import './App.css'

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">
          JobSearch
        </Link>
        <nav>
          <NavLink to="/" end>
            Jobs
          </NavLink>
          <NavLink to="/scraper">Run Scraper</NavLink>
          <NavLink to="/city-careers">City Careers</NavLink>
        </nav>
      </header>
      <main className="main">
        <Outlet />
      </main>
    </div>
  )
}
