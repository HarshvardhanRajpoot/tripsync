"""
Adds the budget breakdown to frontend/src/pages/TripDetail.jsx.

Run ONCE from the tripsync folder:   python apply_budget_ui.py

It makes 5 small edits to TripDetail.jsx. If any spot can't be found (because
the file was changed), it stops BEFORE writing anything and tells you which one.
Running it twice is safe.
"""
import pathlib
import sys

path = pathlib.Path("frontend/src/pages/TripDetail.jsx")
if not path.exists():
    sys.exit("Run this from the tripsync folder (the one that contains 'frontend' and 'backend').")
src = path.read_text(encoding="utf-8")

if "BudgetBreakdown" in src:
    sys.exit("Already applied. Nothing to do.")

edits = [
    ("import",
     "import { api } from '../api'\n",
     "import { api } from '../api'\nimport BudgetBreakdown from '../components/BudgetBreakdown'\n"),
    ("state",
     "  const [aiError, setAiError] = useState('')\n",
     "  const [aiError, setAiError] = useState('')\n  const [budgetStyle, setBudgetStyle] = useState('balanced')\n"),
    ("request",
     "api.generateAiPlan(id, { request: aiRequest.trim() || null })",
     "api.generateAiPlan(id, { request: aiRequest.trim() || null, budget_style: budgetStyle })"),
    ("style picker",
     '        <button className="btn-primary" type="submit" disabled={aiLoading}>',
     '''        <label className="field-label">
          Budget style
          <select className="field" value={budgetStyle} onChange={(e) => setBudgetStyle(e.target.value)}>
            <option value="budget">Budget-friendly (more for travel and food)</option>
            <option value="balanced">Balanced</option>
            <option value="comfort">Comfortable (more for stay)</option>
          </select>
        </label>
        <button className="btn-primary" type="submit" disabled={aiLoading}>'''),
    ("breakdown card",
     "{aiPlan.summary && <p style={{ fontSize: '1.05rem', lineHeight: 1.5 }}>{aiPlan.summary}</p>}\n",
     "{aiPlan.summary && <p style={{ fontSize: '1.05rem', lineHeight: 1.5 }}>{aiPlan.summary}</p>}\n          <BudgetBreakdown data={aiPlan.breakdown} />\n"),
]

missing = [name for name, old, _ in edits if src.count(old) != 1]
if missing:
    sys.exit("Could not find the spot for: " + ", ".join(missing) + ". TripDetail.jsx was not changed. "
             "Send me the file and I'll adjust the script.")

for _, old, new in edits:
    src = src.replace(old, new, 1)
path.write_text(src, encoding="utf-8")
print("Done: TripDetail.jsx now shows the budget breakdown.")
