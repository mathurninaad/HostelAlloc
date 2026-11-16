from datetime import datetime
from mongoengine import (
    Document, StringField, IntField, BooleanField, DateField, DateTimeField, ReferenceField,
)


class User(Document):
    name = StringField(required=True)
    email = StringField(required=True, unique=True)
    phone = StringField(default="")
    password = StringField(required=True)
    role = StringField(required=True)
    active = BooleanField(default=True)


class Hostel(Document):
    name = StringField(required=True, unique=True)
    floors = IntField(default=1)
    warden = ReferenceField(User, null=True)
    status = StringField(default="Active")

    @property
    def rooms(self):
        return list(Room.objects(hostel=self).order_by("number"))

    def total_beds(self):
        return sum(len(room.beds) for room in self.rooms)

    def occupied_beds(self):
        return sum(1 for room in self.rooms for bed in room.beds if bed.occupied)


class Room(Document):
    hostel = ReferenceField(Hostel, required=True)
    floor = IntField(default=0)
    number = StringField(required=True)
    capacity = IntField(default=1)
    room_type = StringField(default="Standard")
    status = StringField(default="Active")

    @property
    def beds(self):
        return list(Bed.objects(room=self).order_by("number"))

    def free_count(self):
        return sum(1 for bed in self.beds if not bed.occupied)

    def is_active(self):
        return self.status == "Active" and self.hostel.status == "Active"


class Bed(Document):
    room = ReferenceField(Room, required=True)
    number = IntField(required=True)
    occupied = BooleanField(default=False)


class Cycle(Document):
    name = StringField(required=True)
    start_date = DateField(required=True)
    end_date = DateField(required=True)
    allocation_run = BooleanField(default=False)
    published = BooleanField(default=False)


class Criteria(Document):
    cycle = ReferenceField(Cycle, required=True)
    year_order = StringField(default="senior")
    use_preference = BooleanField(default=True)


class Application(Document):
    user = ReferenceField(User, required=True)
    cycle = ReferenceField(Cycle, required=True)
    year = IntField(null=True)
    hostel = ReferenceField(Hostel, null=True)
    status = StringField(default="draft")
    created_at = DateTimeField(default=datetime.now)


class Allocation(Document):
    application = ReferenceField(Application, required=True)
    user = ReferenceField(User, required=True)
    cycle = ReferenceField(Cycle, required=True)
    bed = ReferenceField(Bed, required=True)
    status = StringField(default="Pending Verification")
    created_at = DateTimeField(default=datetime.now)


class RoomChange(Document):
    user = ReferenceField(User, required=True)
    allocation = ReferenceField(Allocation, required=True)
    requested_room = ReferenceField(Room, required=True)
    reason = StringField(required=True)
    status = StringField(default="Pending")
    decision_note = StringField(default="")
    approver = ReferenceField(User, null=True)
    created_at = DateTimeField(default=datetime.now)
    decided_at = DateTimeField(null=True)


class Checkout(Document):
    user = ReferenceField(User, required=True)
    allocation = ReferenceField(Allocation, required=True)
    status = StringField(default="Initiated")
    initiated_at = DateTimeField(default=datetime.now)
    confirmed_at = DateTimeField(null=True)


class Notification(Document):
    user = ReferenceField(User, required=True)
    message = StringField(required=True)
    read = BooleanField(default=False)
    created_at = DateTimeField(default=datetime.now)


class AuditLog(Document):
    user = ReferenceField(User, null=True)
    action = StringField(required=True)
    created_at = DateTimeField(default=datetime.now)
