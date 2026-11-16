from datetime import date, timedelta
from fastapi import APIRouter, Depends, Form, Request
from models import (
    Hostel, Room, Bed, User, Cycle, Criteria, Application, Allocation, RoomChange,
)
from helpers import (
    render, go, flash, login_required, notify, log, current_cycle, window_open, ACTIVE_STATUSES, find,
)
from allocation import run_allocation

router = APIRouter(prefix="/office")
office_only = login_required("office")


def get_criteria(cycle):
    if cycle is None:
        return None
    return Criteria.objects(cycle=cycle).first()


def active_wardens():
    return list(User.objects(role="warden", active=True))


@router.get("")
def home(request: Request, user=Depends(office_only)):
    cycle = current_cycle()
    hostels = list(Hostel.objects)
    total = sum(h.total_beds() for h in hostels)
    occupied = sum(h.occupied_beds() for h in hostels)
    applications = 0
    submitted = 0
    if cycle:
        applications = Application.objects(
            cycle=cycle, status__in=["draft", "submitted", "allocated", "unallocated"]
        ).count()
        submitted = Application.objects(cycle=cycle, status__in=["submitted", "allocated", "unallocated"]).count()
    pending_changes = RoomChange.objects(status="Pending").count()
    return render(
        request, "office_home.html", user=user, cycle=cycle, is_open=window_open(cycle),
        hostels=len(hostels), total=total, occupied=occupied, applications=applications,
        submitted=submitted, pending_changes=pending_changes,
    )


@router.get("/hostels")
def hostels(request: Request, user=Depends(office_only)):
    items = list(Hostel.objects.order_by("name"))
    return render(request, "hostels.html", user=user, items=items, wardens=active_wardens())


@router.post("/hostels")
def add_hostel(
    request: Request,
    name: str = Form(...),
    floors: int = Form(1),
    warden_id: str = Form(""),
    user=Depends(office_only),
):
    name = name.strip()
    if not name or floors < 1:
        flash(request, "Enter a hostel name and number of floors")
        return go("/office/hostels")
    if Hostel.objects(name=name).first():
        flash(request, "A hostel with this name already exists")
        return go("/office/hostels")
    Hostel(name=name, floors=floors, warden=find(User, warden_id)).save()
    log(user, "Created hostel " + name)
    flash(request, "Hostel added")
    return go("/office/hostels")


@router.get("/hostels/{hostel_id}")
def hostel_page(hostel_id: str, request: Request, user=Depends(office_only)):
    hostel = find(Hostel, hostel_id)
    if hostel is None:
        flash(request, "Hostel not found")
        return go("/office/hostels")
    return render(request, "hostel_detail.html", user=user, hostel=hostel, wardens=active_wardens())


@router.post("/hostels/{hostel_id}/edit")
def edit_hostel(
    hostel_id: str,
    request: Request,
    name: str = Form(...),
    floors: int = Form(1),
    warden_id: str = Form(""),
    status: str = Form("Active"),
    user=Depends(office_only),
):
    hostel = find(Hostel, hostel_id)
    back = "/office/hostels/" + hostel_id
    other = Hostel.objects(name=name.strip(), id__ne=hostel.id).first() if hostel else None
    if hostel is None or not name.strip() or floors < 1 or other:
        flash(request, "Could not update the hostel")
        return go(back)
    if status not in ("Active", "Inactive"):
        flash(request, "Choose a valid status")
        return go(back)
    if status == "Inactive" and hostel.occupied_beds() > 0:
        flash(request, "Hostel has students living in it, it cannot be made inactive")
        return go(back)
    old_warden = hostel.warden
    new_warden = find(User, warden_id)
    changed = hostel.name != name.strip() or hostel.status != status or hostel.floors != floors
    hostel.name = name.strip()
    hostel.floors = floors
    hostel.status = status
    hostel.warden = new_warden
    hostel.save()
    old_id = old_warden.id if old_warden else None
    new_id = new_warden.id if new_warden else None
    if old_id != new_id:
        if old_warden:
            notify(old_warden, "You are no longer the warden of " + hostel.name)
        if new_warden:
            notify(new_warden, "You are now the warden of " + hostel.name)
        changed = True
    if changed:
        for allocation in Allocation.objects(status__in=ACTIVE_STATUSES):
            if allocation.bed.room.hostel.id == hostel.id:
                notify(allocation.user, "Details of your hostel " + hostel.name + " were updated by the hostel office")
    log(user, "Edited hostel " + hostel.name)
    flash(request, "Hostel updated")
    return go(back)


