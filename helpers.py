import hashlib
import os
from datetime import date
from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from bson import ObjectId
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


def find(model, item_id):
    if not item_id or not ObjectId.is_valid(str(item_id)):
        return None
    return model.objects(id=item_id).first()


def login_required(*roles):
    def check(request: Request):
        user = find(User, request.session.get("user_id"))
        if user is None or not user.active:
            raise HTTPException(status_code=401)
        if roles and user.role not in roles:
            raise HTTPException(status_code=403, detail="You are not allowed to open this page")
        return user

    return check


def notify(user, message):
    Notification(user=user, message=message).save()


def log(user, action):
    AuditLog(user=user, action=action).save()


def current_cycle():
    return Cycle.objects.order_by("-id").first()


def window_open(cycle):
    if cycle is None:
        return False
    return cycle.start_date <= date.today() <= cycle.end_date


def active_allocation(user):
    return Allocation.objects(user=user, status__in=ACTIVE_STATUSES).order_by("-id").first()


def eligibility_problem(user):
    if not user.active:
        return "Your account is not active"
    if active_allocation(user):
        return "You already have a room allocated"
    return None


def find_vacant_bed(hostel=None, room=None):
    if room is not None:
        rooms = [room] if room.is_active() else []
    else:
        rooms = [r for r in Room.objects(status="Active").order_by("id") if r.hostel.status == "Active"]
        if hostel is not None:
            rooms = [r for r in rooms if r.hostel.id == hostel.id]
    for r in rooms:
        bed = Bed.objects(room=r, occupied=False).order_by("number").first()
        if bed:
            return bed
    return None


def bed_text(bed):
    room = bed.room
    return room.hostel.name + ", Room " + room.number + ", Bed " + str(bed.number)
