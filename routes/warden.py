from datetime import datetime
from fastapi import APIRouter, Depends, Form, Request
from models import Hostel, Room, Bed, Allocation, Application, RoomChange, Checkout, Notification
from helpers import (
    render, go, flash, login_required, notify, log, current_cycle, find_vacant_bed, bed_text, find,
)

router = APIRouter(prefix="/warden")
warden_only = login_required("warden")


def my_hostels(user):
    return list(Hostel.objects(warden=user))


def my_hostel_ids(user):
    return [h.id for h in my_hostels(user)]


def hostel_of(allocation):
    return allocation.bed.room.hostel


def my_allocations(hostel_ids):
    items = Allocation.objects.order_by("id")
    return [a for a in items if hostel_of(a).id in hostel_ids]


def involves(change, hostel_ids):
    return (
        change.requested_room.hostel.id in hostel_ids
        or hostel_of(change.allocation).id in hostel_ids
    )


def my_changes(hostel_ids):
    changes = RoomChange.objects.order_by("-id")
    return [c for c in changes if involves(c, hostel_ids)]


@router.get("")
def home(request: Request, user=Depends(warden_only)):
    ids = my_hostel_ids(user)
    hostels = my_hostels(user)
    allocations = my_allocations(ids)
    to_verify = len([a for a in allocations if a.status == "Pending Verification"])
    changes = len([c for c in my_changes(ids) if c.status == "Pending"])
    checkouts = len([c for c in Checkout.objects(status="Initiated") if hostel_of(c.allocation).id in ids])
    unread = Notification.objects(user=user, read=False).count()
    cycle = current_cycle()
    applications = 0
    if cycle:
        applications = Application.objects(
            cycle=cycle, status__in=["submitted", "allocated", "unallocated"]
        ).count()
    return render(
        request, "warden_home.html", user=user, hostels=hostels, to_verify=to_verify,
        changes=changes, checkouts=checkouts, unread=unread, applications=applications,
    )


@router.get("/applications")
def applications(request: Request, user=Depends(warden_only)):
    cycle = current_cycle()
    items = []
    if cycle:
        items = list(
            Application.objects(cycle=cycle, status__in=["submitted", "allocated", "unallocated"]).order_by("id")
        )
    ids = my_hostel_ids(user)
    return render(request, "warden_applications.html", user=user, items=items, cycle=cycle, ids=ids)


@router.get("/allocations")
def allocations(request: Request, user=Depends(warden_only)):
    items = my_allocations(my_hostel_ids(user))
    return render(request, "warden_allocations.html", user=user, items=items)


@router.post("/verify/{allocation_id}")
def verify(allocation_id: str, request: Request, user=Depends(warden_only)):
    ids = my_hostel_ids(user)
    allocation = find(Allocation, allocation_id)
    if allocation is None or hostel_of(allocation).id not in ids or allocation.status != "Pending Verification":
        flash(request, "Cannot verify this allocation")
        return go("/warden/allocations")
    allocation.status = "Verified"
    allocation.save()
    log(user, "Verified allocation of " + allocation.user.name)
    flash(request, "Allocation verified")
    return go("/warden/allocations")


@router.post("/verify-all")
def verify_all(request: Request, user=Depends(warden_only)):
    count = 0
    for allocation in my_allocations(my_hostel_ids(user)):
        if allocation.status == "Pending Verification":
            allocation.status = "Verified"
            allocation.save()
            count += 1
    log(user, "Verified " + str(count) + " allocations")
    flash(request, str(count) + " allocations verified")
    return go("/warden/allocations")


@router.get("/changes")
def changes(request: Request, user=Depends(warden_only)):
    items = my_changes(my_hostel_ids(user))
    rooms = [r for r in Room.objects if r.free_count() > 0]
    return render(request, "warden_changes.html", user=user, items=items, rooms=rooms)


