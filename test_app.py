import os
from datetime import date, timedelta

os.environ["MONGO_URL"] = "mongomock://localhost/hostelalloc_test"

from fastapi.testclient import TestClient
from models import User, Hostel, Room, Bed, Cycle, Allocation, Application, RoomChange, Checkout
from helpers import hash_password
from main import app


def login(email):
    client = TestClient(app)
    client.post("/login", data={"email": email, "password": "pass123"})
    return client


def setup_module():
    for name, email, role in [
        ("Office", "office@t.com", "office"),
        ("Warden", "warden@t.com", "warden"),
        ("Admin", "admin@t.com", "sysadmin"),
        ("S1", "s1@t.com", "student"),
        ("S2", "s2@t.com", "student"),
        ("S3", "s3@t.com", "student"),
    ]:
        User(name=name, email=email, password=hash_password("pass123"), role=role).save()
    warden = User.objects(email="warden@t.com").first()
    hostel = Hostel(name="Test Hostel", floors=2, warden=warden)
    hostel.save()
    room = Room(hostel=hostel, floor=1, number="101", capacity=2)
    room.save()
    Bed(room=room, number=1).save()
    Bed(room=room, number=2).save()
    Cycle(name="Test", start_date=date.today(), end_date=date.today() + timedelta(days=5)).save()


def test_wrong_password():
    client = TestClient(app)
    response = client.post("/login", data={"email": "s1@t.com", "password": "wrong"})
    assert "Wrong email or password" in response.text


def test_student_cannot_open_office_pages():
    client = login("s1@t.com")
    response = client.get("/office")
    assert response.status_code == 403


def test_not_logged_in_goes_to_login():
    client = TestClient(app)
    response = client.get("/student")
    assert "Login" in response.text


def test_full_flow():
    s1 = login("s1@t.com")
    s2 = login("s2@t.com")
    s3 = login("s3@t.com")
    office = login("office@t.com")
    warden = login("warden@t.com")

    r = s1.post("/student/apply", data={"year": ""})
    assert "select your year" in r.text

    r = s1.post("/student/apply", data={"year": "3", "action": "draft"})
    assert "Draft saved" in r.text
    assert Application.objects(status="draft").count() == 1

    s1.post("/student/apply", data={"year": "3"})
    s2.post("/student/apply", data={"year": "2"})
    r = s3.post("/student/apply", data={"year": "1"})
    assert "Application submitted" in r.text

    r = office.post("/office/allocation/run")
    assert "only after the application window closes" in r.text

    yesterday = str(date.today() - timedelta(days=1))
    r = office.post("/office/cycle/dates", data={"start_date": yesterday, "end_date": yesterday})
    assert "before today" in r.text
    r = office.post("/office/cycle/dates", data={"start_date": yesterday, "end_date": str(date.today())})
    assert "before today" in r.text
    r = office.post("/office/cycle/dates", data={"start_date": str(date.today()), "end_date": str(date.today())})
    assert "Dates updated" in r.text

    office.post("/office/cycle/close")
    r = s1.post("/student/apply", data={"year": "3"})
    assert "not open" in r.text

    r = office.post("/office/allocation/run")
    assert "Set the allocation criteria first" in r.text

    office.post("/office/criteria", data={"year_order": "senior", "use_preference": "yes"})
    r = office.post("/office/allocation/run")
    assert "2 students allocated, 1 could not be allocated" in r.text

    assert Allocation.objects.count() == 2
    assert Bed.objects(occupied=True).count() == 2
    names = [a.user.name for a in Allocation.objects.order_by("id")]
    assert names == ["S1", "S2"]

    r = office.post("/office/allocation/publish")
    assert "have not verified" in r.text

    r = s1.get("/student/allocation")
    assert "not been published" in r.text

    warden.post("/warden/verify-all")
    r = office.post("/office/allocation/publish")
    assert "Allocation published" in r.text

    r = s1.get("/student/allocation")
    assert "Test Hostel" in r.text
    r = s3.get("/notifications")
    assert "no room could be allocated" in r.text

    hostel = Hostel.objects.first()
    room = Room(hostel=hostel, floor=1, number="102", capacity=1)
    room.save()
    Bed(room=room, number=1).save()
    new_room_id = str(room.id)

    r = s1.post("/student/room-change", data={"room_id": new_room_id, "reason": ""})
    assert "write a reason" in r.text
    r = s1.post("/student/room-change", data={"room_id": new_room_id, "reason": "Need a quiet room"})
    assert "Request sent" in r.text
    r = s1.post("/student/room-change", data={"room_id": new_room_id, "reason": "Again"})
    assert "pending request" in r.text

    r = warden.post("/warden/changes/" + str(RoomChange.objects.first().id) + "/reject", data={"note": ""})
    assert "reason for rejecting" in r.text
    r = warden.post("/warden/changes/" + str(RoomChange.objects.first().id) + "/approve", data={"room_id": new_room_id})
    assert "Request approved" in r.text

    allocation = Allocation.objects(user=User.objects(email="s1@t.com").first()).first()
    assert allocation.bed.room.number == "102"
    assert Bed.objects(occupied=True).count() == 2
    assert Room.objects(number="101").first().free_count() == 1

    r = s2.post("/student/checkout")
    assert "Checkout started" in r.text
    r = warden.post("/warden/checkouts/" + str(Checkout.objects.first().id) + "/confirm")
    assert "bed is vacant now" in r.text

    assert Bed.objects(occupied=True).count() == 1

    r = s2.get("/student/checkout")
    assert "do not have a room" in r.text
    r = s2.get("/student")
    assert "checked out" in r.text
    assert "You have checked out and your bed is vacant now" in r.text
    s2_user = User.objects(email="s2@t.com").first()
    assert Allocation.objects(user=s2_user).first().status == "Cancelled"


def test_edit_room_capacity():
    office = login("office@t.com")
    room_id = Room.objects(number="102").first().id
    r = office.post("/office/rooms/" + str(room_id) + "/edit", data={"capacity": "1", "room_type": "Standard"})
    assert "Room updated" in r.text


def test_reports_and_audit():
    office = login("office@t.com")
    assert "Occupancy" in office.get("/reports").text
    admin = login("admin@t.com")
    assert "Ran allocation" in admin.get("/admin/audit").text
    student = login("s1@t.com")
    assert student.get("/reports").status_code == 403


def test_inventory_and_hostel_status():
    office = login("office@t.com")
    assert "Hostel Inventory" in office.get("/inventory").text
    assert "Hostel Inventory" in login("warden@t.com").get("/inventory").text
    assert login("s3@t.com").get("/inventory").status_code == 403
    hostel_id = Hostel.objects.first().id
    bed = Bed.objects.first()
    bed.occupied = True
    bed.save()
    r = office.post("/office/hostels/" + str(hostel_id) + "/edit", data={"name": "Test Hostel", "floors": 1, "status": "Inactive"})
    assert "students living" in r.text


def test_register_only_college_email():
    client = TestClient(app)
    r = client.post("/register", data={"name": "X", "email": "x@gmail.com", "password": "abcdef"})
    assert "Only @lnmiit.ac.in emails can register" in r.text
    r = client.post("/register", data={"name": "X", "email": "x@lnmiit.ac.in", "password": "abcdef"})
    assert "Account created" in r.text
