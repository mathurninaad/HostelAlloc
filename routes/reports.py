from fastapi import APIRouter, Depends, Request
from models import Hostel, Application, RoomChange
from helpers import render, login_required, current_cycle

router = APIRouter()


@router.get("/reports")
def reports(
    request: Request,
    user=Depends(login_required("warden", "office", "institute", "sysadmin")),
):
    if user.role == "warden":
        hostels = list(Hostel.objects(warden=user))
    else:
        hostels = list(Hostel.objects)
    ids = [h.id for h in hostels]

    occupancy = []
    for h in hostels:
        total = h.total_beds()
        used = h.occupied_beds()
        percent = round(used * 100 / total) if total else 0
        occupancy.append({"name": h.name, "rooms": len(h.rooms), "total": total, "used": used,
                          "vacant": total - used, "percent": percent})

    cycle = current_cycle()
    by_status = {}
    by_year = {}
    if cycle:
        for app in Application.objects(cycle=cycle):
            by_status[app.status] = by_status.get(app.status, 0) + 1
            if app.status not in ("withdrawn", "draft"):
                by_year[app.year] = by_year.get(app.year, 0) + 1

    changes = list(RoomChange.objects.order_by("-id"))
    if user.role == "warden":
        changes = [c for c in changes if c.requested_room.hostel.id in ids or c.allocation.bed.room.hostel.id in ids]
    change_counts = {}
    for c in changes:
        change_counts[c.status] = change_counts.get(c.status, 0) + 1

    return render(
        request, "reports.html", user=user, occupancy=occupancy, cycle=cycle, by_status=by_status,
        by_year=sorted(by_year.items()), changes=changes, change_counts=change_counts,
    )
