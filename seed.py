from datetime import date, timedelta
import database
from models import User, Hostel, Room, Bed, Cycle
from helpers import hash_password

if User.objects.count() > 0:
    print("Database already has data")
    raise SystemExit

users = [
    ("System Admin", "admin@lnmiit.ac.in", "sysadmin"),
    ("Hostel Office", "office@lnmiit.ac.in", "office"),
    ("Institute Admin", "institute@lnmiit.ac.in", "institute"),
    ("Warden 1", "warden1@lnmiit.ac.in", "warden"),
    ("Warden 2", "warden2@lnmiit.ac.in", "warden"),
]
for i in range(1, 21):
    users.append(("Student " + str(i), "student" + str(i) + "@lnmiit.ac.in", "student"))

for name, email, role in users:
    User(name=name, email=email, password=hash_password("password123"), role=role).save()

warden1 = User.objects(email="warden1@lnmiit.ac.in").first()
warden2 = User.objects(email="warden2@lnmiit.ac.in").first()

for hostel_name, warden in [("BH1", warden1), ("BH2", warden1), ("BH3", warden2), ("BH4", warden2)]:
    hostel = Hostel(name=hostel_name, floors=2, warden=warden)
    hostel.save()
    for number, floor in [("101", 1), ("102", 1)]:
        room = Room(hostel=hostel, floor=floor, number=number, capacity=2)
        room.save()
        for bed_number in [1, 2]:
            Bed(room=room, number=bed_number).save()

Cycle(name="2026-27", start_date=date.today(), end_date=date.today() + timedelta(days=15)).save()
print("Sample data added")
