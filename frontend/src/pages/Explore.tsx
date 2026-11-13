import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { api, errorMessage } from '../api'
import type { ExploreResult } from '../types'
import rawLocations from '../data/indiaStatesDistricts.json'

// state name -> list of districts
const LOCATIONS: Record<string, string[]> = rawLocations

const SOURCE_LABELS: Record<string, string> = {
  google: 'Google Places',
  openstreetmap: 'OpenStreetMap',
  wikipedia: 'Wikipedia',
}

function fallbackLink(state: string, district: string) {
  const q = encodeURIComponent(`top tourist places in ${district} ${state}`)
  return `https://www.google.com/maps/search/?api=1&query=${q}`
}

function Explore() {
  const states = Object.keys(LOCATIONS)
  const [state, setState] = useState('')
  const [district, setDistrict] = useState('')
  const [result, setResult] = useState<ExploreResult | null>(null)
  const [loadingPlaces, setLoadingPlaces] = useState(false)
  const [error, setError] = useState('')
  const requestId = useRef(0) // ignore answers from older selections

  const navigate = useNavigate()

  useEffect(() => {
    if (!api.getToken()) {
      navigate('/login')
      return
    }
  }, [])

  function handleStateChange(e: ChangeEvent<HTMLSelectElement>) {
    const value = e.target.value
    requestId.current += 1
    setState(value)
    setDistrict('')
    setResult(null)
    setError('')
    setLoadingPlaces(false)
  }

  async function handleDistrictChange(e: ChangeEvent<HTMLSelectElement>) {
    const value = e.target.value
    setDistrict(value)
    setResult(null)
    setError('')
    if (!value) return
    const myId = ++requestId.current
    setLoadingPlaces(true)
    try {
      const data = await api.explorePlaces(state, value)
      if (myId === requestId.current) setResult(data)
    } catch (err) {
      if (myId === requestId.current) setError(errorMessage(err))
    } finally {
      if (myId === requestId.current) setLoadingPlaces(false)
    }
  }

  return (
    <div className="dash">
      <div className="dash-header">
        <h1>🧭 Explore places</h1>
        <Link to="/dashboard" className="btn-secondary" style={{ textDecoration: 'none' }}>← Back to trips</Link>
      </div>

      <p className="explore-intro">
        Pick a state and a district to see its most visited places, with a Google Maps link for each.
      </p>

      <div className="explore-controls">
        <label className="field-label">
          State
          <select className="field" value={state} onChange={handleStateChange}>
            <option value="">Select a state</option>
            {states.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        <label className="field-label">
          District
          <select className="field" value={district} onChange={handleDistrictChange} disabled={!state}>
            <option value="">{state ? 'Select a district' : 'Select a state first'}</option>
            {(LOCATIONS[state] || []).map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </label>
      </div>

      {error && (
        <div className="form-error" style={{ marginTop: '1.2rem' }}>
          {error}
          {district && (
            <div style={{ marginTop: '0.5rem' }}>
              You can still{' '}
              <a href={fallbackLink(state, district)} target="_blank" rel="noopener noreferrer">
                search {district} on Google Maps
              </a>.
            </div>
          )}
        </div>
      )}

      {loadingPlaces && <p className="empty-state" style={{ marginTop: '1.5rem' }}>Finding top places in {district}…</p>}

      {result && result.places.length === 0 && (
        <p className="empty-state" style={{ marginTop: '1.5rem' }}>
          No places found for {result.district}.{' '}
          <a href={result.maps_search_url} target="_blank" rel="noopener noreferrer">Try Google Maps</a>
        </p>
      )}

      {result && result.places.length > 0 && (
        <>
          <h2 className="section-label" style={{ marginTop: '2rem' }}>
            Top places in {result.district}, {result.state}
          </h2>
          {result.note && <p className="note">{result.note}</p>}
          <div className="trip-list">
            {result.places.map((p, i) => (
              <div className="place-card" key={p.place_id || p.name}>
                <div className="place-rank">{i + 1}</div>
                <div className="place-main">
                  <h3>
                    {p.name}
                    {p.kind && <span className="kind-chip">{p.kind}</span>}
                  </h3>
                  {p.address && <p className="destination">{p.address}</p>}
                  {p.rating != null && (
                    <p className="trip-meta">
                      ⭐ {p.rating.toFixed(1)}
                      {p.reviews ? ` · ${p.reviews.toLocaleString('en-IN')} reviews` : ''}
                    </p>
                  )}
                </div>
                {p.maps_url && (
                  <a className="map-btn" href={p.maps_url} target="_blank" rel="noopener noreferrer">
                    📍 Google Maps
                  </a>
                )}
              </div>
            ))}
          </div>
          <p className="trip-meta">
            Source: {SOURCE_LABELS[result.source] ?? result.source}
          </p>
          <p className="explore-more">
            <a href={result.maps_search_url} target="_blank" rel="noopener noreferrer">
              See more places in {result.district} on Google Maps →
            </a>
          </p>
        </>
      )}
    </div>
  )
}

export default Explore
