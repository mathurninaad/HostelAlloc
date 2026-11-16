from fastapi import APIRouter, Depends, Form, Request
from models import User, AuditLog
from helpers import render, go, flash, login_required, hash_password, log, find

router = APIRouter(prefix="/admin")
admin_only = login_required("sysadmin")

ROLES = ["student", "warden", "office", "institute", "sysadmin"]


@router.get("/users")
def users(request: Request, user=Depends(admin_only)):
    items = list(User.objects.order_by("id"))
    return render(request, "users.html", user=user, items=items, roles=ROLES)


@router.post("/users")
def add_user(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    user=Depends(admin_only),
):
    email = email.strip().lower()
    if role not in ROLES or len(password) < 6 or not name.strip():
        flash(request, "Check the name, role and password (at least 6 characters)")
        return go("/admin/users")
    if User.objects(email=email).first():
        flash(request, "This email is already used")
        return go("/admin/users")
    User(name=name.strip(), email=email, password=hash_password(password), role=role).save()
    log(user, "Created " + role + " account " + email)
    flash(request, "User created")
    return go("/admin/users")


@router.post("/users/{user_id}/role")
def change_role(
    user_id: str,
    request: Request,
    role: str = Form(...),
    user=Depends(admin_only),
):
    target = find(User, user_id)
    if target is None or role not in ROLES:
        flash(request, "Could not change the role")
        return go("/admin/users")
    if target.id == user.id:
        flash(request, "You cannot change your own role")
        return go("/admin/users")
    target.role = role
    target.save()
    log(user, "Changed role of " + target.email + " to " + role)
    flash(request, "Role changed")
    return go("/admin/users")


@router.post("/users/{user_id}/toggle")
def toggle(user_id: str, request: Request, user=Depends(admin_only)):
    target = find(User, user_id)
    if target is None or target.id == user.id:
        flash(request, "Could not change this account")
        return go("/admin/users")
    target.active = not target.active
    target.save()
    log(user, ("Activated " if target.active else "Deactivated ") + target.email)
    flash(request, "Account updated")
    return go("/admin/users")


@router.get("/audit")
def audit(request: Request, user=Depends(admin_only)):
    items = list(AuditLog.objects.order_by("-id").limit(200))
    return render(request, "audit.html", user=user, items=items)
