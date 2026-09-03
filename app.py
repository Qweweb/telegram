import os
import time
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
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
PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "0.0.0.0")

client: Optional[TelegramClient] = None
last_query_timestamp: float = 0.0
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
    """Safely and accurately translates text and labels to English without 500 error bugs."""
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

def get_cooldown_remaining() -> int:
    global last_query_timestamp, COOLDOWN_SECONDS
    elapsed = time.time() - last_query_timestamp
    if elapsed < COOLDOWN_SECONDS:
        return int(COOLDOWN_SECONDS - elapsed)
    return 0

@asynccontextmanager
async def lifespan(app: FastAPI):
    global client
    logger.info("Initializing Telegram Client...")
    if not API_ID or not API_HASH or API_ID == "your_api_id_here":
        logger.warning("TG_API_ID or TG_API_HASH not configured in .env!")
    else:
        try:
            api_id_int = int(API_ID)
            # 1. Try StringSession first (ideal for Cloud like Render/Railway)
            if TG_SESSION_STRING and TG_SESSION_STRING.strip():
                logger.info("Using StringSession from environment variable.")
                client = TelegramClient(StringSession(TG_SESSION_STRING.strip()), api_id_int, API_HASH)
            else:
                # 2. Fallback to local session file
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

@app.get("/api/status")
async def get_status():
    is_connected = bool(client and client.is_connected() and await client.is_user_authorized())
    return {
        "status": "online",
        "authorized": is_connected,
        "bot": BOT_USERNAME,
        "cooldown_remaining": get_cooldown_remaining(),
        "cooldown_total": COOLDOWN_SECONDS
    }

@app.post("/api/admin/reset-cooldown")
async def reset_cooldown():
    global last_query_timestamp
    last_query_timestamp = 0.0
    logger.info("Admin secret reset triggered: Cooldown reset to 0.")
    return {"status": "success", "message": "Cooldown reset to 0 successfully."}

@app.post("/api/search")
async def search_number(req: SearchRequest):
    global last_query_timestamp, client
    cleaned_query = req.query.strip()
    if not cleaned_query:
        raise HTTPException(status_code=400, detail="Search query cannot be empty.")
    
    remaining = get_cooldown_remaining()
    if remaining > 0:
        mins = remaining // 60
        secs = remaining % 60
        return JSONResponse(
            status_code=429,
            content={
                "error": "cooldown_active",
                "message": f"Cooldown active. Please wait {mins}m {secs}s before next search.",
                "remaining_seconds": remaining
            }
        )

    if not client or not client.is_connected():
        raise HTTPException(status_code=503, detail="Telegram client is not connected.")
    if not await client.is_user_authorized():
        raise HTTPException(status_code=503, detail="Telegram account is not authorized. Please run setup_session.py.")

    async with query_lock:
        remaining = get_cooldown_remaining()
        if remaining > 0:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "cooldown_active",
                    "message": f"Cooldown active. Please wait {remaining}s.",
                    "remaining_seconds": remaining
                }
            )

        try:
            logger.info(f"Querying @{BOT_USERNAME} with query: {cleaned_query}")
            
            messages_collected = []
            async with client.conversation(BOT_USERNAME, timeout=35) as conv:
                await conv.send_message(cleaned_query)
                
                # 1. Wait for initial response
                first_response = await conv.get_response()
                if first_response.raw_text or first_response.message:
                    messages_collected.append((first_response.raw_text or first_response.message).strip())
                
                # 2. Wait for any subsequent detailed messages (like leak reports)
                while True:
                    try:
                        next_response = await conv.get_response(timeout=4)
                        text = (next_response.raw_text or next_response.message or "").strip()
                        if text:
                            messages_collected.append(text)
                    except asyncio.TimeoutError:
                        break

            # Process and translate collected messages
            translated_messages = []
            for msg_text in messages_collected:
                trans = safe_translate(msg_text)
                translated_messages.append(trans)

            divider = "\n\n" + "—" * 35 + "\n\n"
            final_text = divider.join(translated_messages) if translated_messages else "No response returned by bot."
            
            last_query_timestamp = time.time()
            return {
                "status": "success",
                "query": cleaned_query,
                "result": final_text,
                "timestamp": int(time.time()),
                "cooldown_seconds": COOLDOWN_SECONDS
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
    return {"message": "Telegram Bot Bridge API is running. UI file static/index.html not found."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=PORT, reload=False)
