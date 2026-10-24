import hashlib
import os
from datetime import date
from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
from models import User, Notification, AuditLog, Cycle, Allocation, Bed, Room

templates = Jinja2Templates(directory="templates")

ACTIVE_STATUSES = ["Pending Verification", "Verified", "Published"]


def hash_password(password):
    salt = os.urandom(8).hex()
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 50000).hex()
    return salt + "$" + hashed


def check_password(password, stored):
    salt, hashed = stored.split("$")
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 50000).hex() == hashed


def go(url):
    return RedirectResponse(url, status_code=303)


def flash(request: Request, message):
    request.session["flash"] = message


def render(request: Request, name, **data):
    data["flash"] = request.session.pop("flash", None)
    return templates.TemplateResponse(request, name, data)


def login_required(*roles):
    def check(request: Request, db: Session = Depends(get_db)):
        user_id = request.session.get("user_id")
        user = db.get(User, user_id) if user_id else None
        if user is None or not user.active:
            raise HTTPException(status_code=401)
        if roles and user.role not in roles:
            raise HTTPException(status_code=403, detail="You are not allowed to open this page")
        return user

    return check


def notify(db, user_id, message):
    db.add(Notification(user_id=user_id, message=message))


def log(db, user_id, action):
    db.add(AuditLog(user_id=user_id, action=action))


def current_cycle(db):
    return db.query(Cycle).order_by(Cycle.id.desc()).first()


def window_open(cycle):
    if cycle is None:
        return False
    return cycle.start_date <= date.today() <= cycle.end_date


def active_allocation(db, user_id):
    return (
        db.query(Allocation)
        .filter(Allocation.user_id == user_id, Allocation.status.in_(ACTIVE_STATUSES))
        .order_by(Allocation.id.desc())
        .first()
    )


def find_vacant_bed(db, hostel_id=None, room_id=None):
    query = db.query(Bed).join(Room, Bed.room_id == Room.id).filter(Bed.occupied == False)
    if hostel_id:
        query = query.filter(Room.hostel_id == hostel_id)
    if room_id:
        query = query.filter(Room.id == room_id)
    return query.order_by(Room.id, Bed.number).first()


def bed_text(bed):
    room = bed.room
    return room.hostel.name + ", Room " + room.number + ", Bed " + str(bed.number)
