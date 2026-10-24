from datetime import date, timedelta
from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session
from database import get_db
from models import (
    Hostel, Room, Bed, User, Cycle, Criteria, Application, Allocation, RoomChange,
)
from helpers import (
    render, go, flash, login_required, notify, log, current_cycle, window_open, ACTIVE_STATUSES,
)
from allocation import run_allocation

router = APIRouter(prefix="/office")
office_only = login_required("office")


def get_criteria(db, cycle):
    if cycle is None:
        return None
    return db.query(Criteria).filter_by(cycle_id=cycle.id).first()


@router.get("")
def home(request: Request, user=Depends(office_only), db: Session = Depends(get_db)):
    cycle = current_cycle(db)
    hostels = db.query(Hostel).all()
    total = sum(h.total_beds() for h in hostels)
    occupied = sum(h.occupied_beds() for h in hostels)
    applications = 0
    submitted = 0
    if cycle:
        applications = db.query(Application).filter(
            Application.cycle_id == cycle.id, Application.status != "withdrawn"
        ).count()
        submitted = db.query(Application).filter(
            Application.cycle_id == cycle.id, Application.status.in_(["submitted", "allocated", "unallocated"])
        ).count()
    pending_changes = db.query(RoomChange).filter_by(status="Pending").count()
    return render(
        request, "office_home.html", user=user, cycle=cycle, is_open=window_open(cycle),
        hostels=len(hostels), total=total, occupied=occupied, applications=applications,
        submitted=submitted, pending_changes=pending_changes,
    )


@router.get("/hostels")
def hostels(request: Request, user=Depends(office_only), db: Session = Depends(get_db)):
    items = db.query(Hostel).all()
    wardens = db.query(User).filter_by(role="warden", active=True).all()
    return render(request, "hostels.html", user=user, items=items, wardens=wardens)


@router.post("/hostels")
def add_hostel(
    request: Request,
    name: str = Form(...),
    floors: int = Form(1),
    warden_id: str = Form(""),
    user=Depends(office_only),
    db: Session = Depends(get_db),
):
    name = name.strip()
    if not name or floors < 1:
        flash(request, "Enter a hostel name and number of floors")
        return go("/office/hostels")
    if db.query(Hostel).filter_by(name=name).first():
        flash(request, "A hostel with this name already exists")
        return go("/office/hostels")
    db.add(Hostel(name=name, floors=floors, warden_id=int(warden_id) if warden_id else None))
    log(db, user.id, "Created hostel " + name)
    db.commit()
    flash(request, "Hostel added")
    return go("/office/hostels")


@router.get("/hostels/{hostel_id}")
def hostel_page(hostel_id: int, request: Request, user=Depends(office_only), db: Session = Depends(get_db)):
    hostel = db.get(Hostel, hostel_id)
    if hostel is None:
        flash(request, "Hostel not found")
        return go("/office/hostels")
    wardens = db.query(User).filter_by(role="warden", active=True).all()
    return render(request, "hostel_detail.html", user=user, hostel=hostel, wardens=wardens)


@router.post("/hostels/{hostel_id}/edit")
def edit_hostel(
    hostel_id: int,
    request: Request,
    name: str = Form(...),
    floors: int = Form(1),
    warden_id: str = Form(""),
    user=Depends(office_only),
    db: Session = Depends(get_db),
):
    hostel = db.get(Hostel, hostel_id)
    other = db.query(Hostel).filter(Hostel.name == name.strip(), Hostel.id != hostel_id).first()
    if hostel is None or not name.strip() or floors < 1 or other:
        flash(request, "Could not update the hostel")
        return go("/office/hostels/" + str(hostel_id))
    hostel.name = name.strip()
    hostel.floors = floors
    hostel.warden_id = int(warden_id) if warden_id else None
    log(db, user.id, "Edited hostel " + hostel.name)
    db.commit()
    flash(request, "Hostel updated")
    return go("/office/hostels/" + str(hostel_id))


