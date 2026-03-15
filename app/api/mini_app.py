import hashlib
import hmac
import html as html_lib
import re
from urllib.parse import parse_qs

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.core.database import get_db
from app.models.service import Mechanic, Parts, ServiceSlot, SlotStatus

router = APIRouter(prefix="/api", tags=["mini-app"])


# ---------------------------------------------------------------------------
# initData validation
# ---------------------------------------------------------------------------

def _verify_init_data(init_data: str) -> bool:
    try:
        parsed = parse_qs(init_data, keep_blank_values=True)
        hash_val = parsed.pop("hash", [None])[0]
        if not hash_val:
            return False
        check_string = "\n".join(
            f"{k}={v[0]}" for k, v in sorted(parsed.items())
        )
        secret = hmac.new(
            b"WebAppData", settings.TELEGRAM_BOT_TOKEN.encode(), hashlib.sha256
        ).digest()
        expected = hmac.new(
            secret, check_string.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, hash_val)
    except Exception:
        return False


def verify_init_data(x_telegram_init_data: str = Header(default="")) -> None:
    """Validate only when initData is actually present and non-empty.
    Empty initData = browser / dev access → allowed through.
    Present but invalid initData → 403.
    """
    if not x_telegram_init_data:
        return
    if not _verify_init_data(x_telegram_init_data):
        raise HTTPException(status_code=403, detail="Invalid Telegram initData")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/slots")
async def get_slots(
    specialization: str = "",
    _: None = Depends(verify_init_data),
):
    slots = await ServiceSlot.find(ServiceSlot.status == SlotStatus.AVAILABLE).to_list()

    mechanic_ids = [
        s.mechanic.ref.id if hasattr(s.mechanic, "ref") else s.mechanic
        for s in slots
    ]
    mechanics = await Mechanic.find({"_id": {"$in": mechanic_ids}}).to_list()

    if specialization.strip():
        keyword = specialization.strip().lower()
        allowed_ids = {
            m.id for m in mechanics
            if any(keyword in spec.lower() for spec in m.specialization)
        }
        mechanics = [m for m in mechanics if m.id in allowed_ids]

    mech_map = {m.id: m for m in mechanics}
    allowed = set(mech_map.keys())

    result = []
    for s in slots:
        mid = s.mechanic.ref.id if hasattr(s.mechanic, "ref") else s.mechanic
        if mid not in allowed:
            continue
        m = mech_map[mid]
        result.append({
            "id": str(s.id),
            "start_time": s.start_time.isoformat(),
            "end_time": s.end_time.isoformat(),
            "mechanic_name": m.name,
            "specialization": m.specialization,
        })

    return result


@router.get("/parts")
async def get_parts(
    q: str = "",
    _: None = Depends(verify_init_data),
):
    if not q.strip():
        parts = await Parts.find().limit(30).to_list()
    else:
        safe = re.escape(q.strip())
        parts = await Parts.find({"name": {"$regex": safe, "$options": "i"}}).to_list()

    return [
        {
            "id": str(p.id),
            "name": p.name,
            "price": p.price,
            "models": [{"name": c.name, "year": c.year} for c in p.models],
        }
        for p in parts
    ]


@router.get("/models")
async def get_models(_: None = Depends(verify_init_data)):
    pipeline = [
        {"$unwind": "$models"},
        {"$group": {"_id": "$models.name"}},
        {"$sort": {"_id": 1}},
    ]
    results = await get_db()["car_parts"].aggregate(pipeline).to_list(length=100)
    names = [r["_id"] for r in results if r["_id"]]

    if not names:
        names = [
            "Honda City", "Honda Civic", "Honda Accord", "Honda CR-V",
            "Honda HR-V", "Honda Pilot", "Honda Jazz", "Honda ZR-V",
            "Acura ILX", "Acura TLX", "Acura RDX", "Acura MDX",
        ]

    return [{"name": n} for n in names]


class CallbackRequest(BaseModel):
    name: str = ""
    phone: str
    car_model: str = ""
    issue: str = ""


@router.post("/callback")
async def post_callback(
    data: CallbackRequest,
    _: None = Depends(verify_init_data),
):
    lines = ["📞 <b>Новий запит на передзвін (Mini App)</b>\n"]
    if data.name:
        lines.append(f"👤 Ім'я: {html_lib.escape(data.name)}")
    lines.append(f"📱 Телефон: {html_lib.escape(data.phone)}")
    if data.car_model:
        lines.append(f"🚗 Модель: {html_lib.escape(data.car_model)}")
    if data.issue:
        lines.append(f"🔧 Питання: {html_lib.escape(data.issue)}")

    notify_bot = Bot(
        token=settings.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        await notify_bot.send_message(settings.STAFF_CHAT_ID, "\n".join(lines))
    finally:
        await notify_bot.session.close()

    return {"ok": True}
