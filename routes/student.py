from fastapi import APIRouter, Depends, Form, Request
from models import Application, Allocation, Hostel, Room, RoomChange, Checkout, Notification
from helpers import (
    render, go, flash, login_required, notify, current_cycle, window_open,
    active_allocation, bed_text, eligibility_problem, find,
)

router = APIRouter(prefix="/student")
student_only = login_required("student")


def get_application(user, cycle):
    if cycle is None:
        return None
    return (
        Application.objects(user=user, cycle=cycle, status__ne="withdrawn")
        .order_by("-id")
        .first()
    )


def shown_status(application, cycle):
    if application is None:
        return None
    if application.status == "allocated":
        allocation = Allocation.objects(application=application).first()
        if allocation and allocation.status == "Cancelled":
            return "checked out"
    if application.status in ("allocated", "unallocated") and not cycle.published:
        return "submitted"
    return application.status


@router.get("")
def home(request: Request, user=Depends(student_only)):
    cycle = current_cycle()
    application = get_application(user, cycle)
    allocation = active_allocation(user)
    if allocation and allocation.status != "Published":
        allocation = None
    change = RoomChange.objects(user=user).order_by("-id").first()
    checkout = Checkout.objects(user=user).order_by("-id").first()
    unread = Notification.objects(user=user, read=False).count()
    return render(
        request, "student_home.html", user=user, cycle=cycle, application=application,
        status=shown_status(application, cycle), allocation=allocation, change=change,
        checkout=checkout, unread=unread, is_open=window_open(cycle),
        place=bed_text(allocation.bed) if allocation else None,
    )


@router.get("/apply")
def apply_page(request: Request, user=Depends(student_only)):
    cycle = current_cycle()
    application = get_application(user, cycle)
    hostels = list(Hostel.objects(status="Active"))
    return render(
        request, "apply.html", user=user, cycle=cycle, application=application,
        hostels=hostels, is_open=window_open(cycle),
        status=shown_status(application, cycle),
    )


@router.post("/apply")
def apply(
    request: Request,
    year: str = Form(""),
    hostel_id: str = Form(""),
    action: str = Form("submit"),
    user=Depends(student_only),
):
    cycle = current_cycle()
    if not window_open(cycle):
        flash(request, "Applications are not open right now")
        return go("/student/apply")
    problem = eligibility_problem(user)
    if problem:
        flash(request, problem)
        return go("/student/apply")
    application = get_application(user, cycle)
    if application and application.status not in ("draft", "submitted"):
        flash(request, "Your application is already processed")
        return go("/student/apply")
    if year and (not year.isdigit() or not 1 <= int(year) <= 4):
        flash(request, "Year of study must be between 1 and 4")
        return go("/student/apply")
    if action == "submit" and not year:
        flash(request, "Please select your year before submitting")
        return go("/student/apply")

    if application is None:
        application = Application(user=user, cycle=cycle)
    application.year = int(year) if year else None
    application.hostel = find(Hostel, hostel_id)
    if action == "draft":
        application.status = "draft"
        flash(request, "Draft saved, you can submit it later")
    else:
        application.status = "submitted"
        notify(user, "Your hostel application has been submitted")
        flash(request, "Application submitted")
    application.save()
    return go("/student/apply")


@router.post("/withdraw")
def withdraw(request: Request, user=Depends(student_only)):
    cycle = current_cycle()
    application = get_application(user, cycle)
    if application is None or application.status != "submitted" or cycle.allocation_run:
        flash(request, "You cannot withdraw now")
        return go("/student")
    application.status = "withdrawn"
    application.save()
    flash(request, "Application withdrawn")
    return go("/student")


@router.get("/allocation")
def allocation_page(request: Request, user=Depends(student_only)):
    allocation = active_allocation(user)
    if allocation and allocation.status != "Published":
        allocation = None
    return render(request, "student_allocation.html", user=user, allocation=allocation)


@router.get("/room-change")
def room_change_page(request: Request, user=Depends(student_only)):
    allocation = active_allocation(user)
    if allocation is None or allocation.status != "Published":
        flash(request, "You need an allocated room to request a change")
        return go("/student")
    rooms = [r for r in Room.objects if r.is_active() and r.free_count() > 0 and r.id != allocation.bed.room.id]
    requests = list(RoomChange.objects(user=user).order_by("-id"))
    pending = any(r.status == "Pending" for r in requests)
    return render(request, "room_change.html", user=user, rooms=rooms, requests=requests, pending=pending)


@router.post("/room-change")
def room_change(
    request: Request,
    room_id: str = Form(...),
    reason: str = Form(""),
    user=Depends(student_only),
):
    allocation = active_allocation(user)
    if allocation is None or allocation.status != "Published":
        flash(request, "You need an allocated room to request a change")
        return go("/student")
    if RoomChange.objects(user=user, status="Pending").first():
        flash(request, "You already have a pending request")
        return go("/student/room-change")
    if not reason.strip():
        flash(request, "Please write a reason")
        return go("/student/room-change")
    room = find(Room, room_id)
    if room is None or not room.is_active() or room.id == allocation.bed.room.id:
        flash(request, "Choose a different room")
        return go("/student/room-change")

    RoomChange(user=user, allocation=allocation, requested_room=room, reason=reason.strip()).save()
    wardens = [room.hostel.warden, allocation.bed.room.hostel.warden]
    done = []
    for warden in wardens:
        if warden and warden.id not in done:
            notify(warden, user.name + " has requested a room change")
            done.append(warden.id)
    notify(user, "Your room change request has been sent")
    flash(request, "Request sent to the warden")
    return go("/student/room-change")


@router.get("/checkout")
def checkout_page(request: Request, user=Depends(student_only)):
    allocation = active_allocation(user)
    if allocation and allocation.status != "Published":
        allocation = None
    checkouts = list(Checkout.objects(user=user).order_by("-id"))
    started = any(c.status == "Initiated" for c in checkouts)
    return render(
        request, "student_checkout.html", user=user, allocation=allocation, checkouts=checkouts, started=started,
    )


@router.post("/checkout")
def start_checkout(request: Request, user=Depends(student_only)):
    allocation = active_allocation(user)
    if allocation is None or allocation.status != "Published":
        flash(request, "You do not have a room to vacate")
        return go("/student/checkout")
    if Checkout.objects(user=user, status="Initiated").first():
        flash(request, "Checkout is already started")
        return go("/student/checkout")
    Checkout(user=user, allocation=allocation).save()
    warden = allocation.bed.room.hostel.warden
    if warden:
        notify(warden, user.name + " has started the checkout")
    flash(request, "Checkout started, wait for the warden to confirm")
    return go("/student/checkout")
