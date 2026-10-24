from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session
from database import get_db
from models import Application, Hostel, Room, RoomChange, Checkout, Notification
from helpers import (
    render, go, flash, login_required, notify, current_cycle, window_open,
    active_allocation, bed_text,
)

router = APIRouter(prefix="/student")
student_only = login_required("student")

CATEGORIES = ["General", "OBC", "SC", "ST", "PwD"]


def get_application(db, user_id, cycle):
    if cycle is None:
        return None
    return (
        db.query(Application)
        .filter(Application.user_id == user_id, Application.cycle_id == cycle.id, Application.status != "withdrawn")
        .order_by(Application.id.desc())
        .first()
    )


def shown_status(application, cycle):
    if application is None:
        return None
    if application.status in ("allocated", "unallocated") and not cycle.published:
        return "submitted"
    return application.status


@router.get("")
def home(request: Request, user=Depends(student_only), db: Session = Depends(get_db)):
    cycle = current_cycle(db)
    application = get_application(db, user.id, cycle)
    allocation = active_allocation(db, user.id)
    if allocation and allocation.status != "Published":
        allocation = None
    change = db.query(RoomChange).filter_by(user_id=user.id).order_by(RoomChange.id.desc()).first()
    checkout = db.query(Checkout).filter_by(user_id=user.id).order_by(Checkout.id.desc()).first()
    unread = db.query(Notification).filter_by(user_id=user.id, read=False).count()
    return render(
        request, "student_home.html", user=user, cycle=cycle, application=application,
        status=shown_status(application, cycle), allocation=allocation, change=change,
        checkout=checkout, unread=unread, is_open=window_open(cycle),
        place=bed_text(allocation.bed) if allocation else None,
    )


@router.get("/apply")
def apply_page(request: Request, user=Depends(student_only), db: Session = Depends(get_db)):
    cycle = current_cycle(db)
    application = get_application(db, user.id, cycle)
    hostels = db.query(Hostel).all()
    return render(
        request, "apply.html", user=user, cycle=cycle, application=application,
        hostels=hostels, categories=CATEGORIES, is_open=window_open(cycle),
        status=shown_status(application, cycle),
    )


@router.post("/apply")
def apply(
    request: Request,
    action: str = Form(...),
    year: str = Form(""),
    category: str = Form(""),
    hostel_id: str = Form(""),
    user=Depends(student_only),
    db: Session = Depends(get_db),
):
    cycle = current_cycle(db)
    if not window_open(cycle):
        flash(request, "Applications are not open right now")
        return go("/student/apply")
    if active_allocation(db, user.id):
        flash(request, "You already have a room allocated")
        return go("/student/apply")
    application = get_application(db, user.id, cycle)
    if application and application.status not in ("draft", "submitted"):
        flash(request, "Your application is already processed")
        return go("/student/apply")
    if action == "submit" and (not year or not category):
        flash(request, "Please fill year of study and category")
        return go("/student/apply")
    if action == "draft" and application and application.status == "submitted":
        flash(request, "Your application is already submitted")
        return go("/student/apply")

    if application is None:
        application = Application(user_id=user.id, cycle_id=cycle.id)
        db.add(application)
    already_submitted = application.status == "submitted"
    application.year = int(year) if year else None
    application.category = category or None
    application.hostel_id = int(hostel_id) if hostel_id else None

    if action == "submit":
        application.status = "submitted"
        if not already_submitted:
            notify(db, user.id, "Your hostel application has been submitted")
            flash(request, "Application submitted")
        else:
            flash(request, "Application updated")
    else:
        application.status = "draft"
        flash(request, "Draft saved")
    db.commit()
    return go("/student/apply")


@router.post("/withdraw")
def withdraw(request: Request, user=Depends(student_only), db: Session = Depends(get_db)):
    cycle = current_cycle(db)
    application = get_application(db, user.id, cycle)
    if application is None or application.status not in ("draft", "submitted") or cycle.allocation_run:
        flash(request, "You cannot withdraw now")
        return go("/student")
    application.status = "withdrawn"
    db.commit()
    flash(request, "Application withdrawn")
    return go("/student")


@router.get("/allocation")
def allocation_page(request: Request, user=Depends(student_only), db: Session = Depends(get_db)):
    allocation = active_allocation(db, user.id)
    if allocation and allocation.status != "Published":
        allocation = None
    return render(request, "student_allocation.html", user=user, allocation=allocation)


@router.get("/room-change")
def room_change_page(request: Request, user=Depends(student_only), db: Session = Depends(get_db)):
    allocation = active_allocation(db, user.id)
    if allocation is None or allocation.status != "Published":
        flash(request, "You need an allocated room to request a change")
        return go("/student")
    rooms = [r for r in db.query(Room).all() if r.free_count() > 0 and r.id != allocation.bed.room_id]
    requests = db.query(RoomChange).filter_by(user_id=user.id).order_by(RoomChange.id.desc()).all()
    pending = any(r.status == "Pending" for r in requests)
    return render(request, "room_change.html", user=user, rooms=rooms, requests=requests, pending=pending)


@router.post("/room-change")
def room_change(
    request: Request,
    room_id: int = Form(...),
    reason: str = Form(""),
    user=Depends(student_only),
    db: Session = Depends(get_db),
):
    allocation = active_allocation(db, user.id)
    if allocation is None or allocation.status != "Published":
        flash(request, "You need an allocated room to request a change")
        return go("/student")
    if db.query(RoomChange).filter_by(user_id=user.id, status="Pending").first():
        flash(request, "You already have a pending request")
        return go("/student/room-change")
    if not reason.strip():
        flash(request, "Please write a reason")
        return go("/student/room-change")
    room = db.get(Room, room_id)
    if room is None or room.id == allocation.bed.room_id:
        flash(request, "Choose a different room")
        return go("/student/room-change")

    db.add(RoomChange(user_id=user.id, allocation_id=allocation.id, requested_room_id=room.id, reason=reason.strip()))
    wardens = {room.hostel.warden_id, allocation.bed.room.hostel.warden_id}
    for warden_id in wardens:
        if warden_id:
            notify(db, warden_id, user.name + " has requested a room change")
    notify(db, user.id, "Your room change request has been sent")
    db.commit()
    flash(request, "Request sent to the warden")
    return go("/student/room-change")


@router.get("/checkout")
def checkout_page(request: Request, user=Depends(student_only), db: Session = Depends(get_db)):
    allocation = active_allocation(db, user.id)
    if allocation and allocation.status != "Published":
        allocation = None
    checkouts = db.query(Checkout).filter_by(user_id=user.id).order_by(Checkout.id.desc()).all()
    started = any(c.status == "Initiated" for c in checkouts)
    return render(
        request, "student_checkout.html", user=user, allocation=allocation, checkouts=checkouts, started=started,
    )


@router.post("/checkout")
def start_checkout(request: Request, user=Depends(student_only), db: Session = Depends(get_db)):
    allocation = active_allocation(db, user.id)
    if allocation is None or allocation.status != "Published":
        flash(request, "You do not have a room to vacate")
        return go("/student/checkout")
    if db.query(Checkout).filter_by(user_id=user.id, status="Initiated").first():
        flash(request, "Checkout is already started")
        return go("/student/checkout")
    db.add(Checkout(user_id=user.id, allocation_id=allocation.id))
    warden_id = allocation.bed.room.hostel.warden_id
    if warden_id:
        notify(db, warden_id, user.name + " has started the checkout")
    db.commit()
    flash(request, "Checkout started, wait for the warden to confirm")
    return go("/student/checkout")
