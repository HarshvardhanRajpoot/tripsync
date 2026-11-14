"""
Remove test accounts (and everything that belongs to them) from the database.

SAFE BY DEFAULT: nothing is deleted unless you add --delete AND type DELETE.

Run from the backend folder (venv active). Always start with step 1:

  1. See everyone:
       python cleanup_users.py

  2. Preview (nothing deleted). Keep only YOUR real account(s):
       python cleanup_users.py --keep you@gmail.com
     or name only the accounts to remove:
       python cleanup_users.py --remove test1@x.com,test2@x.com

  3. Really delete (it asks you to type DELETE first):
       python cleanup_users.py --keep you@gmail.com --delete

What goes with a deleted account: the trips it created, its memberships and
preferences, its AI plans and expenses. A trip created by a deleted account that
a KEPT account also joined is a conflict: the script stops and tells you. Add
--delete-shared-trips if you are happy to lose those trips too.

NOTE: this uses the database in backend/.env (your real Supabase database).
"""
import argparse
import sys

from sqlalchemy.orm import Session

import models
from database import SessionLocal


def plan(db: Session, doomed_ids: set[int], allow_shared: bool):
    """Works out exactly which rows to delete. Returns (trip_ids, conflicts)."""
    trips = db.query(models.Trip).all()
    members_by_trip: dict[int, set[int]] = {}
    for tm in db.query(models.TripMember).all():
        members_by_trip.setdefault(tm.trip_id, set()).add(tm.user_id)

    trip_ids, conflicts = set(), []
    for t in trips:
        members = members_by_trip.get(t.id, set())
        if t.created_by in doomed_ids:
            survivors = members - doomed_ids
            if survivors and not allow_shared:
                conflicts.append((t, survivors))
            else:
                trip_ids.add(t.id)
        elif members and members <= doomed_ids:      # nobody left who isn't being deleted
            trip_ids.add(t.id)
    return trip_ids, conflicts


def delete_rows(db: Session, doomed_ids: set[int], trip_ids: set[int]):
    """Deletes children before parents. Returns a dict of counts."""
    members = db.query(models.TripMember).filter(
        models.TripMember.trip_id.in_(trip_ids) | models.TripMember.user_id.in_(doomed_ids)
    ).all() if (trip_ids or doomed_ids) else []
    member_ids = [m.id for m in members]
    counts = {}

    def kill(label, query):
        counts[label] = query.delete(synchronize_session=False)

    if trip_ids or doomed_ids:
        kill("AI plans", db.query(models.AiPlan).filter(
            models.AiPlan.trip_id.in_(trip_ids) | models.AiPlan.user_id.in_(doomed_ids)))
        kill("itinerary items", db.query(models.ItineraryItem).filter(models.ItineraryItem.trip_id.in_(trip_ids)))
        kill("expenses", db.query(models.Expense).filter(
            models.Expense.trip_id.in_(trip_ids) | models.Expense.paid_by.in_(doomed_ids)))
    if member_ids:
        kill("preferences", db.query(models.Preference).filter(models.Preference.trip_member_id.in_(member_ids)))
        kill("memberships", db.query(models.TripMember).filter(models.TripMember.id.in_(member_ids)))
    if trip_ids:
        kill("trips", db.query(models.Trip).filter(models.Trip.id.in_(trip_ids)))
    kill("users", db.query(models.User).filter(models.User.id.in_(doomed_ids)))
    return counts


def main():
    ap = argparse.ArgumentParser(description="Remove test accounts safely.")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--keep", help="comma-separated emails to KEEP; everyone else is removed")
    group.add_argument("--remove", help="comma-separated emails to remove")
    ap.add_argument("--delete", action="store_true", help="actually delete (otherwise only a preview)")
    ap.add_argument("--delete-shared-trips", action="store_true",
                    help="also delete trips created by removed accounts that kept accounts joined")
    args = ap.parse_args()

    db = SessionLocal()
    users = db.query(models.User).order_by(models.User.id).all()
    by_email = {u.email.lower(): u for u in users}
    trips_created = {u.id: db.query(models.Trip).filter(models.Trip.created_by == u.id).count() for u in users}
    joined = {u.id: db.query(models.TripMember).filter(models.TripMember.user_id == u.id).count() for u in users}

    def parse(value):
        emails = [e.strip().lower() for e in value.split(",") if e.strip()]
        unknown = [e for e in emails if e not in by_email]
        if unknown:
            sys.exit("These emails do not exist: " + ", ".join(unknown) + "\nNothing was changed.")
        return {by_email[e].id for e in emails}

    if not (args.keep or args.remove):
        print(f"{len(users)} accounts:\n")
        for u in users:
            print(f"  id {u.id:<4} {u.email:<34} {u.name:<18} trips created: {trips_created[u.id]}, trips joined: {joined[u.id]}")
        print("\nNext: python cleanup_users.py --keep your@email.com   (preview, deletes nothing)")
        return

    if args.keep:
        keep_ids = parse(args.keep)
        doomed = {u.id for u in users} - keep_ids
    else:
        doomed = parse(args.remove)
    if not doomed:
        sys.exit("Nothing to remove.")
    if len(doomed) == len(users):
        sys.exit("That would delete EVERY account. Nothing was changed.")

    trip_ids, conflicts = plan(db, doomed, args.delete_shared_trips)
    id_to_user = {u.id: u for u in users}

    print("WILL DELETE accounts:")
    for uid in sorted(doomed):
        u = id_to_user[uid]
        print(f"  x {u.email:<34} ({u.name})")
    print("WILL KEEP accounts:")
    for u in users:
        if u.id not in doomed:
            print(f"  ok {u.email:<33} ({u.name})")
    trips = db.query(models.Trip).filter(models.Trip.id.in_(trip_ids)).all() if trip_ids else []
    print(f"\nTrips that will be deleted with them ({len(trips)}):")
    for t in trips:
        print(f"  - #{t.id} {t.name} ({t.destination})")

    if conflicts:
        print("\nCONFLICT: these trips were created by an account you are removing, but a kept account joined them:")
        for t, survivors in conflicts:
            who = ", ".join(id_to_user[i].email for i in survivors)
            print(f"  - #{t.id} {t.name}  (kept members: {who})")
        print("Keep the creator's account, or add --delete-shared-trips to delete these trips too.\nNothing was changed.")
        sys.exit(1)

    if not args.delete:
        print("\nPREVIEW ONLY. Nothing was deleted. Add --delete to do it for real.")
        return

    if input("\nType DELETE to confirm (anything else cancels): ").strip() != "DELETE":
        sys.exit("Cancelled. Nothing was changed.")
    try:
        counts = delete_rows(db, doomed, trip_ids)
        db.commit()
    except Exception as e:
        db.rollback()
        sys.exit(f"Failed and rolled back, nothing was changed: {e}")
    print("\nDeleted: " + ", ".join(f"{n} {label}" for label, n in counts.items()))


if __name__ == "__main__":
    main()