@router.post("/hostels/{hostel_id}/rooms")
def add_room(
    hostel_id: int,
    request: Request,
    floor: int = Form(0),
    number: str = Form(...),
    capacity: int = Form(...),
    room_type: str = Form("Standard"),
    user=Depends(office_only),
    db: Session = Depends(get_db),
):
    hostel = db.get(Hostel, hostel_id)
    number = number.strip()
    back = "/office/hostels/" + str(hostel_id)
    if hostel is None or not number or capacity < 1 or capacity > 10:
        flash(request, "Enter a room number and a capacity between 1 and 10")
        return go(back)
    if db.query(Room).filter_by(hostel_id=hostel_id, number=number).first():
        flash(request, "This room number already exists in the hostel")
        return go(back)
    room = Room(hostel_id=hostel_id, floor=floor, number=number, capacity=capacity, room_type=room_type)
    db.add(room)
    db.flush()
    for i in range(1, capacity + 1):
        db.add(Bed(room_id=room.id, number=i))
    log(db, user.id, "Added room " + number + " to " + hostel.name)
    db.commit()
    flash(request, "Room added")
    return go(back)


@router.post("/rooms/{room_id}/edit")
def edit_room(
    room_id: int,
    request: Request,
    capacity: int = Form(...),
    room_type: str = Form("Standard"),
    user=Depends(office_only),
    db: Session = Depends(get_db),
):
    room = db.get(Room, room_id)
    if room is None:
        flash(request, "Room not found")
        return go("/office/hostels")
    back = "/office/hostels/" + str(room.hostel_id)
    if capacity < 1 or capacity > 10:
        flash(request, "Capacity must be between 1 and 10")
        return go(back)
    occupied = len([b for b in room.beds if b.occupied])
    if capacity < occupied:
        flash(request, "Room has " + str(occupied) + " students, capacity cannot be less than that")
        return go(back)
    if capacity > len(room.beds):
        for i in range(len(room.beds) + 1, capacity + 1):
            db.add(Bed(room_id=room.id, number=i))
    else:
        free_beds = [b for b in room.beds if not b.occupied]
        free_beds.sort(key=lambda b: b.number, reverse=True)
        for bed in free_beds[: len(room.beds) - capacity]:
            db.delete(bed)
    room.capacity = capacity
    room.room_type = room_type

    bed_ids = [b.id for b in room.beds]
    students = db.query(Allocation).filter(
        Allocation.bed_id.in_(bed_ids), Allocation.status.in_(ACTIVE_STATUSES)
    ).all()
    for allocation in students:
        notify(db, allocation.user_id, "Details of your room " + room.number + " were updated by the hostel office")
    log(db, user.id, "Edited room " + room.number + " of " + room.hostel.name)
    db.commit()
    flash(request, "Room updated")
    return go(back)


@router.get("/cycle")
def cycle_page(request: Request, user=Depends(office_only), db: Session = Depends(get_db)):
    cycle = current_cycle(db)
    return render(
        request, "cycle.html", user=user, cycle=cycle, criteria=get_criteria(db, cycle),
        is_open=window_open(cycle), today=date.today(),
    )


@router.post("/cycle/new")
def new_cycle(
    request: Request,
    name: str = Form(...),
    start_date: date = Form(...),
    end_date: date = Form(...),
    user=Depends(office_only),
    db: Session = Depends(get_db),
):
    cycle = current_cycle(db)
    if cycle and not cycle.published:
        flash(request, "Finish the current cycle first")
        return go("/office/cycle")
    if end_date < start_date or not name.strip():
        flash(request, "Check the name and dates")
        return go("/office/cycle")
    db.add(Cycle(name=name.strip(), start_date=start_date, end_date=end_date))
    log(db, user.id, "Created cycle " + name.strip())
    db.commit()
    flash(request, "New cycle created")
    return go("/office/cycle")


@router.post("/cycle/dates")
def change_dates(
    request: Request,
    start_date: date = Form(...),
    end_date: date = Form(...),
    user=Depends(office_only),
    db: Session = Depends(get_db),
):
    cycle = current_cycle(db)
    if cycle is None or cycle.allocation_run:
        flash(request, "Dates cannot be changed now")
        return go("/office/cycle")
    if end_date < start_date:
        flash(request, "End date is before start date")
        return go("/office/cycle")
    cycle.start_date = start_date
    cycle.end_date = end_date
    log(db, user.id, "Changed application window of " + cycle.name)
    db.commit()
    flash(request, "Dates updated")
    return go("/office/cycle")


