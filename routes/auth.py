from fastapi import APIRouter, Depends, Form, Request
from models import User, Notification
from helpers import render, go, flash, hash_password, check_password, log, login_required, find

router = APIRouter()

HOME = {
    "student": "/student",
    "warden": "/warden",
    "office": "/office",
    "institute": "/reports",
    "sysadmin": "/admin/users",
}


@router.get("/")
def index(request: Request):
    user = find(User, request.session.get("user_id"))
    if user is None:
        return go("/login")
    return go(HOME[user.role])


@router.get("/login")
def login_page(request: Request):
    return render(request, "login.html", user=None)


@router.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...)):
    user = User.objects(email=email.strip().lower()).first()
    if user is None or not user.active or not check_password(password, user.password):
        flash(request, "Wrong email or password")
        return go("/login")
    request.session["user_id"] = str(user.id)
    return go("/")


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return go("/login")


@router.get("/register")
def register_page(request: Request):
    return render(request, "register.html", user=None)


@router.post("/register")
def register(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    password: str = Form(...),
):
    email = email.strip().lower()
    if not email.endswith("@lnmiit.ac.in"):
        flash(request, "Only @lnmiit.ac.in emails can register")
        return go("/register")
    if len(password) < 6:
        flash(request, "Password must have at least 6 characters")
        return go("/register")
    if User.objects(email=email).first():
        flash(request, "This email is already registered")
        return go("/register")
    user = User(name=name.strip(), email=email, phone=phone.strip(), password=hash_password(password), role="student")
    user.save()
    log(user, "New student registered: " + email)
    flash(request, "Account created, please login")
    return go("/login")


@router.get("/notifications")
def notifications(request: Request, user=Depends(login_required())):
    items = list(Notification.objects(user=user).order_by("-id"))
    new_ids = [n.id for n in items if not n.read]
    for n in items:
        n.read = True
        n.save()
    return render(request, "notifications.html", user=user, items=items, new_ids=new_ids)
