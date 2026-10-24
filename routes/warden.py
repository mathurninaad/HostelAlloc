from datetime import datetime
from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session
from database import get_db
from models import Hostel, Room, Bed, Allocation, Application, RoomChange, Checkout, Notification
from helpers import (
    render, go, flash, login_required, notify, log, current_cycle, find_vacant_bed, bed_text,
)

router = APIRouter(prefix="/warden")
warden_only = login_required("warden")


def my_hostel_ids(db, user):
    return [h.id for h in db.query(Hostel).filter_by(warden_id=user.id).all()]


def my_allocations(db, hostel_ids):
    return (
        db.query(Allocation)
        .join(Bed, Allocation.bed_id == Bed.id)
        .join(Room, Bed.room_id == Room.id)
        .filter(Room.hostel_id.in_(hostel_ids))
        .order_by(Allocation.id)
        .all()
    )


def involves(change, hostel_ids):
    return (
        change.requested_room.hostel_id in hostel_ids
        or change.allocation.bed.room.hostel_id in hostel_ids
    )


def my_changes(db, hostel_ids):
    changes = db.query(RoomChange).order_by(RoomChange.id.desc()).all()
    return [c for c in changes if involves(c, hostel_ids)]


@router.get("")
def home(request: Request, user=Depends(warden_only), db: Session = Depends(get_db)):
    ids = my_hostel_ids(db, user)
    hostels = db.query(Hostel).filter(Hostel.id.in_(ids)).all()
    allocations = my_allocations(db, ids)
    to_verify = len([a for a in allocations if a.status == "Pending Verification"])
    changes = len([c for c in my_changes(db, ids) if c.status == "Pending"])
    checkouts = len([c for c in db.query(Checkout).filter_by(status="Initiated").all()
                     if c.allocation.bed.room.hostel_id in ids])
    unread = db.query(Notification).filter_by(user_id=user.id, read=False).count()
    return render(
        request, "warden_home.html", user=user, hostels=hostels, to_verify=to_verify,
        changes=changes, checkouts=checkouts, unread=unread,
    )


@router.get("/applications")
def applications(request: Request, user=Depends(warden_only), db: Session = Depends(get_db)):
    cycle = current_cycle(db)
    items = []
    if cycle:
        items = db.query(Application).filter(
            Application.cycle_id == cycle.id, Application.status != "draft"
        ).order_by(Application.id).all()
    ids = my_hostel_ids(db, user)
    return render(request, "warden_applications.html", user=user, items=items, cycle=cycle, ids=ids)


@router.get("/allocations")
def allocations(request: Request, user=Depends(warden_only), db: Session = Depends(get_db)):
    items = my_allocations(db, my_hostel_ids(db, user))
    return render(request, "warden_allocations.html", user=user, items=items)


@router.post("/verify/{allocation_id}")
def verify(allocation_id: int, request: Request, user=Depends(warden_only), db: Session = Depends(get_db)):
    ids = my_hostel_ids(db, user)
    allocation = db.get(Allocation, allocation_id)
    if allocation is None or allocation.bed.room.hostel_id not in ids or allocation.status != "Pending Verification":
        flash(request, "Cannot verify this allocation")
        return go("/warden/allocations")
    allocation.status = "Verified"
    log(db, user.id, "Verified allocation of " + allocation.user.name)
    db.commit()
    flash(request, "Allocation verified")
    return go("/warden/allocations")


@router.post("/verify-all")
def verify_all(request: Request, user=Depends(warden_only), db: Session = Depends(get_db)):
    count = 0
    for allocation in my_allocations(db, my_hostel_ids(db, user)):
        if allocation.status == "Pending Verification":
            allocation.status = "Verified"
            count += 1
    log(db, user.id, "Verified " + str(count) + " allocations")
    db.commit()
    flash(request, str(count) + " allocations verified")
    return go("/warden/allocations")


@router.get("/changes")
def changes(request: Request, user=Depends(warden_only), db: Session = Depends(get_db)):
    items = my_changes(db, my_hostel_ids(db, user))
    rooms = [r for r in db.query(Room).all() if r.free_count() > 0]
    return render(request, "warden_changes.html", user=user, items=items, rooms=rooms)


