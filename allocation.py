from models import Application, Allocation
from helpers import find_vacant_bed


def run_allocation(cycle, criteria):
    applications = list(Application.objects(cycle=cycle, status="submitted"))

    def sort_key(app):
        if criteria.year_order == "senior":
            year = -app.year
        else:
            year = app.year
        return (year, app.created_at)

    applications.sort(key=sort_key)

    allocated = 0
    unallocated = 0
    for app in applications:
        bed = None
        if criteria.use_preference and app.hostel:
            bed = find_vacant_bed(hostel=app.hostel)
        if bed is None:
            bed = find_vacant_bed()
        if bed is None:
            app.status = "unallocated"
            app.save()
            unallocated += 1
            continue
        bed.occupied = True
        bed.save()
        Allocation(application=app, user=app.user, cycle=cycle, bed=bed).save()
        app.status = "allocated"
        app.save()
        allocated += 1
    return allocated, unallocated
