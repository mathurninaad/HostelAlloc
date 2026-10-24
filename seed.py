from datetime import date, timedelta
from database import SessionLocal, engine, Base
from models import User, Hostel, Room, Bed, Cycle
from helpers import hash_password

Base.metadata.create_all(bind=engine)
db = SessionLocal()

if db.query(User).count() > 0:
    print("Database already has data")
    raise SystemExit

users = [
    ("System Admin", "admin@hostel.com", "sysadmin"),
    ("Hostel Office", "office@hostel.com", "office"),
    ("Institute Admin", "institute@hostel.com", "institute"),
    ("Warden Sharma", "warden1@hostel.com", "warden"),
    ("Warden Verma", "warden2@hostel.com", "warden"),
]
for i in range(1, 11):
    users.append(("Student " + str(i), "student" + str(i) + "@hostel.com", "student"))

for name, email, role in users:
    db.add(User(name=name, email=email, password=hash_password("password123"), role=role))
db.commit()

warden1 = db.query(User).filter_by(email="warden1@hostel.com").first()
warden2 = db.query(User).filter_by(email="warden2@hostel.com").first()

for hostel_name, warden in [("Aravali Hostel", warden1), ("Vindhya Hostel", warden2)]:
    hostel = Hostel(name=hostel_name, floors=2, warden_id=warden.id)
    db.add(hostel)
    db.flush()
    for number, floor in [("101", 1), ("102", 1), ("201", 2), ("202", 2)]:
        room = Room(hostel_id=hostel.id, floor=floor, number=number, capacity=2)
        db.add(room)
        db.flush()
        for bed_number in [1, 2]:
            db.add(Bed(room_id=room.id, number=bed_number))

db.add(Cycle(name="2026-27", start_date=date.today(), end_date=date.today() + timedelta(days=15)))
db.commit()
db.close()
print("Sample data added")
