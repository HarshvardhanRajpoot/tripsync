// Shared types for everything the backend sends and receives.
// They mirror backend/schemas.py and the dicts returned by routes_ai.py / routes_explore.py.
// NOTE: these are compile-time only: the browser does not validate responses against them.

// ---------- constants that the types are built from ----------
export const INTEREST_OPTIONS = ['beach', 'food', 'culture', 'adventure', 'nightlife', 'nature', 'shopping'] as const
export const PACE_OPTIONS = ['relaxed', 'moderate', 'packed'] as const

export type InterestTag = (typeof INTEREST_OPTIONS)[number]
export type Pace = (typeof PACE_OPTIONS)[number]

export function isInterestTag(value: string): value is InterestTag {
  return (INTEREST_OPTIONS as readonly string[]).includes(value)
}

export function isPace(value: string): value is Pace {
  return (PACE_OPTIONS as readonly string[]).includes(value)
}

// ---------- auth ----------
export interface User {
  id: number
  name: string
  email: string
}

export interface Token {
  access_token: string
  token_type: string
}

export interface SignupPayload {
  name: string
  email: string
  password: string
}

export interface LoginPayload {
  email: string
  password: string
}

// ---------- trips ----------
export interface Trip {
  id: number
  name: string
  destination: string
  start_date: string | null // ISO date-time
  end_date: string | null
  total_budget: number
  status: string
  invite_code: string
  created_by: number
}

export interface TripCreatePayload {
  name: string
  destination: string
  total_budget: number
  start_date: string | null
  end_date: string | null
}

export interface TripMember {
  id: number
  trip_id: number
  user_id: number
  budget_contribution: number
}

export interface AddMemberPayload {
  user_email: string
  budget_contribution?: number
}

// ---------- preferences ----------
export interface Preference {
  id: number
  trip_member_id: number
  interest_tags: string // comma-separated, e.g. "food,culture"
  pace: string
  must_see_places: string | null
}

export interface PreferencePayload {
  interest_tags: InterestTag[]
  pace: Pace
  must_see_places: string | null
}

export interface MemberPreference {
  user_id: number
  user_name: string
  preference: Preference | null
}

// ---------- AI plan ----------
export type BudgetStyle = 'budget' | 'balanced' | 'comfort'
export type TimeOfDay = 'morning' | 'afternoon' | 'evening'
export type BudgetCategoryKey = 'travel' | 'stay' | 'food' | 'activities' | 'buffer'

export interface AiPlanRequest {
  request: string | null
  budget_style: BudgetStyle
  days?: number
  activity_budget?: number
}

export interface BudgetCategory {
  key: BudgetCategoryKey
  label: string
  amount: number
  percent: number
  detail: string
}

export interface BudgetBreakdownData {
  style: BudgetStyle
  style_label: string
  total: number
  days: number
  nights: number
  people: number
  categories: BudgetCategory[]
  activities_amount: number
  warnings: string[]
  note: string
}

export interface AiStop {
  place_id: number
  name: string
  category: string | null
  cost: number
  time_of_day: TimeOfDay
  why: string
  tip: string
}

export interface AiDay {
  day: number
  title: string
  stops: AiStop[]
}

export interface AiPlan {
  trip_id: number
  summary: string
  budget_note: string
  days: AiDay[]
  budget: { activity_budget: number; total_cost: number; remaining: number }
  breakdown?: BudgetBreakdownData // missing on plans saved before the breakdown existed
  unmatched_must_sees: string[]
  warnings: string[]
  ai_used: boolean
  retrieval_used: boolean
}

// ---------- explore ----------
export type ExploreSource = 'google' | 'openstreetmap' | 'wikipedia'

export interface ExplorePlace {
  place_id: string | null
  name: string
  kind: string | null
  address: string | null
  rating: number | null
  reviews: number | null
  maps_url: string | null
}

export interface ExploreResult {
  state: string
  district: string
  maps_search_url: string
  source: ExploreSource
  note: string | null
  places: ExplorePlace[]
}
