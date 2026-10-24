from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session
from database import get_db
from models import User, AuditLog
from helpers import render, go, flash, login_required, hash_password, log

router = APIRouter(prefix="/admin")
admin_only = login_required("sysadmin")

ROLES = ["student", "warden", "office", "institute", "sysadmin"]


@router.get("/users")
def users(request: Request, user=Depends(admin_only), db: Session = Depends(get_db)):
    items = db.query(User).order_by(User.id).all()
    return render(request, "users.html", user=user, items=items, roles=ROLES)


@router.post("/users")
def add_user(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    user=Depends(admin_only),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    if role not in ROLES or len(password) < 6 or not name.strip():
        flash(request, "Check the name, role and password (at least 6 characters)")
        return go("/admin/users")
    if db.query(User).filter_by(email=email).first():
        flash(request, "This email is already used")
        return go("/admin/users")
    db.add(User(name=name.strip(), email=email, password=hash_password(password), role=role))
    log(db, user.id, "Created " + role + " account " + email)
    db.commit()
    flash(request, "User created")
    return go("/admin/users")


@router.post("/users/{user_id}/role")
def change_role(
    user_id: int,
    request: Request,
    role: str = Form(...),
    user=Depends(admin_only),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if target is None or role not in ROLES:
        flash(request, "Could not change the role")
        return go("/admin/users")
    if target.id == user.id:
        flash(request, "You cannot change your own role")
        return go("/admin/users")
    target.role = role
    log(db, user.id, "Changed role of " + target.email + " to " + role)
    db.commit()
    flash(request, "Role changed")
    return go("/admin/users")


@router.post("/users/{user_id}/toggle")
def toggle(user_id: int, request: Request, user=Depends(admin_only), db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if target is None or target.id == user.id:
        flash(request, "Could not change this account")
        return go("/admin/users")
    target.active = not target.active
    log(db, user.id, ("Activated " if target.active else "Deactivated ") + target.email)
    db.commit()
    flash(request, "Account updated")
    return go("/admin/users")


@router.get("/audit")
def audit(request: Request, user=Depends(admin_only), db: Session = Depends(get_db)):
    items = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(200).all()
    return render(request, "audit.html", user=user, items=items)
