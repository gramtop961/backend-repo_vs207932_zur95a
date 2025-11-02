"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, Literal

# Example schemas (kept for reference):

class User(BaseModel):
    """
    Users collection schema
    Collection name: "user" (lowercase of class name)
    """
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    address: str = Field(..., description="Address")
    age: Optional[int] = Field(None, ge=0, le=120, description="Age in years")
    is_active: bool = Field(True, description="Whether user is active")

class Product(BaseModel):
    """
    Products collection schema
    Collection name: "product" (lowercase of class name)
    """
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in dollars")
    category: str = Field(..., description="Product category")
    in_stock: bool = Field(True, description="Whether product is in stock")

# Hospital Kiosk Schemas

DepartmentName = Literal[
    "General",
    "Cardiology",
    "Pediatrics",
    "Radiology",
    "Orthopedics",
]

class Appointment(BaseModel):
    """
    Appointments collection
    Collection name: "appointment"
    """
    patient_name: str = Field(..., min_length=2)
    phone: str = Field(..., description="Contact number")
    email: Optional[EmailStr] = Field(None)
    department: DepartmentName
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD")
    time_slot: Optional[str] = Field(None, description="Optional time slot label, e.g., 10:00")
    status: Literal["booked", "checked_in"] = "booked"
    booking_code: Optional[str] = Field(None, description="System-generated code for check-in")

class AppointmentCreate(BaseModel):
    patient_name: str
    phone: str
    email: Optional[EmailStr] = None
    department: DepartmentName
    date: str
    time_slot: Optional[str] = None

class CheckInRequest(BaseModel):
    booking_code: Optional[str] = None
    patient_name: Optional[str] = None
    phone: Optional[str] = None
    department: Optional[DepartmentName] = None
    date: Optional[str] = None
