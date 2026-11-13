const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function getToken() {
  return localStorage.getItem('tripsync_token')
}

function setToken(token) {
  localStorage.setItem('tripsync_token', token)
}

function clearToken() {
  localStorage.removeItem('tripsync_token')
}

async function request(path, { method = 'GET', body, auth = false } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (auth) {
    const token = getToken()
    if (token) headers['Authorization'] = `Bearer ${token}`
  }

  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  })

  if (!res.ok) {
    const errData = await res.json().catch(() => ({}))
    const message =
      typeof errData.detail === 'string'
        ? errData.detail
        : Array.isArray(errData.detail)
        ? errData.detail.map((d) => d.msg).join(', ')
        : 'Something went wrong'
    throw new Error(message)
  }

  return res.json()
}

export const api = {
  signup: (data) => request('/api/auth/signup', { method: 'POST', body: data }),
  login: (data) => request('/api/auth/login', { method: 'POST', body: data }),
  me: () => request('/api/auth/me', { auth: true }),

  createTrip: (data) => request('/api/trips', { method: 'POST', body: data, auth: true }),
  joinTrip: (inviteCode) => request('/api/trips/join', { method: 'POST', body: { invite_code: inviteCode }, auth: true }),
  listTrips: () => request('/api/trips', { auth: true }),
  getTrip: (id) => request(`/api/trips/${id}`, { auth: true }),
  addMember: (tripId, data) =>
    request(`/api/trips/${tripId}/members`, { method: 'POST', body: data, auth: true }),

  setPreference: (tripId, data) =>
    request(`/api/trips/${tripId}/preferences`, { method: 'POST', body: data, auth: true }),
  listPreferences: (tripId) =>
    request(`/api/trips/${tripId}/preferences`, { auth: true }),

  generateAiPlan: (tripId, data) =>
    request(`/api/trips/${tripId}/ai-plan`, { method: 'POST', body: data, auth: true }),
  getAiPlan: (tripId) => request(`/api/trips/${tripId}/ai-plan`, { auth: true }),

  exploreStates: () => request('/api/explore/states', { auth: true }),
  exploreDistricts: (state) =>
    request(`/api/explore/districts?state=${encodeURIComponent(state)}`, { auth: true }),
  explorePlaces: (state, district) =>
    request(`/api/explore/places?state=${encodeURIComponent(state)}&district=${encodeURIComponent(district)}`, { auth: true }),

  setToken,
  clearToken,
  getToken,
}