@router.post("/changes/{change_id}/approve")
def approve(
    change_id: int,
    request: Request,
    room_id: int = Form(...),
    user=Depends(warden_only),
    db: Session = Depends(get_db),
):
    change = db.get(RoomChange, change_id)
    if change is None or change.status != "Pending" or not involves(change, my_hostel_ids(db, user)):
        flash(request, "Cannot decide this request")
        return go("/warden/changes")
    allocation = change.allocation
    if allocation.status != "Published":
        flash(request, "Student does not have an active allocation")
        return go("/warden/changes")
    new_bed = find_vacant_bed(db, room_id=room_id)
    if new_bed is None:
        flash(request, "No vacant bed in that room, choose another room or reject the request")
        return go("/warden/changes")

    allocation.bed.occupied = False
    new_bed.occupied = True
    allocation.bed_id = new_bed.id
    change.status = "Approved"
    change.approver_id = user.id
    change.decided_at = datetime.now()
    notify(db, change.user_id, "Your room change request is approved. New room: " + bed_text(new_bed))
    log(db, user.id, "Approved room change of " + change.user.name)
    db.commit()
    flash(request, "Request approved")
    return go("/warden/changes")


@router.post("/changes/{change_id}/reject")
def reject(
    change_id: int,
    request: Request,
    note: str = Form(""),
    user=Depends(warden_only),
    db: Session = Depends(get_db),
):
    change = db.get(RoomChange, change_id)
    if change is None or change.status != "Pending" or not involves(change, my_hostel_ids(db, user)):
        flash(request, "Cannot decide this request")
        return go("/warden/changes")
    if not note.strip():
        flash(request, "Please write a reason for rejecting")
        return go("/warden/changes")
    change.status = "Rejected"
    change.decision_note = note.strip()
    change.approver_id = user.id
    change.decided_at = datetime.now()
    notify(db, change.user_id, "Your room change request is rejected. Reason: " + note.strip())
    log(db, user.id, "Rejected room change of " + change.user.name)
    db.commit()
    flash(request, "Request rejected")
    return go("/warden/changes")


@router.get("/checkouts")
def checkouts(request: Request, user=Depends(warden_only), db: Session = Depends(get_db)):
    ids = my_hostel_ids(db, user)
    items = [c for c in db.query(Checkout).order_by(Checkout.id.desc()).all()
             if c.allocation.bed.room.hostel_id in ids]
    students = [a for a in my_allocations(db, ids) if a.status == "Published"]
    started = [c.allocation_id for c in items if c.status == "Initiated"]
    return render(request, "warden_checkouts.html", user=user, items=items, students=students, started=started)


@router.post("/checkouts/start/{allocation_id}")
def start(allocation_id: int, request: Request, user=Depends(warden_only), db: Session = Depends(get_db)):
    allocation = db.get(Allocation, allocation_id)
    if allocation is None or allocation.bed.room.hostel_id not in my_hostel_ids(db, user) \
            or allocation.status != "Published":
        flash(request, "Cannot start checkout")
        return go("/warden/checkouts")
    if db.query(Checkout).filter_by(allocation_id=allocation.id, status="Initiated").first():
        flash(request, "Checkout is already started")
        return go("/warden/checkouts")
    db.add(Checkout(user_id=allocation.user_id, allocation_id=allocation.id))
    notify(db, allocation.user_id, "The warden has started your hostel checkout")
    db.commit()
    flash(request, "Checkout started")
    return go("/warden/checkouts")


@router.post("/checkouts/{checkout_id}/confirm")
def confirm(checkout_id: int, request: Request, user=Depends(warden_only), db: Session = Depends(get_db)):
    checkout = db.get(Checkout, checkout_id)
    if checkout is None or checkout.status != "Initiated" \
            or checkout.allocation.bed.room.hostel_id not in my_hostel_ids(db, user):
        flash(request, "Cannot confirm this checkout")
        return go("/warden/checkouts")
    allocation = checkout.allocation
    allocation.bed.occupied = False
    allocation.status = "Checked Out"
    checkout.status = "Confirmed"
    checkout.confirmed_at = datetime.now()
    notify(db, checkout.user_id, "Your hostel checkout is confirmed")
    log(db, user.id, "Confirmed checkout of " + checkout.user.name)
    db.commit()
    flash(request, "Checkout confirmed, bed is vacant now")
    return go("/warden/checkouts")
