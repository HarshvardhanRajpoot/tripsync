import { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { api } from '../api'
import BudgetBreakdown from '../components/BudgetBreakdown'

const INTEREST_OPTIONS = ['beach', 'food', 'culture', 'adventure', 'nightlife', 'nature', 'shopping']
const PACE_OPTIONS = ['relaxed', 'moderate', 'packed']

function TripDetail() {
  const { id } = useParams()
  const navigate = useNavigate()

  const [trip, setTrip] = useState(null)
  const [members, setMembers] = useState([])
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)

  const [selectedTags, setSelectedTags] = useState([])
  const [pace, setPace] = useState('moderate')
  const [mustSee, setMustSee] = useState('')
  const [saving, setSaving] = useState(false)

  const [aiRequest, setAiRequest] = useState('')
  const [aiPlan, setAiPlan] = useState(null)
  const [aiLoading, setAiLoading] = useState(false)
  const [aiError, setAiError] = useState('')
  const [budgetStyle, setBudgetStyle] = useState('balanced')

  useEffect(() => {
    if (!api.getToken()) {
      navigate('/login')
      return
    }
    loadData()
    // show the last AI plan if there is one (404 just means "none yet")
    api.getAiPlan(id).then(setAiPlan).catch(() => {})
  }, [id])

  async function loadData() {
    try {
      const [tripRes, prefsRes] = await Promise.all([
        api.getTrip(id),
        api.listPreferences(id),
      ])
      setTrip(tripRes)
      setMembers(prefsRes)

      // Pre-fill the form if the current user already has a preference saved
      const me = await api.me()
      const mine = prefsRes.find((m) => m.user_id === me.id)
      if (mine?.preference) {
        setSelectedTags(mine.preference.interest_tags.split(',').filter(Boolean))
        setPace(mine.preference.pace)
        setMustSee(mine.preference.must_see_places || '')
      }
    } catch (err) {
      setError(err.message)
    }
  }

  function toggleTag(tag) {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    )
  }

  async function handleSave(e) {
    e.preventDefault()
    setSaving(true)
    setError('')
    setSaved(false)
    try {
      await api.setPreference(id, {
        interest_tags: selectedTags,
        pace,
        must_see_places: mustSee || null,
      })
      setSaved(true)
      loadData()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleGeneratePlan(e) {
    e.preventDefault()
    setAiLoading(true)
    setAiError('')
    try {
      const plan = await api.generateAiPlan(id, { request: aiRequest.trim() || null, budget_style: budgetStyle })
      setAiPlan(plan)
    } catch (err) {
      setAiError(err.message)
    } finally {
      setAiLoading(false)
    }
  }

  if (!trip) return <div className="dash">Loading...</div>

  return (
    <div className="dash">
      <Link to="/dashboard" className="btn-secondary" style={{ display: 'inline-block', marginBottom: '1.5rem', textDecoration: 'none' }}>
        ← Back to trips
      </Link>

      <div className="dash-header">
        <h1>🧳 {trip.name}</h1>
      </div>
      <p style={{ color: 'var(--ink-soft)', marginTop: '-1rem', marginBottom: '1rem' }}>
        {trip.destination} · Budget ₹{trip.total_budget}
      </p>

      <div className="trip-form" style={{ maxWidth: '340px', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: '1rem 1.3rem' }}>
        <div>
          <div style={{ fontSize: '0.75rem', color: 'var(--ink-soft)', fontWeight: 600, textTransform: 'uppercase' }}>Invite code</div>
          <div style={{ fontSize: '1.3rem', fontWeight: 700, letterSpacing: '0.05em' }}>{trip.invite_code}</div>
        </div>
        <button
          className="btn-secondary"
          onClick={() => navigator.clipboard.writeText(trip.invite_code)}
        >
          Copy
        </button>
      </div>

      {error && <p className="form-error">{error}</p>}

      <h2 className="section-label">Your preferences</h2>
      <form onSubmit={handleSave} className="trip-form" style={{ maxWidth: '420px' }}>
        <label className="field-label">
          What are you into? (pick a few)
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginTop: '0.3rem' }}>
            {INTEREST_OPTIONS.map((tag) => (
              <button
                type="button"
                key={tag}
                onClick={() => toggleTag(tag)}
                className="btn-secondary"
                style={{
                  background: selectedTags.includes(tag) ? 'var(--purple)' : 'var(--bg-tint)',
                  color: selectedTags.includes(tag) ? 'white' : 'var(--ink)',
                  textTransform: 'capitalize',
                }}
              >
                {tag}
              </button>
            ))}
          </div>
        </label>

        <label className="field-label">
          Pace
          <select className="field" value={pace} onChange={(e) => setPace(e.target.value)}>
            {PACE_OPTIONS.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </label>

        <label className="field-label">
          Must-see places (optional)
          <input
            className="field"
            placeholder="e.g. Baga Beach, Fort Aguada"
            value={mustSee}
            onChange={(e) => setMustSee(e.target.value)}
          />
        </label>

        <button className="btn-primary" type="submit" disabled={saving}>
          {saving ? 'Saving...' : 'Save my preferences'}
        </button>
        {saved && <p style={{ color: 'var(--mint)', fontWeight: 600, fontSize: '0.9rem' }}>Saved ✓</p>}
      </form>


      <h2 className="section-label" style={{ marginTop: '2.5rem' }}>✨ AI trip planner</h2>
      <form onSubmit={handleGeneratePlan} className="trip-form" style={{ maxWidth: '520px' }}>
        <label className="field-label">
          Anything else the group wants? (optional)
          <textarea
            className="field"
            rows={2}
            maxLength={300}
            placeholder="e.g. street food, old forts, not too tiring"
            value={aiRequest}
            onChange={(e) => setAiRequest(e.target.value)}
          />
        </label>
        <label className="field-label">
          Budget style
          <select className="field" value={budgetStyle} onChange={(e) => setBudgetStyle(e.target.value)}>
            <option value="budget">Budget-friendly (more for travel and food)</option>
            <option value="balanced">Balanced</option>
            <option value="comfort">Comfortable (more for stay)</option>
          </select>
        </label>
        <button className="btn-primary" type="submit" disabled={aiLoading}>
          {aiLoading ? 'Planning your trip… (the first run can take ~30s)' : aiPlan ? 'Regenerate plan' : 'Generate AI plan'}
        </button>
        <p style={{ fontSize: '0.8rem', color: 'var(--ink-soft)', margin: 0 }}>
          Uses everyone&rsquo;s saved preferences and the trip budget.
        </p>
        {aiError && <p className="form-error">{aiError}</p>}
      </form>

      {aiPlan && (
        <div style={{ marginTop: '1.5rem', maxWidth: '720px' }}>
          {aiPlan.summary && <p style={{ fontSize: '1.05rem', lineHeight: 1.5 }}>{aiPlan.summary}</p>}
          <BudgetBreakdown data={aiPlan.breakdown} />
          <p style={{ color: 'var(--ink-soft)', fontSize: '0.9rem' }}>
            Planned ₹{Math.round(aiPlan.budget.total_cost)} of ₹{Math.round(aiPlan.budget.activity_budget)} activity budget
            {aiPlan.budget_note ? ` · ${aiPlan.budget_note}` : ''}
          </p>
          {aiPlan.warnings?.map((w, i) => (
            <p key={i} className="note" style={{ fontSize: '0.85rem' }}>⚠ {w}</p>
          ))}
          {aiPlan.unmatched_must_sees?.length > 0 && (
            <p className="note" style={{ fontSize: '0.85rem' }}>
              Couldn&rsquo;t find: {aiPlan.unmatched_must_sees.join(', ')}
            </p>
          )}
          {aiPlan.days.map((day) => (
            <div key={day.day} style={{ marginTop: '1.4rem' }}>
              <h3 style={{ marginBottom: '0.6rem' }}>Day {day.day} · {day.title}</h3>
              <div className="trip-list">
                {day.stops.map((s) => (
                  <div key={s.place_id} className="trip-card">
                    <div className="trip-card-icon">{s.time_of_day === 'morning' ? '🌅' : s.time_of_day === 'evening' ? '🌙' : '☀️'}</div>
                    <div className="trip-card-main">
                      <h3>{s.name} <span style={{ fontWeight: 400, fontSize: '0.85rem', color: 'var(--ink-soft)' }}>· ₹{Math.round(s.cost)}</span></h3>
                      {s.why && <p className="destination">{s.why}</p>}
                      {s.tip && <p style={{ fontSize: '0.85rem', color: 'var(--ink-soft)', margin: '0.2rem 0 0' }}>💡 {s.tip}</p>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
          {!aiPlan.ai_used && <p className="note" style={{ fontSize: '0.8rem' }}>AI text wasn&rsquo;t available, so this is the optimizer&rsquo;s plan.</p>}
        </div>
      )}

      <h2 className="section-label" style={{ marginTop: '2.5rem' }}>Group preferences</h2>
      <div className="trip-list">
        {members.map((m) => (
          <div key={m.user_id} className="trip-card">
            <div className="trip-card-icon">👤</div>
            <div className="trip-card-main">
              <h3>{m.user_name}</h3>
              <p className="destination">
                {m.preference
                  ? `${m.preference.interest_tags.split(',').join(', ')} · ${m.preference.pace} pace`
                  : 'Hasn\u2019t set preferences yet'}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default TripDetail
