from models import Application
from helpers import find_vacant_bed
from models import Allocation


def run_allocation(db, cycle, criteria):
    applications = db.query(Application).filter_by(cycle_id=cycle.id, status="submitted").all()

    def sort_key(app):
        if criteria.priority_category and app.category == criteria.priority_category:
            first = 0
        else:
            first = 1
        if criteria.year_order == "senior":
            year = -app.year
        else:
            year = app.year
        return (first, year, app.created_at)

    applications.sort(key=sort_key)

    allocated = 0
    unallocated = 0
    for app in applications:
        bed = None
        if criteria.use_preference and app.hostel_id:
            bed = find_vacant_bed(db, hostel_id=app.hostel_id)
        if bed is None:
            bed = find_vacant_bed(db)
        if bed is None:
            app.status = "unallocated"
            unallocated += 1
            continue
        bed.occupied = True
        app.status = "allocated"
        db.add(Allocation(application_id=app.id, user_id=app.user_id, cycle_id=cycle.id, bed_id=bed.id))
        db.flush()
        allocated += 1
    return allocated, unallocated
