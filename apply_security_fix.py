"""
Closes a security hole and fixes a stuck "Loading..." page.

THE PROBLEM
  Any logged-in user could read ANY trip (including its invite code) by changing
  the number in /api/trips/<id>, add people to other people's trips, and list or
  refresh places for them. Only trip members should be allowed.

Run ONCE from the tripsync folder:   python apply_security_fix.py

It changes backend/main.py (4 endpoints) and frontend/src/pages/TripDetail.tsx
(shows the error instead of "Loading..." forever). If a spot can't be found it
stops BEFORE writing anything. Running it twice is safe.
"""
import pathlib
import sys

MAIN = pathlib.Path("backend/main.py")
PAGE = pathlib.Path("frontend/src/pages/TripDetail.tsx")
for p in (MAIN, PAGE):
    if not p.exists():
        sys.exit(f"Can't find {p}. Run this from the tripsync folder.")

main_src = MAIN.read_text(encoding="utf-8")
page_src = PAGE.read_text(encoding="utf-8")
CHECK = "    _get_or_404_trip_member(trip_id, current_user.id, db)  # only members\n"

if "# only members" in main_src and "dash\">\n        {error ? (" in page_src:
    print("Already applied. Nothing to do.")
    sys.exit(0)

NOT_FOUND = '''    trip = db.query(models.Trip).filter(models.Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
'''
edits = []   # (file label, old, new)

def add_check(signature: str, label: str):
    """Insert the membership check right after the endpoint's docstring/signature, before the trip lookup."""
    start = main_src.find(signature)
    if start == -1:
        return None
    body = main_src.find("    trip = db.query(models.Trip)", start)
    return (start, body, label)

# 1. get_trip, 2. add_trip_member, 3. refresh_places, 4. list_places_for_trip
targets = {
    "get_trip": "def get_trip(",
    "add_trip_member": "def add_trip_member(",
    "refresh_places": "def refresh_places(",
    "list_places_for_trip": "def list_places_for_trip(",
}
positions = []
for label, sig in targets.items():
    if main_src.count(sig) != 1:
        sys.exit(f"Could not find {label} in backend/main.py. Nothing was changed.")
    start = main_src.index(sig)
    body = main_src.find("    trip = db.query(models.Trip).filter(models.Trip.id == trip_id).first()\n", start)
    nxt = main_src.find("\n@app.", start)
    if body == -1 or (nxt != -1 and body > nxt):
        sys.exit(f"The code of {label} looks different from what I expected. Nothing was changed.")
    positions.append((body, label))

OLD_LOADING = '  if (!trip) return <div className="dash">Loading...</div>\n'
NEW_LOADING = '''  if (!trip) {
    return (
      <div className="dash">
        {error ? (
          <>
            <p className="form-error">{error}</p>
            <Link to="/dashboard" className="btn-secondary" style={{ textDecoration: 'none' }}>
              ← Back to trips
            </Link>
          </>
        ) : (
          'Loading...'
        )}
      </div>
    )
  }
'''
if page_src.count(OLD_LOADING) != 1:
    sys.exit("Could not find the Loading line in TripDetail.tsx. Nothing was changed.")

# apply (from the bottom up so earlier positions stay valid)
for body, _ in sorted(positions, reverse=True):
    main_src = main_src[:body] + CHECK + main_src[body:]
MAIN.write_text(main_src, encoding="utf-8")
PAGE.write_text(page_src.replace(OLD_LOADING, NEW_LOADING, 1), encoding="utf-8")
print("Done. 4 endpoints now require trip membership, and the trip page shows errors.")
