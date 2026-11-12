"""
Seed sample places so the optimizer has data without a Google key.
Run from the backend folder:   python seed_places.py
Create your test trip with destination exactly "Jaipur".
Costs are rough per-person rupee estimates (sample data, not live prices).
"""
from database import SessionLocal
import models

DEST = "Jaipur"
# name, category, lat, lng, cost per person, rating
PLACES = [
    ("Amber Fort", "sightseeing", 26.9855, 75.8513, 550, 4.6),
    ("City Palace", "sightseeing", 26.9258, 75.8237, 700, 4.5),
    ("Hawa Mahal", "sightseeing", 26.9239, 75.8267, 200, 4.4),
    ("Jantar Mantar", "sightseeing", 26.9247, 75.8246, 200, 4.5),
    ("Nahargarh Fort", "sightseeing", 26.9373, 75.8155, 200, 4.5),
    ("Jaigarh Fort", "sightseeing", 26.9856, 75.8440, 200, 4.5),
    ("Jal Mahal", "sightseeing", 26.9535, 75.8462, 0, 4.3),
    ("Albert Hall Museum", "sightseeing", 26.9116, 75.8195, 150, 4.4),
    ("Birla Mandir", "sightseeing", 26.8920, 75.8157, 0, 4.6),
    ("Johari Bazaar Shopping Walk", "sightseeing", 26.9190, 75.8250, 500, 4.2),
    ("Laxmi Misthan Bhandar (LMB)", "food", 26.9188, 75.8213, 600, 4.2),
    ("Rawat Mishthan Bhandar", "food", 26.9065, 75.7896, 300, 4.3),
    ("Chokhi Dhani Dinner", "food", 26.7660, 75.8390, 1200, 4.4),
    ("Masala Chowk Street Food", "food", 26.9240, 75.8250, 250, 4.3),
    ("Tapri Central Cafe", "food", 26.9050, 75.8070, 400, 4.4),
    ("Hot Air Balloon Ride", "adventure", 26.9800, 75.8500, 12000, 4.5),
    ("Elephant Village Visit", "adventure", 26.9900, 75.8500, 1000, 4.0),
    ("Jaipur Zipline Experience", "adventure", 26.9860, 75.8470, 2000, 4.3),
]

db = SessionLocal()
added = 0
for name, cat, lat, lng, cost, rating in PLACES:
    exists = db.query(models.Place).filter(models.Place.name == name, models.Place.destination == DEST).first()
    if exists:
        continue
    db.add(models.Place(name=name, category=cat, latitude=lat, longitude=lng,
                        estimated_cost=cost, rating=rating, destination=DEST))
    added += 1
db.commit()
print(f"Seeded {added} new places for {DEST}.")
