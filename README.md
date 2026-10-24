# HostelAlloc

Hostel room allocation and management system made for the CS314 Software Development Lab at LNMIIT, Jaipur (Team T041).

Students apply for hostel rooms online, the hostel office sets up hostels and runs the allocation, wardens verify it, and students can see their room, ask for a room change and checkout at the end of the stay.

## Tech used

- FastAPI
- SQLAlchemy with SQLite
- Jinja2 templates and a small CSS file

## How to run

```
pip install -r requirements.txt
python seed.py
uvicorn main:app --reload
```

Then open http://127.0.0.1:8000

`seed.py` adds some sample users, four hostels (BH-1 to BH-4) and one application cycle. All sample users have the password `password123`.

| Role | Email |
| --- | --- |
| Student | student1@lnmiit.ac.in ... student20@lnmiit.ac.in |
| Warden | warden1@lnmiit.ac.in, warden2@lnmiit.ac.in |
| Hostel office | office@lnmiit.ac.in |
| Institute admin | institute@lnmiit.ac.in |
| System admin | admin@lnmiit.ac.in |

New students can also register from the login page.

## How the flow works

1. Students login and submit the application while the window is open.
2. Hostel office sets the allocation criteria and closes the window.
3. Hostel office runs the allocation. Results are saved as Pending Verification.
4. Wardens verify the allocations of their hostel.
5. Hostel office publishes the results and students get a notification.
6. Students can ask for a room change, wardens approve or reject it.
7. At the end of the stay the checkout is confirmed by the warden and the bed becomes vacant.

## Tests

```
pytest
```

## Project files

- `main.py` - app setup
- `models.py` - database tables
- `helpers.py` - login check, notifications and other common functions
- `allocation.py` - the allocation logic
- `routes/` - pages for each role
- `templates/` and `static/` - html pages and css
