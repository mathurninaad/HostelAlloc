from fastapi import APIRouter, Depends, Request
from models import Hostel, Room
from helpers import render, login_required

router = APIRouter()


@router.get("/inventory")
def inventory(
    request: Request,
    hostel_id: str = "",
    status: str = "",
    user=Depends(login_required("warden", "office", "institute", "sysadmin")),
):
    hostels = list(Hostel.objects)
    rooms = sorted(Room.objects, key=lambda r: (r.hostel.name, r.number))
    if hostel_id:
        rooms = [r for r in rooms if str(r.hostel.id) == hostel_id]
    if status == "Vacant":
        rooms = [r for r in rooms if r.free_count() > 0]
    elif status == "Full":
        rooms = [r for r in rooms if r.free_count() == 0]
    elif status in ("Active", "Inactive"):
        rooms = [r for r in rooms if r.status == status]
    return render(
        request, "inventory.html", user=user, hostels=hostels, rooms=rooms,
        hostel_id=hostel_id, status=status,
    )
