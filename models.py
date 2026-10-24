from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    phone = Column(String, default="")
    password = Column(String, nullable=False)
    role = Column(String, nullable=False)
    active = Column(Boolean, default=True)


class Hostel(Base):
    __tablename__ = "hostels"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    floors = Column(Integer, default=1)
    warden_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    warden = relationship("User")
    rooms = relationship("Room", back_populates="hostel", order_by="Room.number")

    def total_beds(self):
        return sum(len(room.beds) for room in self.rooms)

    def occupied_beds(self):
        return sum(1 for room in self.rooms for bed in room.beds if bed.occupied)


class Room(Base):
    __tablename__ = "rooms"
    id = Column(Integer, primary_key=True)
    hostel_id = Column(Integer, ForeignKey("hostels.id"), nullable=False)
    floor = Column(Integer, default=0)
    number = Column(String, nullable=False)
    capacity = Column(Integer, default=1)
    room_type = Column(String, default="Standard")
    hostel = relationship("Hostel", back_populates="rooms")
    beds = relationship("Bed", back_populates="room", order_by="Bed.number")

    def free_count(self):
        return sum(1 for bed in self.beds if not bed.occupied)


class Bed(Base):
    __tablename__ = "beds"
    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    number = Column(Integer, nullable=False)
    occupied = Column(Boolean, default=False)
    room = relationship("Room", back_populates="beds")


class Cycle(Base):
    __tablename__ = "cycles"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    allocation_run = Column(Boolean, default=False)
    published = Column(Boolean, default=False)


class Criteria(Base):
    __tablename__ = "criteria"
    id = Column(Integer, primary_key=True)
    cycle_id = Column(Integer, ForeignKey("cycles.id"), nullable=False)
    year_order = Column(String, default="senior")
    priority_category = Column(String, default="")
    use_preference = Column(Boolean, default=True)


class Application(Base):
    __tablename__ = "applications"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    cycle_id = Column(Integer, ForeignKey("cycles.id"), nullable=False)
    year = Column(Integer, nullable=True)
    category = Column(String, nullable=True)
    hostel_id = Column(Integer, ForeignKey("hostels.id"), nullable=True)
    status = Column(String, default="draft")
    created_at = Column(DateTime, default=datetime.now)
    user = relationship("User")
    hostel = relationship("Hostel")


class Allocation(Base):
    __tablename__ = "allocations"
    id = Column(Integer, primary_key=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    cycle_id = Column(Integer, ForeignKey("cycles.id"), nullable=False)
    bed_id = Column(Integer, ForeignKey("beds.id"), nullable=False)
    status = Column(String, default="Pending Verification")
    created_at = Column(DateTime, default=datetime.now)
    user = relationship("User")
    application = relationship("Application")
    bed = relationship("Bed")


class RoomChange(Base):
    __tablename__ = "room_changes"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    allocation_id = Column(Integer, ForeignKey("allocations.id"), nullable=False)
    requested_room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    reason = Column(Text, nullable=False)
    status = Column(String, default="Pending")
    decision_note = Column(Text, default="")
    approver_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    decided_at = Column(DateTime, nullable=True)
    user = relationship("User", foreign_keys=[user_id])
    approver = relationship("User", foreign_keys=[approver_id])
    allocation = relationship("Allocation")
    requested_room = relationship("Room")


class Checkout(Base):
    __tablename__ = "checkouts"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    allocation_id = Column(Integer, ForeignKey("allocations.id"), nullable=False)
    status = Column(String, default="Initiated")
    initiated_at = Column(DateTime, default=datetime.now)
    confirmed_at = Column(DateTime, nullable=True)
    user = relationship("User")
    allocation = relationship("Allocation")


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message = Column(String, nullable=False)
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    user = relationship("User")