@router.post("/hostels/{hostel_id}/rooms")
def add_room(
    hostel_id: str,
    request: Request,
    floor: int = Form(0),
    number: str = Form(...),
    capacity: int = Form(...),
    room_type: str = Form("Standard"),
    user=Depends(office_only),
):
    hostel = find(Hostel, hostel_id)
    number = number.strip()
    back = "/office/hostels/" + hostel_id
    if hostel is None or not number or capacity < 1 or capacity > 10:
        flash(request, "Enter a room number and a capacity between 1 and 10")
        return go(back)
    if floor < 0 or floor >= hostel.floors:
        flash(request, "Floor must be between 0 and " + str(hostel.floors - 1))
        return go(back)
    if Room.objects(hostel=hostel, number=number).first():
        flash(request, "This room number already exists in the hostel")
        return go(back)
    room = Room(hostel=hostel, floor=floor, number=number, capacity=capacity, room_type=room_type)
    room.save()
    for i in range(1, capacity + 1):
        Bed(room=room, number=i).save()
    log(user, "Added room " + number + " to " + hostel.name)
    flash(request, "Room added")
    return go(back)


@router.post("/rooms/{room_id}/edit")
def edit_room(
    room_id: str,
    request: Request,
    capacity: int = Form(...),
    room_type: str = Form("Standard"),
    number: str = Form(""),
    floor: int = Form(0),
    status: str = Form("Active"),
    user=Depends(office_only),
):
    room = find(Room, room_id)
    if room is None:
        flash(request, "Room not found")
        return go("/office/hostels")
    back = "/office/hostels/" + str(room.hostel.id)
    if capacity < 1 or capacity > 10:
        flash(request, "Capacity must be between 1 and 10")
        return go(back)
    number = number.strip() or room.number
    if Room.objects(hostel=room.hostel, number=number, id__ne=room.id).first():
        flash(request, "This room number already exists in the hostel")
        return go(back)
    if floor < 0 or floor >= room.hostel.floors:
        flash(request, "Floor must be between 0 and " + str(room.hostel.floors - 1))
        return go(back)
    if status not in ("Active", "Inactive"):
        flash(request, "Choose a valid status")
        return go(back)
    beds = room.beds
    occupied = len([b for b in beds if b.occupied])
    if status == "Inactive" and occupied > 0:
        flash(request, "Room has students living in it, it cannot be made inactive")
        return go(back)
    if capacity < occupied:
        flash(request, "Room has " + str(occupied) + " students, capacity cannot be less than that")
        return go(back)
    if capacity > len(beds):
        for i in range(len(beds) + 1, capacity + 1):
            Bed(room=room, number=i).save()
    else:
        free_beds = [b for b in beds if not b.occupied]
        free_beds.sort(key=lambda b: b.number, reverse=True)
        for bed in free_beds[: len(beds) - capacity]:
            bed.delete()
    room.capacity = capacity
    room.room_type = room_type
    room.number = number
    room.floor = floor
    room.status = status
    room.save()

    bed_ids = [b.id for b in room.beds]
    for allocation in Allocation.objects(status__in=ACTIVE_STATUSES):
        if allocation.bed.id in bed_ids:
            notify(allocation.user, "Details of your room " + room.number + " were updated by the hostel office")
    log(user, "Edited room " + room.number + " of " + room.hostel.name)
    flash(request, "Room updated")
    return go(back)


@router.get("/cycle")
def cycle_page(request: Request, user=Depends(office_only)):
    cycle = current_cycle()
    return render(
        request, "cycle.html", user=user, cycle=cycle, criteria=get_criteria(cycle),
        is_open=window_open(cycle), today=date.today(),
    )


@router.post("/cycle/new")
def new_cycle(
    request: Request,
    name: str = Form(...),
    start_date: date = Form(...),
    end_date: date = Form(...),
    user=Depends(office_only),
):
    cycle = current_cycle()
    if cycle and not cycle.published:
        flash(request, "Finish the current cycle first")
        return go("/office/cycle")
    if end_date < start_date or not name.strip():
        flash(request, "Check the name and dates")
        return go("/office/cycle")
    if start_date < date.today() or end_date < date.today():
        flash(request, "Dates cannot be before today")
        return go("/office/cycle")
    Cycle(name=name.strip(), start_date=start_date, end_date=end_date).save()
    log(user, "Created cycle " + name.strip())
    flash(request, "New cycle created")
    return go("/office/cycle")


