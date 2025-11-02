import os
from datetime import date, datetime
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import db, create_document, get_documents
from schemas import Appointment, AppointmentCreate, CheckInRequest, DepartmentName

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
DEPARTMENTS: List[DepartmentName] = [
    "General",
    "Cardiology",
    "Pediatrics",
    "Radiology",
    "Orthopedics",
]
DEPARTMENT_CAPACITY = 25


# Utility functions

def today_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def count_booked_for(department: str, day_str: str) -> int:
    pipeline = [
        {"$match": {"department": department, "date": day_str}},
        {"$count": "count"},
    ]
    result = list(db["appointment"].aggregate(pipeline)) if db is not None else []
    return int(result[0]["count"]) if result else 0


# Routes

@app.get("/")
def read_root():
    return {"message": "Hospital Kiosk Backend Running"}


@app.get("/departments")
def get_departments():
    return [{"name": d, "capacity": DEPARTMENT_CAPACITY} for d in DEPARTMENTS]


@app.get("/availability")
def get_availability(
    department: DepartmentName = Query(...),
    date_str: str = Query(..., alias="date"),
):
    if department not in DEPARTMENTS:
        raise HTTPException(status_code=400, detail="Unknown department")
    booked = count_booked_for(department, date_str)
    remaining = max(0, DEPARTMENT_CAPACITY - booked)
    used_pct = int(round((booked / DEPARTMENT_CAPACITY) * 100)) if DEPARTMENT_CAPACITY else 0
    return {
        "department": department,
        "date": date_str,
        "capacity": DEPARTMENT_CAPACITY,
        "booked": booked,
        "remaining": remaining,
        "used_pct": used_pct,
    }


@app.get("/calendar-availability")
def calendar_availability(
    department: DepartmentName = Query(...),
    year: int = Query(..., ge=1970, le=2100),
    month: int = Query(..., ge=1, le=12),
):
    if department not in DEPARTMENTS:
        raise HTTPException(status_code=400, detail="Unknown department")

    # Build date prefix and iterate over possible days (1..31), validate actual days per month
    days: Dict[str, Dict[str, int]] = {}
    for day in range(1, 32):
        try:
            d = date(year, month, day)
        except ValueError:
            continue
        d_str = d.strftime("%Y-%m-%d")
        booked = count_booked_for(department, d_str)
        used_pct = int(round((booked / DEPARTMENT_CAPACITY) * 100)) if DEPARTMENT_CAPACITY else 0
        days[d_str] = {
            "booked": booked,
            "remaining": max(0, DEPARTMENT_CAPACITY - booked),
            "used_pct": used_pct,
            "capacity": DEPARTMENT_CAPACITY,
        }
    return {"department": department, "year": year, "month": month, "days": days}


@app.post("/appointments")
def create_appointment(payload: AppointmentCreate):
    if payload.department not in DEPARTMENTS:
        raise HTTPException(status_code=400, detail="Unknown department")

    # Capacity check
    booked = count_booked_for(payload.department, payload.date)
    if booked >= DEPARTMENT_CAPACITY:
        raise HTTPException(status_code=400, detail="No slots available for this date and department")

    # Generate simple booking code
    code_base = f"{payload.department[:3].upper()}{payload.date.replace('-','')}"
    counter = booked + 1
    booking_code = f"{code_base}-{counter:03d}"

    doc = Appointment(
        patient_name=payload.patient_name,
        phone=payload.phone,
        email=payload.email,
        department=payload.department,  # type: ignore
        date=payload.date,
        time_slot=payload.time_slot,
        status="booked",
        booking_code=booking_code,
    )
    inserted_id = create_document("appointment", doc)

    return {"id": inserted_id, "booking_code": booking_code, "status": "booked"}


@app.get("/appointments")
def list_appointments(
    department: Optional[DepartmentName] = None,
    date_str: Optional[str] = Query(None, alias="date"),
):
    query: Dict[str, Any] = {}
    if department:
        query["department"] = department
    if date_str:
        query["date"] = date_str
    docs = get_documents("appointment", query)
    # Clean ObjectId for client
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return docs


@app.post("/checkin")
def check_in(payload: CheckInRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    query: Dict[str, Any] = {}
    if payload.booking_code:
        query["booking_code"] = payload.booking_code
    else:
        # Fallback match by basic fields
        required = [payload.patient_name, payload.phone, payload.department, payload.date]
        if not all(required):
            raise HTTPException(status_code=400, detail="Provide booking_code or name, phone, department and date")
        query = {
            "patient_name": payload.patient_name,
            "phone": payload.phone,
            "department": payload.department,
            "date": payload.date,
        }

    appt = db["appointment"].find_one(query)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if appt.get("status") == "checked_in":
        return {"id": str(appt.get("_id")), "status": "checked_in", "booking_code": appt.get("booking_code")}

    db["appointment"].update_one({"_id": appt["_id"]}, {"$set": {"status": "checked_in", "checked_in_at": datetime.utcnow()}})
    return {"id": str(appt.get("_id")), "status": "checked_in", "booking_code": appt.get("booking_code")}


@app.get("/patients")
def patients_tracking(date_str: Optional[str] = Query(None, alias="date")):
    query: Dict[str, Any] = {}
    if date_str:
        query["date"] = date_str
    docs = get_documents("appointment", query)
    out = []
    for d in docs:
        out.append({
            "id": str(d.get("_id")),
            "patient_name": d.get("patient_name"),
            "phone": d.get("phone"),
            "email": d.get("email"),
            "department": d.get("department"),
            "date": d.get("date"),
            "status": d.get("status", "booked"),
            "booking_code": d.get("booking_code"),
        })
    # Add simple summary
    summary = {
        "total": len(out),
        "checked_in": sum(1 for x in out if x.get("status") == "checked_in"),
        "booked": sum(1 for x in out if x.get("status") != "checked_in"),
    }
    return {"summary": summary, "patients": out}


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        # Try to import database module
        from database import db as test_db

        if test_db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = test_db.name if hasattr(test_db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"

            # Try to list collections to verify connectivity
            try:
                collections = test_db.list_collection_names()
                response["collections"] = collections[:10]  # Show first 10 collections
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except ImportError:
        response["database"] = "❌ Database module not found (run enable-database first)"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    # Check environment variables
    import os
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
