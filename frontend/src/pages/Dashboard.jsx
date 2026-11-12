import { useEffect, useMemo, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { api } from '../api'

const DAY = 24 * 60 * 60 * 1000

function startOfToday() {
  const d = new Date()
  d.setHours(0, 0, 0, 0)
  return d
}

// Works out where a trip is in time, using only start_date / end_date
function getTiming(trip) {
  if (!trip.start_date) return { key: 'nodates', label: 'Dates not set', days: null }
  const today = startOfToday().getTime()
  const start = new Date(trip.start_date).setHours(0, 0, 0, 0)
  const end = trip.end_date ? new Date(trip.end_date).setHours(0, 0, 0, 0) : start
  if (today < start) {
    const d = Math.round((start - today) / DAY)
    return { key: 'upcoming', label: d === 1 ? 'Tomorrow' : `In ${d} days`, days: d }
  }
  if (today <= end) return { key: 'ongoing', label: 'In progress', days: 0 }
  return { key: 'completed', label: 'Completed', days: null }
}

function tripLength(trip) {
  if (!trip.start_date || !trip.end_date) return null
  const s = new Date(trip.start_date).setHours(0, 0, 0, 0)
  const e = new Date(trip.end_date).setHours(0, 0, 0, 0)
  return Math.max(Math.round((e - s) / DAY) + 1, 1)
}

function fmtDate(iso) {
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
}

function money(n) {
  return `₹${Number(n || 0).toLocaleString('en-IN')}`
}

const STEPS = [
  { icon: '🧳', title: 'Create or join', text: 'Start a trip with a budget, or join friends with an invite code.' },
  { icon: '❤️', title: 'Add preferences', text: 'Everyone picks interests, pace and must-see places.' },
  { icon: '🧠', title: 'Get the best plan', text: 'The optimizer fits places to your budget and days.' },
  { icon: '🔄', title: 'Re-plan anytime', text: 'Place closed? Re-run it on the remaining budget and days.' },
]

function Dashboard() {
  const [user, setUser] = useState(null)
  const [trips, setTrips] = useState([])
  const [error, setError] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [showJoinForm, setShowJoinForm] = useState(false)
  const [joinCode, setJoinCode] = useState('')
  const [joining, setJoining] = useState(false)

  const [name, setName] = useState('')
  const [destination, setDestination] = useState('')
  const [budget, setBudget] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [creating, setCreating] = useState(false)

  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('all')
  const [sort, setSort] = useState('soonest')
  const [copiedId, setCopiedId] = useState(null)

  const navigate = useNavigate()

  useEffect(() => {
    if (!api.getToken()) {
      navigate('/login')
      return
    }
    loadData()
  }, [])

  async function loadData() {
    try {
      const [meRes, tripsRes] = await Promise.all([api.me(), api.listTrips()])
      setUser(meRes)
      setTrips(tripsRes)
    } catch (err) {
      setError(err.message)
      api.clearToken()
      navigate('/login')
    }
  }

  async function handleCreateTrip(e) {
    e.preventDefault()
    setCreating(true)
    setError('')
    try {
      await api.createTrip({
        name,
        destination,
        total_budget: parseFloat(budget),
        start_date: startDate ? new Date(startDate).toISOString() : null,
        end_date: endDate ? new Date(endDate).toISOString() : null,
      })
      setName('')
      setDestination('')
      setBudget('')
      setStartDate('')
      setEndDate('')
      setShowForm(false)
      loadData()
    } catch (err) {
      setError(err.message)
    } finally {
      setCreating(false)
    }
  }

  function handleLogout() {
    api.clearToken()
    navigate('/login')
  }

  async function handleJoinTrip(e) {
    e.preventDefault()
    setJoining(true)
    setError('')
    try {
      await api.joinTrip(joinCode)
      setJoinCode('')
      setShowJoinForm(false)
      loadData()
    } catch (err) {
      setError(err.message)
    } finally {
      setJoining(false)
    }
  }

  function copyInvite(e, trip) {
    e.preventDefault()
    e.stopPropagation()
    navigator.clipboard?.writeText(trip.invite_code)
    setCopiedId(trip.id)
    setTimeout(() => setCopiedId(null), 1500)
  }

  // Trips with their computed timing, computed once per change
  const enriched = useMemo(
    () => trips.map((t) => ({ ...t, timing: getTiming(t), length: tripLength(t) })),
    [trips]
  )

  const stats = useMemo(() => {
    const upcoming = enriched.filter((t) => t.timing.key === 'upcoming' || t.timing.key === 'ongoing')
    return {
      total: enriched.length,
      upcoming: upcoming.length,
      budget: enriched.reduce((sum, t) => sum + (t.total_budget || 0), 0),
      organizing: user ? enriched.filter((t) => t.created_by === user.id).length : 0,
    }
  }, [enriched, user])

  // The trip to highlight: one in progress, otherwise the soonest upcoming
  const nextTrip = useMemo(() => {
    const live = enriched.find((t) => t.timing.key === 'ongoing')
    if (live) return live
    return enriched
      .filter((t) => t.timing.key === 'upcoming')
      .sort((a, b) => a.timing.days - b.timing.days)[0]
  }, [enriched])

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase()
    let list = enriched.filter((t) => {
      if (filter !== 'all' && t.timing.key !== filter) return false
      if (!q) return true
      return t.name.toLowerCase().includes(q) || t.destination.toLowerCase().includes(q)
    })
    const rank = (t) => (t.timing.days == null ? 9999 : t.timing.days)
    if (sort === 'soonest') list = [...list].sort((a, b) => rank(a) - rank(b))
    if (sort === 'newest') list = [...list].sort((a, b) => b.id - a.id)
    if (sort === 'budget') list = [...list].sort((a, b) => b.total_budget - a.total_budget)
    return list
  }, [enriched, search, filter, sort])

  if (!user) return <div className="dash">Loading...</div>

  const firstName = (user.name || '').split(' ')[0]

  return (
    <div className="dash">
      <div className="dash-header">
        <h1>✈️ TripSync</h1>
        <div className="dash-user">
          <span>Hi, {user.name}</span>
          <Link to="/explore" className="btn-secondary" style={{ textDecoration: 'none' }}>🧭 Explore places</Link>
          <button className="btn-secondary" onClick={handleLogout}>Log out</button>
        </div>
      </div>

      <div className="hero">
        <div>
          <h2 className="hero-title">Welcome back, {firstName} 👋</h2>
          <p className="hero-sub">
            {stats.total === 0
              ? 'Plan your first group trip — one shared budget, one plan everyone agrees on.'
              : 'Plan together, stay on budget, and keep everyone’s interests in the mix.'}
          </p>
        </div>
        {nextTrip && (
          <Link to={`/trips/${nextTrip.id}`} className="next-trip">
            <span className="next-trip-label">
              {nextTrip.timing.key === 'ongoing' ? 'Happening now' : 'Next trip'}
            </span>
            <strong>{nextTrip.name}</strong>
            <span className="next-trip-where">📍 {nextTrip.destination}</span>
            <span className="next-trip-count">{nextTrip.timing.label}</span>
          </Link>
        )}
      </div>

      {stats.total > 0 && (
        <div className="stat-grid">
          <div className="stat"><span className="stat-num">{stats.total}</span><span className="stat-label">Total trips</span></div>
          <div className="stat"><span className="stat-num">{stats.upcoming}</span><span className="stat-label">Upcoming</span></div>
          <div className="stat"><span className="stat-num">{money(stats.budget)}</span><span className="stat-label">Combined budget</span></div>
          <div className="stat"><span className="stat-num">{stats.organizing}</span><span className="stat-label">You organize</span></div>
        </div>
      )}

      {error && <p className="form-error">{error}</p>}

      <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
        <button className="new-trip-btn" onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Cancel' : '+ New Trip'}
        </button>
        <button
          className="new-trip-btn"
          style={{ background: 'linear-gradient(135deg, var(--mint), #00A896)' }}
          onClick={() => setShowJoinForm(!showJoinForm)}
        >
          {showJoinForm ? 'Cancel' : '🔗 Join a Trip'}
        </button>
      </div>

      {showJoinForm && (
        <form onSubmit={handleJoinTrip} className="trip-form">
          <label className="field-label">
            Invite code
            <input
              className="field"
              placeholder="e.g. A1B2C3D4"
              value={joinCode}
              onChange={(e) => setJoinCode(e.target.value)}
              required
            />
          </label>
          <button className="btn-primary" type="submit" disabled={joining}>
            {joining ? 'Joining...' : 'Join Trip'}
          </button>
        </form>
      )}

      {showForm && (
        <form onSubmit={handleCreateTrip} className="trip-form">
          <input
            className="field"
            placeholder="Trip name (e.g. Goa Squad Trip)"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
          <input
            className="field"
            placeholder="Destination (e.g. Goa)"
            value={destination}
            onChange={(e) => setDestination(e.target.value)}
            required
          />
          <input
            className="field"
            type="number"
            placeholder="Total budget (e.g. 20000)"
            value={budget}
            onChange={(e) => setBudget(e.target.value)}
            required
          />
          <label className="field-label">
            Start date
            <input className="field" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          </label>
          <label className="field-label">
            End date
            <input className="field" type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
          </label>
          <button className="btn-primary" type="submit" disabled={creating}>
            {creating ? 'Creating...' : 'Create Trip'}
          </button>
        </form>
      )}

      <h2 className="section-label">Your trips</h2>

      {trips.length > 0 && (
        <div className="toolbar">
          <input
            className="field toolbar-search"
            placeholder="Search by trip or destination"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select className="field toolbar-sort" value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="soonest">Soonest first</option>
            <option value="newest">Newest created</option>
            <option value="budget">Highest budget</option>
          </select>
          <div className="chips">
            {[
              ['all', 'All'],
              ['upcoming', 'Upcoming'],
              ['ongoing', 'In progress'],
              ['completed', 'Completed'],
            ].map(([key, label]) => (
              <button
                key={key}
                type="button"
                className={`chip ${filter === key ? 'chip-active' : ''}`}
                onClick={() => setFilter(key)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      )}

      {trips.length === 0 ? (
        <p className="empty-state">No trips yet — create your first one above 🗺️</p>
      ) : visible.length === 0 ? (
        <p className="empty-state">No trips match your search or filter.</p>
      ) : (
        <div className="trip-list">
          {visible.map((trip) => {
            const perDay = trip.length ? Math.round(trip.total_budget / trip.length) : null
            const mine = user && trip.created_by === user.id
            return (
              <Link key={trip.id} to={`/trips/${trip.id}`} className="trip-card" style={{ textDecoration: 'none', color: 'inherit' }}>
                <div className="trip-card-icon">🧳</div>
                <div className="trip-card-main">
                  <h3>
                    {trip.name}
                    {mine && <span className="badge-org">Organizer</span>}
                  </h3>
                  <p className="destination">{trip.destination}</p>
                  <p className="trip-meta">
                    {trip.start_date
                      ? `${fmtDate(trip.start_date)}${trip.end_date ? ' – ' + fmtDate(trip.end_date) : ''}`
                      : 'Dates not set'}
                    {trip.length ? ` · ${trip.length} day${trip.length > 1 ? 's' : ''}` : ''}
                    {perDay ? ` · ~${money(perDay)}/day` : ''}
                  </p>
                  <button type="button" className="invite-chip" onClick={(e) => copyInvite(e, trip)}>
                    {copiedId === trip.id ? '✓ Copied' : `🔗 Invite code: ${trip.invite_code}`}
                  </button>
                </div>
                <div className="trip-card-right">
                  <div className="stub-budget">{money(trip.total_budget)}</div>
                  <span className={`stub-status timing-${trip.timing.key}`}>{trip.timing.label}</span>
                </div>
              </Link>
            )
          })}
        </div>
      )}

      <h2 className="section-label" style={{ marginTop: '3rem' }}>How TripSync works</h2>
      <div className="steps">
        {STEPS.map((s, i) => (
          <div className="step" key={s.title}>
            <div className="step-icon">{s.icon}</div>
            <span className="step-num">Step {i + 1}</span>
            <h3>{s.title}</h3>
            <p>{s.text}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

export default Dashboard
