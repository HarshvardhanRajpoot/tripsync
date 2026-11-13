import type {
  AddMemberPayload,
  AiPlan,
  AiPlanRequest,
  ExploreResult,
  LoginPayload,
  MemberPreference,
  Preference,
  PreferencePayload,
  SignupPayload,
  Token,
  Trip,
  TripCreatePayload,
  TripMember,
  User,
} from '../types'

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const TOKEN_KEY = 'tripsync_token'

function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

/** Turns anything thrown in a catch block into a message we can show. */
export function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : 'Something went wrong'
}

interface RequestOptions {
  method?: 'GET' | 'POST'
  body?: unknown
  auth?: boolean
}

async function request<T>(path: string, { method = 'GET', body, auth = false }: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
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
    const errData: { detail?: unknown } = await res.json().catch(() => ({}))
    const message =
      typeof errData.detail === 'string'
        ? errData.detail
        : Array.isArray(errData.detail)
        ? errData.detail.map((d: { msg?: string }) => d.msg).join(', ')
        : 'Something went wrong'
    throw new Error(message)
  }

  return (await res.json()) as T
}

export const api = {
  signup: (data: SignupPayload) => request<User>('/api/auth/signup', { method: 'POST', body: data }),
  login: (data: LoginPayload) => request<Token>('/api/auth/login', { method: 'POST', body: data }),
  me: () => request<User>('/api/auth/me', { auth: true }),

  createTrip: (data: TripCreatePayload) => request<Trip>('/api/trips', { method: 'POST', body: data, auth: true }),
  joinTrip: (inviteCode: string) =>
    request<Trip>('/api/trips/join', { method: 'POST', body: { invite_code: inviteCode }, auth: true }),
  listTrips: () => request<Trip[]>('/api/trips', { auth: true }),
  getTrip: (id: string | number) => request<Trip>(`/api/trips/${id}`, { auth: true }),
  addMember: (tripId: string | number, data: AddMemberPayload) =>
    request<TripMember>(`/api/trips/${tripId}/members`, { method: 'POST', body: data, auth: true }),

  setPreference: (tripId: string | number, data: PreferencePayload) =>
    request<Preference>(`/api/trips/${tripId}/preferences`, { method: 'POST', body: data, auth: true }),
  listPreferences: (tripId: string | number) =>
    request<MemberPreference[]>(`/api/trips/${tripId}/preferences`, { auth: true }),

  generateAiPlan: (tripId: string | number, data: AiPlanRequest) =>
    request<AiPlan>(`/api/trips/${tripId}/ai-plan`, { method: 'POST', body: data, auth: true }),
  getAiPlan: (tripId: string | number) => request<AiPlan>(`/api/trips/${tripId}/ai-plan`, { auth: true }),

  exploreStates: () => request<string[]>('/api/explore/states', { auth: true }),
  exploreDistricts: (state: string) =>
    request<string[]>(`/api/explore/districts?state=${encodeURIComponent(state)}`, { auth: true }),
  explorePlaces: (state: string, district: string) =>
    request<ExploreResult>(
      `/api/explore/places?state=${encodeURIComponent(state)}&district=${encodeURIComponent(district)}`,
      { auth: true },
    ),

  setToken,
  clearToken,
  getToken,
}
