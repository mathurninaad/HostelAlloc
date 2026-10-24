from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from database import get_db
from models import Hostel, Application, RoomChange
from helpers import render, login_required, current_cycle

router = APIRouter()


@router.get("/reports")
def reports(
    request: Request,
    user=Depends(login_required("warden", "office", "institute", "sysadmin")),
    db: Session = Depends(get_db),
):
    query = db.query(Hostel)
    if user.role == "warden":
        query = query.filter(Hostel.warden_id == user.id)
    hostels = query.all()
    ids = [h.id for h in hostels]

    occupancy = []
    for h in hostels:
        total = h.total_beds()
        used = h.occupied_beds()
        percent = round(used * 100 / total) if total else 0
        occupancy.append({"name": h.name, "rooms": len(h.rooms), "total": total, "used": used,
                          "vacant": total - used, "percent": percent})

    cycle = current_cycle(db)
    by_status = {}
    by_year = {}
    if cycle:
        for app in db.query(Application).filter_by(cycle_id=cycle.id).all():
            by_status[app.status] = by_status.get(app.status, 0) + 1
            if app.status != "withdrawn":
                by_year[app.year] = by_year.get(app.year, 0) + 1

    changes = db.query(RoomChange).order_by(RoomChange.id.desc()).all()
    if user.role == "warden":
        changes = [c for c in changes if c.requested_room.hostel_id in ids or c.allocation.bed.room.hostel_id in ids]
    change_counts = {}
    for c in changes:
        change_counts[c.status] = change_counts.get(c.status, 0) + 1

    return render(
        request, "reports.html", user=user, occupancy=occupancy, cycle=cycle, by_status=by_status,
        by_year=sorted(by_year.items()), changes=changes, change_counts=change_counts,
    )