@router.post("/cycle/dates")
def change_dates(
    request: Request,
    start_date: date = Form(...),
    end_date: date = Form(...),
    user=Depends(office_only),
):
    cycle = current_cycle()
    if cycle is None or cycle.allocation_run:
        flash(request, "Dates cannot be changed now")
        return go("/office/cycle")
    if end_date < start_date:
        flash(request, "End date is before start date")
        return go("/office/cycle")
    start_changed = start_date != cycle.start_date and start_date < date.today()
    end_changed = end_date != cycle.end_date and end_date < date.today()
    if start_changed or end_changed:
        flash(request, "Dates cannot be changed to a day before today")
        return go("/office/cycle")
    cycle.start_date = start_date
    cycle.end_date = end_date
    cycle.save()
    log(user, "Changed application window of " + cycle.name)
    flash(request, "Dates updated")
    return go("/office/cycle")


@router.post("/cycle/close")
def close_window(request: Request, user=Depends(office_only)):
    cycle = current_cycle()
    if cycle is None or cycle.allocation_run:
        flash(request, "Cannot close now")
        return go("/office/cycle")
    cycle.end_date = date.today() - timedelta(days=1)
    if cycle.start_date > cycle.end_date:
        cycle.start_date = cycle.end_date
    cycle.save()
    log(user, "Closed application window of " + cycle.name)
    flash(request, "Application window closed")
    return go("/office/cycle")


@router.post("/criteria")
def save_criteria(
    request: Request,
    year_order: str = Form("senior"),
    use_preference: str = Form(""),
    user=Depends(office_only),
):
    cycle = current_cycle()
    if cycle is None or cycle.allocation_run:
        flash(request, "Criteria cannot be changed now")
        return go("/office/cycle")
    criteria = get_criteria(cycle)
    if criteria is None:
        criteria = Criteria(cycle=cycle)
    criteria.year_order = year_order
    criteria.use_preference = use_preference == "yes"
    criteria.save()
    log(user, "Saved allocation criteria for " + cycle.name)
    flash(request, "Criteria saved")
    return go("/office/cycle")


@router.get("/allocation")
def allocation_page(request: Request, user=Depends(office_only)):
    cycle = current_cycle()
    allocations = []
    unallocated = []
    if cycle:
        allocations = list(Allocation.objects(cycle=cycle).order_by("id"))
        unallocated = list(Application.objects(cycle=cycle, status="unallocated"))
    pending = len([a for a in allocations if a.status == "Pending Verification"])
    return render(
        request, "office_allocation.html", user=user, cycle=cycle, allocations=allocations,
        unallocated=unallocated, pending=pending, criteria=get_criteria(cycle),
        is_open=window_open(cycle),
    )


@router.post("/allocation/run")
def run(request: Request, user=Depends(office_only)):
    cycle = current_cycle()
    if cycle is None:
        flash(request, "There is no cycle yet")
        return go("/office/allocation")
    if cycle.allocation_run:
        flash(request, "Allocation is already done for this cycle")
        return go("/office/allocation")
    if date.today() <= cycle.end_date:
        flash(request, "Allocation can run only after the application window closes")
        return go("/office/allocation")
    criteria = get_criteria(cycle)
    if criteria is None:
        flash(request, "Set the allocation criteria first")
        return go("/office/allocation")
    if Bed.objects.count() == 0:
        flash(request, "Add hostels, rooms and beds first")
        return go("/office/allocation")

    allocated, unallocated = run_allocation(cycle, criteria)
    cycle.allocation_run = True
    cycle.save()
    log(user, "Ran allocation for " + cycle.name + ": " + str(allocated) + " allocated, "
        + str(unallocated) + " unallocated")
    flash(request, str(allocated) + " students allocated, " + str(unallocated) + " could not be allocated")
    return go("/office/allocation")


@router.post("/allocation/publish")
def publish(request: Request, user=Depends(office_only)):
    cycle = current_cycle()
    if cycle is None or not cycle.allocation_run or cycle.published:
        flash(request, "Nothing to publish")
        return go("/office/allocation")
    allocations = list(Allocation.objects(cycle=cycle))
    if any(a.status == "Pending Verification" for a in allocations):
        flash(request, "Wardens have not verified all allocations yet")
        return go("/office/allocation")
    for allocation in allocations:
        allocation.status = "Published"
        allocation.save()
        notify(allocation.user, "Your hostel room is allocated. Open My Room to see the details")
    for app in Application.objects(cycle=cycle, status="unallocated"):
        notify(app.user, "Sorry, no room could be allocated to you in this cycle")
    cycle.published = True
    cycle.save()
    log(user, "Published allocation for " + cycle.name)
    flash(request, "Allocation published")
    return go("/office/allocation")
