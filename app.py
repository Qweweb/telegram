import os
import time
import asyncio
import logging
import sqlite3
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from deep_translator import GoogleTranslator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("telegram_bridge")

load_dotenv()
API_ID = os.getenv("TG_API_ID")
API_HASH = os.getenv("TG_API_HASH")
TG_SESSION_STRING = os.getenv("TG_SESSION_STRING")
BOT_USERNAME = os.getenv("BOT_USERNAME", "SoSOsintX_bot")
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "600"))
MAX_SEARCH_LIMIT = int(os.getenv("MAX_SEARCH_LIMIT", "7"))
PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "0.0.0.0")

# Database Setup for persistent device tracking
DB_PATH = os.path.join(os.path.dirname(__file__), "device_tracking.db")

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS device_usage (
                device_id TEXT PRIMARY KEY,
                search_count INTEGER DEFAULT 0,
                last_search_time REAL DEFAULT 0,
                is_blocked INTEGER DEFAULT 0,
                created_at REAL DEFAULT (strftime('%s', 'now'))
            )
        """)
        conn.commit()

init_db()

def get_device_info(device_id: str):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT search_count, last_search_time, is_blocked FROM device_usage WHERE device_id = ?", (device_id,))
        row = cursor.fetchone()
        if row:
            return {"search_count": row[0], "last_search_time": row[1], "is_blocked": bool(row[2])}
        else:
            cursor.execute("INSERT INTO device_usage (device_id, search_count, last_search_time) VALUES (?, 0, 0)", (device_id,))
            conn.commit()
            return {"search_count": 0, "last_search_time": 0.0, "is_blocked": False}

def update_device_search(device_id: str):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        now = time.time()
        cursor.execute("""
            UPDATE device_usage 
            SET search_count = search_count + 1, last_search_time = ? 
            WHERE device_id = ?
        """, (now, device_id))
        conn.commit()

def reset_device_db(device_id: str):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE device_usage 
            SET search_count = 0, last_search_time = 0, is_blocked = 0 
            WHERE device_id = ?
        """, (device_id,))
        conn.commit()

client: Optional[TelegramClient] = None
query_lock = asyncio.Lock()

COMMON_LABELS = {
    "Запрос:": "Request:",
    "Выполнено подзапросов:": "Queries executed:",
    "Количество результатов:": "Number of results:",
    "Количество утечек:": "Number of leaks:",
    "Время поиска:": "Search time:",
    "Регион:": "Region:",
    "región:": "Region:",
    "Страна:": "Country:",
    "Имя:": "Name:",
    "Ориентир:": "Landmark:",
    "Контакт:": "Contact:",
    "Telefón:": "Phone:",
    "Celé meno:": "Full name:",
    "Meno Otca:": "Father's Name:",
    "Dress:": "Address:",
    "Adres:": "Address:",
    "Mesto:": "City:",
    "Štát:": "State:",
    "Poštové smerovacie číslo:": "Postal Code:",
    "Názov spoločnosti:": "Company Name:",
    "Pracovná pozícia:": "Job Title:",
}

def safe_translate(text: str) -> str:
    if not text or not text.strip():
        return text

    modified = text
    for k, v in COMMON_LABELS.items():
        modified = modified.replace(k, v)

    paragraphs = modified.split("\n\n")
    translated_paragraphs = []

    for p in paragraphs:
        p_clean = p.strip()
        if not p_clean:
            translated_paragraphs.append(p)
            continue
        try:
            t = GoogleTranslator(source="auto", target="en").translate(p_clean)
            if t and "Error 500" not in t and "That's an error" not in t:
                translated_paragraphs.append(t)
            else:
                translated_paragraphs.append(p)
        except Exception:
            translated_paragraphs.append(p)

    return "\n\n".join(translated_paragraphs)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global client
    logger.info("Initializing Telegram Client...")
    if not API_ID or not API_HASH or API_ID == "your_api_id_here":
        logger.warning("TG_API_ID or TG_API_HASH not configured in .env!")
    else:
        try:
            api_id_int = int(API_ID)
            if TG_SESSION_STRING and TG_SESSION_STRING.strip():
                logger.info("Using StringSession from environment variable.")
                client = TelegramClient(StringSession(TG_SESSION_STRING.strip()), api_id_int, API_HASH)
            else:
                session_path = os.path.join(os.path.dirname(__file__), "user_session")
                logger.info(f"Using file session at {session_path}")
                client = TelegramClient(session_path, api_id_int, API_HASH)

            await client.connect()
            if await client.is_user_authorized():
                me = await client.get_me()
                logger.info(f"Connected to Telegram as {me.first_name} (@{me.username or 'NoUsername'})")
            else:
                logger.warning("Telegram client is not authorized. Please run 'python setup_session.py' first.")
        except Exception as e:
            logger.error(f"Failed to initialize Telegram client: {e}")
    yield
    if client and client.is_connected():
        logger.info("Disconnecting Telegram client...")
        await client.disconnect()

app = FastAPI(title="Telegram Bot Bridge", lifespan=lifespan)

class SearchRequest(BaseModel):
    query: str
    device_id: Optional[str] = "default_device"

