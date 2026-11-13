"""
Delete the saved places of ONE destination, so the AI planner fetches them again.

Run from the backend folder:
    python reset_places.py pachmarhi

It also removes itinerary items that point at those places (they would block
the delete). Plans are regenerated the next time you click "Generate AI plan".
"""
import sys

from database import SessionLocal
import models

if len(sys.argv) < 2:
    raise SystemExit('Usage: python reset_places.py "<destination as typed in the trip>"')

dest = " ".join(sys.argv[1:]).strip()
db = SessionLocal()
ids = [i for (i,) in db.query(models.Place.id).filter(models.Place.destination.ilike(dest)).all()]
if not ids:
    raise SystemExit(f"No saved places found for '{dest}'.")
items = db.query(models.ItineraryItem).filter(models.ItineraryItem.place_id.in_(ids)).delete(synchronize_session=False)
places = db.query(models.Place).filter(models.Place.id.in_(ids)).delete(synchronize_session=False)
db.commit()
print(f"Deleted {places} places and {items} itinerary items for '{dest}'.")