@router.post("/changes/{change_id}/approve")
def approve(
    change_id: str,
    request: Request,
    room_id: str = Form(...),
    user=Depends(warden_only),
):
    change = find(RoomChange, change_id)
    if change is None or change.status != "Pending" or not involves(change, my_hostel_ids(user)):
        flash(request, "Cannot decide this request")
        return go("/warden/changes")
    allocation = change.allocation
    if allocation.status != "Published":
        flash(request, "Student does not have an active allocation")
        return go("/warden/changes")
    room = find(Room, room_id)
    new_bed = find_vacant_bed(room=room) if room else None
    if new_bed is None:
        flash(request, "No vacant bed in that room, choose another room or reject the request")
        return go("/warden/changes")

    old_bed = allocation.bed
    old_bed.occupied = False
    old_bed.save()
    new_bed.occupied = True
    new_bed.save()
    allocation.bed = new_bed
    allocation.save()
    change.status = "Approved"
    change.approver = user
    change.decided_at = datetime.now()
    change.save()
    notify(change.user, "Your room change request is approved. New room: " + bed_text(new_bed))
    log(user, "Approved room change of " + change.user.name)
    flash(request, "Request approved")
    return go("/warden/changes")


@router.post("/changes/{change_id}/reject")
def reject(
    change_id: str,
    request: Request,
    note: str = Form(""),
    user=Depends(warden_only),
):
    change = find(RoomChange, change_id)
    if change is None or change.status != "Pending" or not involves(change, my_hostel_ids(user)):
        flash(request, "Cannot decide this request")
        return go("/warden/changes")
    if not note.strip():
        flash(request, "Please write a reason for rejecting")
        return go("/warden/changes")
    change.status = "Rejected"
    change.decision_note = note.strip()
    change.approver = user
    change.decided_at = datetime.now()
    change.save()
    notify(change.user, "Your room change request is rejected. Reason: " + note.strip())
    log(user, "Rejected room change of " + change.user.name)
    flash(request, "Request rejected")
    return go("/warden/changes")


@router.get("/checkouts")
def checkouts(request: Request, user=Depends(warden_only)):
    ids = my_hostel_ids(user)
    items = [c for c in Checkout.objects.order_by("-id") if hostel_of(c.allocation).id in ids]
    students = [a for a in my_allocations(ids) if a.status == "Published"]
    started = [c.allocation.id for c in items if c.status == "Initiated"]
    return render(request, "warden_checkouts.html", user=user, items=items, students=students, started=started)


@router.post("/checkouts/start/{allocation_id}")
def start(allocation_id: str, request: Request, user=Depends(warden_only)):
    allocation = find(Allocation, allocation_id)
    if allocation is None or hostel_of(allocation).id not in my_hostel_ids(user) \
            or allocation.status != "Published":
        flash(request, "Cannot start checkout")
        return go("/warden/checkouts")
    if Checkout.objects(allocation=allocation, status="Initiated").first():
        flash(request, "Checkout is already started")
        return go("/warden/checkouts")
    Checkout(user=allocation.user, allocation=allocation).save()
    notify(allocation.user, "The warden has started your hostel checkout")
    flash(request, "Checkout started")
    return go("/warden/checkouts")


@router.post("/checkouts/{checkout_id}/confirm")
def confirm(checkout_id: str, request: Request, user=Depends(warden_only)):
    checkout = find(Checkout, checkout_id)
    if checkout is None or checkout.status != "Initiated" \
            or hostel_of(checkout.allocation).id not in my_hostel_ids(user):
        flash(request, "Cannot confirm this checkout")
        return go("/warden/checkouts")
    allocation = checkout.allocation
    bed = allocation.bed
    bed.occupied = False
    bed.save()
    allocation.status = "Cancelled"
    allocation.save()
    checkout.status = "Confirmed"
    checkout.confirmed_at = datetime.now()
    checkout.save()
    notify(checkout.user, "Your hostel checkout is confirmed")
    log(user, "Confirmed checkout of " + checkout.user.name)
    flash(request, "Checkout confirmed, bed is vacant now")
    return go("/warden/checkouts")
