import os
import tempfile
from datetime import date, timedelta

# Each test gets its own fresh database
db_file = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["DATABASE_URL"] = "sqlite:///" + db_file

from database import SessionLocal, engine, Base
from models import User, Hostel, Room, Bed, Cycle, Allocation, RoomChange, Application
from helpers import hash_password


def setup_function():
    """Create fresh tables for each test function."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def teardown_function():
    """Clean up after each test."""
    import shutil
    shutil.rmtree(os.path.dirname(db_file), ignore_errors=True)


def test_user_creation():
    """Test that a User can be created and has expected attributes."""
    db = SessionLocal()
    user = User(name="Test User", email="test@example.com", password=hash_password("pass123"), role="student")
    db.add(user)
    db.commit()
    db.refresh(user)
    assert user.id is not None
    assert user.name == "Test User"
    assert user.email == "test@example.com"
    assert user.role == "student"
    assert user.active is True
    db.delete(user)
    db.commit()
    db.close()


def test_hostel_relationship():
    """Test Hostel model relationship with Rooms and Beds."""
    db = SessionLocal()
    # Create a user as warden
    warden = User(name="Warden", email="warden1@test.com", password=hash_password("pass123"), role="warden")
    db.add(warden)
    db.flush()

    hostel = Hostel(name="Test Hostel 1", floors=2, warden_id=warden.id)
    db.add(hostel)
    db.flush()

    # Create rooms with beds
    room1 = Room(hostel_id=hostel.id, floor=1, number="101", capacity=3)
    db.add(room1)
    db.flush()

    for i in range(1, 4):
        db.add(Bed(room_id=room1.id, number=i))

    db.commit()

    # Test relationships
    assert hostel.rooms[0].beds[0].room == room1
    assert room1.hostel == hostel
    assert hostel.total_beds() == 3

    # Test occupied/unoccupied
    assert room1.free_count() == 3

    # Delete in correct order: beds first, then room, then hostel, then warden
    for bed in room1.beds:
        db.delete(bed)
    db.delete(room1)
    db.delete(hostel)
    db.delete(warden)
    db.commit()
    db.close()


def test_cycle_dates():
    """Test Cycle model with start and end dates."""
    db = SessionLocal()
    cycle = Cycle(
        name="Test Cycle 2",
        start_date=date.today(),
        end_date=date.today() + timedelta(days=30),
    )
    db.add(cycle)
    db.commit()
    db.refresh(cycle)
    assert cycle.id is not None
    assert cycle.name == "Test Cycle 2"
    db.delete(cycle)
    db.commit()
    db.close()


def test_allocation_creation():
    """Test Allocation model creation and relationships."""
    db = SessionLocal()

    # Create user
    user = User(name="Student", email="student1@test.com", password=hash_password("pass123"), role="student")
    db.add(user)
    db.flush()

    # Create hostel and room with unique name
    hostel = Hostel(name="Test Hostel 2", floors=1)
    db.add(hostel)
    db.flush()

    room = Room(hostel_id=hostel.id, floor=1, number="101", capacity=1)
    db.add(room)
    db.flush()

    bed = Bed(room_id=room.id, number=1)
    db.add(bed)
    db.flush()

    # Create cycle
    cycle = Cycle(name="Test Cycle 3", start_date=date.today(), end_date=date.today() + timedelta(days=30))
    db.add(cycle)
    db.commit()

    # Create application first (required for allocation)
    application = Application(user_id=user.id, cycle_id=cycle.id, year=3, status="submitted")
    db.add(application)
    db.commit()

    # Create allocation with application_id
    allocation = Allocation(
        application_id=application.id,
        user_id=user.id,
        cycle_id=cycle.id,
        bed_id=bed.id,
        status="Pending Verification",
    )
    db.add(allocation)
    db.commit()

    # Use cycle_id instead of cycle relationship (model doesn't have cycle relationship)
    assert allocation.id is not None
    assert allocation.user == user
    assert allocation.bed == bed
    assert allocation.cycle_id == cycle.id
    assert allocation.status == "Pending Verification"

    # Clean up in correct order
    db.delete(allocation)
    db.delete(application)
    db.delete(cycle)
    db.delete(bed)
    db.delete(room)
    db.delete(hostel)
    db.delete(user)
    db.commit()
    db.close()


def test_room_change_model():
    """Test RoomChange model creation and relationships."""
    db = SessionLocal()

    # Create user
    user = User(name="Student", email="student2@test.com", password=hash_password("pass123"), role="student")
    db.add(user)
    db.flush()

    # Create hostel, room, and bed
    hostel = Hostel(name="Test Hostel 3", floors=1)
    db.add(hostel)
    db.flush()

    room1 = Room(hostel_id=hostel.id, floor=1, number="101", capacity=1)
    db.add(room1)
    db.flush()

    bed1 = Bed(room_id=room1.id, number=1)
    db.add(bed1)
    db.commit()

    # Create allocation first - need application
    from models import Cycle, Application
    cycle = Cycle(name="Test", start_date=date.today(), end_date=date.today() + timedelta(days=30))
    db.add(cycle)
    db.flush()

    application = Application(user_id=user.id, cycle_id=cycle.id, year=3, status="submitted")
    db.add(application)
    db.commit()

    allocation = Allocation(
        application_id=application.id,
        user_id=user.id,
        cycle_id=cycle.id,
        bed_id=bed1.id,
        status="Pending Verification",
    )
    db.add(allocation)
    db.commit()

    # Create room change request
    room_change = RoomChange(
        user_id=user.id,
        allocation_id=allocation.id,
        requested_room_id=room1.id,
        reason="Need a quieter room",
    )
    db.add(room_change)
    db.commit()
    db.refresh(room_change)

    assert room_change.id is not None
    assert room_change.user == user
    assert room_change.allocation == allocation
    assert room_change.requested_room == room1
    assert room_change.reason == "Need a quieter room"
    assert room_change.status == "Pending"

    # Clean up in correct order
    db.delete(room_change)
    db.delete(allocation)
    db.delete(application)
    db.delete(cycle)
    db.delete(bed1)
    db.delete(room1)
    db.delete(hostel)
    db.delete(user)
    db.commit()
    db.close()