@app.get("/api/status")
async def get_status(device_id: Optional[str] = "default_device"):
    is_connected = bool(client and client.is_connected() and await client.is_user_authorized())
    dev = get_device_info(device_id)
    
    elapsed = time.time() - dev["last_search_time"]
    cooldown_remaining = max(0, int(COOLDOWN_SECONDS - elapsed)) if elapsed < COOLDOWN_SECONDS else 0
    searches_left = max(0, MAX_SEARCH_LIMIT - dev["search_count"])
    is_locked = (dev["search_count"] >= MAX_SEARCH_LIMIT) or dev["is_blocked"]

    return {
        "status": "online",
        "authorized": is_connected,
        "cooldown_remaining": cooldown_remaining,
        "cooldown_total": COOLDOWN_SECONDS,
        "searches_left": searches_left,
        "max_searches": MAX_SEARCH_LIMIT,
        "is_locked": is_locked
    }

class ResetRequest(BaseModel):
    device_id: Optional[str] = "default_device"

@app.post("/api/admin/reset-cooldown")
async def reset_cooldown(req: ResetRequest):
    reset_device_db(req.device_id)
    logger.info(f"Admin secret reset triggered: Quota & cooldown reset for device {req.device_id}.")
    return {
        "status": "success", 
        "message": f"Cooldown and search limit reset to {MAX_SEARCH_LIMIT} for device."
    }

@app.post("/api/search")
async def search_number(req: SearchRequest):
    global client
    cleaned_query = req.query.strip()
    device_id = req.device_id.strip() if req.device_id else "default_device"

    if not cleaned_query:
        raise HTTPException(status_code=400, detail="Search query cannot be empty.")
    
    # 1. Check Device Quota Limit
    dev = get_device_info(device_id)
    if dev["search_count"] >= MAX_SEARCH_LIMIT or dev["is_blocked"]:
        return JSONResponse(
            status_code=403,
            content={
                "error": "limit_reached",
                "message": f"Access Limit Reached: {MAX_SEARCH_LIMIT}/{MAX_SEARCH_LIMIT} searches used on this device. Device locked.",
                "searches_left": 0
            }
        )

    # 2. Check Device Cooldown
    elapsed = time.time() - dev["last_search_time"]
    if elapsed < COOLDOWN_SECONDS:
        remaining = int(COOLDOWN_SECONDS - elapsed)
        mins = remaining // 60
        secs = remaining % 60
        return JSONResponse(
            status_code=429,
            content={
                "error": "cooldown_active",
                "message": f"Cooldown active. Please wait {mins}m {secs}s before next search.",
                "remaining_seconds": remaining,
                "searches_left": max(0, MAX_SEARCH_LIMIT - dev["search_count"])
            }
        )

    if not client or not client.is_connected():
        raise HTTPException(status_code=503, detail="Telegram client is not connected.")
    if not await client.is_user_authorized():
        raise HTTPException(status_code=503, detail="Telegram account is not authorized.")

    async with query_lock:
        # Re-check quota and cooldown inside lock
        dev = get_device_info(device_id)
        if dev["search_count"] >= MAX_SEARCH_LIMIT:
            return JSONResponse(
                status_code=403,
                content={"error": "limit_reached", "message": "Device quota exceeded (7/7)."}
            )
        elapsed = time.time() - dev["last_search_time"]
        if elapsed < COOLDOWN_SECONDS:
            remaining = int(COOLDOWN_SECONDS - elapsed)
            return JSONResponse(
                status_code=429,
                content={"error": "cooldown_active", "message": f"Cooldown active: {remaining}s remaining.", "remaining_seconds": remaining}
            )

        try:
            logger.info(f"Device [{device_id}] querying @{BOT_USERNAME} with query: {cleaned_query}")
            
            messages_collected = []
            async with client.conversation(BOT_USERNAME, timeout=35) as conv:
                await conv.send_message(cleaned_query)
                
                # 1. Wait for initial response
                first_response = await conv.get_response()
                if first_response.raw_text or first_response.message:
                    messages_collected.append((first_response.raw_text or first_response.message).strip())
                
                # 2. Wait for any subsequent detailed messages
                while True:
                    try:
                        next_response = await conv.get_response(timeout=4)
                        text = (next_response.raw_text or next_response.message or "").strip()
                        if text:
                            messages_collected.append(text)
                    except asyncio.TimeoutError:
                        break

            # Translate collected messages
            translated_messages = []
            for msg_text in messages_collected:
                trans = safe_translate(msg_text)
                translated_messages.append(trans)

            divider = "\n\n" + "—" * 35 + "\n\n"
            final_text = divider.join(translated_messages) if translated_messages else "No response returned by bot."
            
            # Update device usage in SQLite
            update_device_search(device_id)
            updated_dev = get_device_info(device_id)
            searches_left = max(0, MAX_SEARCH_LIMIT - updated_dev["search_count"])

            return {
                "status": "success",
                "query": cleaned_query,
                "result": final_text,
                "timestamp": int(time.time()),
                "cooldown_seconds": COOLDOWN_SECONDS,
                "searches_left": searches_left,
                "max_searches": MAX_SEARCH_LIMIT
            }

        except asyncio.TimeoutError:
            logger.error("Timeout waiting for bot response.")
            raise HTTPException(status_code=504, detail="The bot did not respond in time (35s timeout). Please try again later.")
        except errors.FloodWaitError as e:
            logger.error(f"FloodWaitError: {e.seconds} seconds required.")
            raise HTTPException(status_code=429, detail=f"Telegram flood limit reached. Please wait {e.seconds} seconds.")
        except Exception as e:
            logger.error(f"Error querying bot: {e}")
            raise HTTPException(status_code=500, detail=f"Error communicating with bot: {str(e)}")

static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def serve_index():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Telegram Bot Bridge API is running."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=PORT, reload=False)
