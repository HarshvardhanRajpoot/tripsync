// Shows where the trip budget goes: travel, stay, food, activities, buffer.
// Numbers come from the backend (budget_breakdown.py); they are estimates.
import type { BudgetBreakdownData, BudgetCategoryKey } from '../types'

const COLORS: Record<BudgetCategoryKey, string> = {
  travel: '#3b82c4',
  stay: '#8b5cf6',
  food: '#e8833a',
  activities: '#2f9e6f',
  buffer: '#9aa3b2',
}

const rupees = (n: number) => '₹' + Math.round(n).toLocaleString('en-IN')

interface Props {
  data?: BudgetBreakdownData
}

export default function BudgetBreakdown({ data }: Props) {
  if (!data || !data.categories) return null // older saved plans don't have a breakdown

  return (
    <div style={{ margin: '1.2rem 0', padding: '1rem 1.2rem', border: '1px solid rgba(128,128,150,0.25)', borderRadius: '14px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.3rem', marginBottom: '0.7rem' }}>
        <strong>Budget breakdown · {rupees(data.total)}</strong>
        <span style={{ fontSize: '0.85rem', opacity: 0.7 }}>
          {data.style_label} · {data.people} {data.people === 1 ? 'person' : 'people'} · {data.days} {data.days === 1 ? 'day' : 'days'}
        </span>
      </div>

      <div style={{ display: 'flex', height: '14px', borderRadius: '7px', overflow: 'hidden', marginBottom: '0.9rem' }}>
        {data.categories.filter((c) => c.amount > 0).map((c) => (
          <div key={c.key} title={`${c.label}: ${rupees(c.amount)}`} style={{ width: `${(c.amount / data.total) * 100}%`, background: COLORS[c.key] }} />
        ))}
      </div>

      {data.categories.map((c) => (
        <div key={c.key} style={{ display: 'flex', alignItems: 'baseline', gap: '0.6rem', padding: '0.3rem 0' }}>
          <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: COLORS[c.key], flexShrink: 0 }} />
          <span style={{ minWidth: '84px', fontWeight: 600 }}>{c.label}</span>
          <span style={{ minWidth: '84px' }}>{rupees(c.amount)} <span style={{ opacity: 0.6, fontSize: '0.8rem' }}>({c.percent}%)</span></span>
          <span style={{ fontSize: '0.85rem', opacity: 0.75 }}>{c.detail}</span>
        </div>
      ))}

      {data.warnings?.map((w, i) => (
        <p key={i} className="note" style={{ fontSize: '0.85rem', margin: '0.5rem 0 0' }}>⚠ {w}</p>
      ))}
      <p style={{ fontSize: '0.75rem', opacity: 0.6, margin: '0.6rem 0 0' }}>{data.note}</p>
    </div>
  )
}
