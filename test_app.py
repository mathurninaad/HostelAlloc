import os
import tempfile
from datetime import date, timedelta

db_file = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["DATABASE_URL"] = "sqlite:///" + db_file

from fastapi.testclient import TestClient
from database import SessionLocal, engine, Base
from models import User, Hostel, Room, Bed, Cycle, Allocation
from helpers import hash_password
from main import app


def login(email):
    client = TestClient(app)
    client.post("/login", data={"email": email, "password": "pass123"})
    return client


def setup_module():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    for name, email, role in [
        ("Office", "office@t.com", "office"),
        ("Warden", "warden@t.com", "warden"),
        ("Admin", "admin@t.com", "sysadmin"),
        ("S1", "s1@t.com", "student"),
        ("S2", "s2@t.com", "student"),
        ("S3", "s3@t.com", "student"),
    ]:
        db.add(User(name=name, email=email, password=hash_password("pass123"), role=role))
    db.commit()
    warden = db.query(User).filter_by(email="warden@t.com").first()
    hostel = Hostel(name="Test Hostel", floors=1, warden_id=warden.id)
    db.add(hostel)
    db.flush()
    room = Room(hostel_id=hostel.id, floor=1, number="101", capacity=2)
    db.add(room)
    db.flush()
    db.add(Bed(room_id=room.id, number=1))
    db.add(Bed(room_id=room.id, number=2))
    db.add(Cycle(name="Test", start_date=date.today(), end_date=date.today() + timedelta(days=5)))
    db.commit()
    db.close()


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
    assert "Please select your year of study" in r.text

    s1.post("/student/apply", data={"year": "3"})
    s2.post("/student/apply", data={"year": "2"})
    r = s3.post("/student/apply", data={"year": "1"})
    assert "Application submitted" in r.text

    r = office.post("/office/allocation/run")
    assert "only after the application window closes" in r.text

    office.post("/office/cycle/close")
    r = s1.post("/student/apply", data={"year": "3"})
    assert "not open" in r.text

    r = office.post("/office/allocation/run")
    assert "Set the allocation criteria first" in r.text

    office.post("/office/criteria", data={"year_order": "senior", "use_preference": "yes"})
    r = office.post("/office/allocation/run")
    assert "2 students allocated, 1 could not be allocated" in r.text

    db = SessionLocal()
    assert db.query(Allocation).count() == 2
    assert db.query(Bed).filter_by(occupied=True).count() == 2
    names = [a.user.name for a in db.query(Allocation).all()]
    assert names == ["S1", "S2"]
    db.close()

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

    db = SessionLocal()
    hostel = db.query(Hostel).first()
    room = Room(hostel_id=hostel.id, floor=1, number="102", capacity=1)
    db.add(room)
    db.flush()
    db.add(Bed(room_id=room.id, number=1))
    db.commit()
    new_room_id = room.id
    db.close()

    r = s1.post("/student/room-change", data={"room_id": new_room_id, "reason": ""})
    assert "write a reason" in r.text
    r = s1.post("/student/room-change", data={"room_id": new_room_id, "reason": "Need a quiet room"})
    assert "Request sent" in r.text
    r = s1.post("/student/room-change", data={"room_id": new_room_id, "reason": "Again"})
    assert "pending request" in r.text

    r = warden.post("/warden/changes/1/reject", data={"note": ""})
    assert "reason for rejecting" in r.text
    r = warden.post("/warden/changes/1/approve", data={"room_id": new_room_id})
    assert "Request approved" in r.text

    db = SessionLocal()
    allocation = db.query(Allocation).filter_by(user_id=db.query(User).filter_by(email="s1@t.com").first().id).first()
    assert allocation.bed.room.number == "102"
    assert db.query(Bed).filter_by(occupied=True).count() == 2
    old_room = db.query(Room).filter_by(number="101").first()
    assert old_room.free_count() == 1
    db.close()

    r = s2.post("/student/checkout")
    assert "Checkout started" in r.text
    r = warden.post("/warden/checkouts/1/confirm")
    assert "bed is vacant now" in r.text

    db = SessionLocal()
    assert db.query(Bed).filter_by(occupied=True).count() == 1
    db.close()

    r = s2.get("/student/checkout")
    assert "do not have a room" in r.text


def test_edit_room_capacity():
    office = login("office@t.com")
    db = SessionLocal()
    room = db.query(Room).filter_by(number="102").first()
    room_id = room.id
    db.close()
    r = office.post("/office/rooms/" + str(room_id) + "/edit", data={"capacity": "1", "room_type": "Standard"})
    assert "Room updated" in r.text


def test_reports_and_audit():
    office = login("office@t.com")
    assert "Occupancy" in office.get("/reports").text
    admin = login("admin@t.com")
    assert "Ran allocation" in admin.get("/admin/audit").text
    student = login("s1@t.com")
    assert student.get("/reports").status_code == 403
