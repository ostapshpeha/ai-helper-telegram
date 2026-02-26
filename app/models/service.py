from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from enum import Enum
from pydantic import BaseModel, Field
from beanie import Document, Link


class SlotStatus(str, Enum):
    AVAILABLE = "available"
    BOOKED = "booked"


class ClientInfo(BaseModel):
    name: str
    phone: str
    car_model: str
    issue_description: str


class Mechanic(Document):
    name: str
    specialization: List[str]
    is_active: bool = True

    class Settings:
        name = "mechanics"


class ServiceSlot(Document):
    mechanic: Link[Mechanic]
    start_time: datetime
    end_time: datetime
    status: SlotStatus = SlotStatus.AVAILABLE
    client: Optional[ClientInfo] = None

    class Settings:
        name = "service_slots"


class Car(BaseModel):
    name: str
    year: int


class Parts(Document):
    name: str
    price: Decimal
    models: List[Car]

    class Settings:
        name = "car_parts"