@router.post("/cycle/close")
def close_window(request: Request, user=Depends(office_only), db: Session = Depends(get_db)):
    cycle = current_cycle(db)
    if cycle is None or cycle.allocation_run:
        flash(request, "Cannot close now")
        return go("/office/cycle")
    cycle.end_date = date.today() - timedelta(days=1)
    if cycle.start_date > cycle.end_date:
        cycle.start_date = cycle.end_date
    log(db, user.id, "Closed application window of " + cycle.name)
    db.commit()
    flash(request, "Application window closed")
    return go("/office/cycle")


@router.post("/criteria")
def save_criteria(
    request: Request,
    year_order: str = Form("senior"),
    use_preference: str = Form(""),
    user=Depends(office_only),
    db: Session = Depends(get_db),
):
    cycle = current_cycle(db)
    if cycle is None or cycle.allocation_run:
        flash(request, "Criteria cannot be changed now")
        return go("/office/cycle")
    criteria = get_criteria(db, cycle)
    if criteria is None:
        criteria = Criteria(cycle_id=cycle.id)
        db.add(criteria)
    criteria.year_order = year_order
    criteria.use_preference = use_preference == "yes"
    log(db, user.id, "Saved allocation criteria for " + cycle.name)
    db.commit()
    flash(request, "Criteria saved")
    return go("/office/cycle")


@router.get("/allocation")
def allocation_page(request: Request, user=Depends(office_only), db: Session = Depends(get_db)):
    cycle = current_cycle(db)
    allocations = []
    unallocated = []
    if cycle:
        allocations = db.query(Allocation).filter_by(cycle_id=cycle.id).order_by(Allocation.id).all()
        unallocated = db.query(Application).filter_by(cycle_id=cycle.id, status="unallocated").all()
    pending = len([a for a in allocations if a.status == "Pending Verification"])
    return render(
        request, "office_allocation.html", user=user, cycle=cycle, allocations=allocations,
        unallocated=unallocated, pending=pending, criteria=get_criteria(db, cycle),
        is_open=window_open(cycle),
    )


@router.post("/allocation/run")
def run(request: Request, user=Depends(office_only), db: Session = Depends(get_db)):
    cycle = current_cycle(db)
    if cycle is None:
        flash(request, "There is no cycle yet")
        return go("/office/allocation")
    if cycle.allocation_run:
        flash(request, "Allocation is already done for this cycle")
        return go("/office/allocation")
    if date.today() <= cycle.end_date:
        flash(request, "Allocation can run only after the application window closes")
        return go("/office/allocation")
    criteria = get_criteria(db, cycle)
    if criteria is None:
        flash(request, "Set the allocation criteria first")
        return go("/office/allocation")
    if db.query(Bed).count() == 0:
        flash(request, "Add hostels, rooms and beds first")
        return go("/office/allocation")

    allocated, unallocated = run_allocation(db, cycle, criteria)
    cycle.allocation_run = True
    log(db, user.id, "Ran allocation for " + cycle.name + ": " + str(allocated) + " allocated, "
        + str(unallocated) + " unallocated")
    db.commit()
    flash(request, str(allocated) + " students allocated, " + str(unallocated) + " could not be allocated")
    return go("/office/allocation")


@router.post("/allocation/publish")
def publish(request: Request, user=Depends(office_only), db: Session = Depends(get_db)):
    cycle = current_cycle(db)
    if cycle is None or not cycle.allocation_run or cycle.published:
        flash(request, "Nothing to publish")
        return go("/office/allocation")
    allocations = db.query(Allocation).filter_by(cycle_id=cycle.id).all()
    if any(a.status == "Pending Verification" for a in allocations):
        flash(request, "Wardens have not verified all allocations yet")
        return go("/office/allocation")
    for allocation in allocations:
        allocation.status = "Published"
        notify(db, allocation.user_id, "Your hostel room is allocated. Open My Room to see the details")
    for app in db.query(Application).filter_by(cycle_id=cycle.id, status="unallocated").all():
        notify(db, app.user_id, "Sorry, no room could be allocated to you in this cycle")
    cycle.published = True
    log(db, user.id, "Published allocation for " + cycle.name)
    db.commit()
    flash(request, "Allocation published")
    return go("/office/allocation")
