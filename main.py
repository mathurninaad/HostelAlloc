from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware
from database import engine, Base
import models
from helpers import templates
from routes import auth, student, warden, office, admin, reports

Base.metadata.create_all(bind=engine)

app = FastAPI(title="HostelAlloc")
app.add_middleware(SessionMiddleware, secret_key="hostelalloc-secret-key")
app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth.router)
app.include_router(student.router)
app.include_router(warden.router)
app.include_router(office.router)
app.include_router(admin.router)
app.include_router(reports.router)


@app.exception_handler(StarletteHTTPException)
async def show_error(request, exc):
    if exc.status_code == 401:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request, "error.html", {"code": exc.status_code, "message": exc.detail, "user": None, "flash": None},
        status_code=exc.status_code,
    )
