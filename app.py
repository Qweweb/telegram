import os
import re
import html
import time
import asyncio
import logging
import sqlite3
import urllib.request
from contextlib import asynccontextmanager
from typing import Optional, List

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from deep_translator import GoogleTranslator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("system_bridge")

load_dotenv()
API_ID = os.getenv("TG_API_ID")
API_HASH = os.getenv("TG_API_HASH")
DEFAULT_SESSION_STRING = "1BVtsOIwBu23DAs8KikZMR7vTp3B84OYaI2vUTY_zl7H7o49KLg9TJ1y5h5CBqcWSdm70NgfifaqFT1XRMZilS3Vmu7M0dgGTNcKB98KI9vlIehgVWwAnnT2jc6JzkLhO3PF37UZgQLRgwGZgJOUkU8FKC0XbeQDbOkPw_TiJmsKwkGat0TSS2kDQn9h_-tD3tYTRePh6bqFp7iRPKOfT_piy3-CFIc-i43trQmdivepN8Xi38pRk4KoSsqBqgvL8ftFRvqWkWBxNlvEjzY-Z1H3fD7s7J-Ln6ShuhPVXdXN6Z1HF3L85cyUEFH9fgaX19NptXuGxmzCQaxHSU7LZsxsZrfLPxV4="
TG_SESSION_STRING = os.getenv("TG_SESSION_STRING") or DEFAULT_SESSION_STRING
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

def clean_html_report(raw_text: str) -> str:
    """Completely strips CSS, styles, scripts, HTML tags and returns clean spacious text."""
    if not raw_text or ("<" not in raw_text and ">" not in raw_text):
        return raw_text

    try:
        soup = BeautifulSoup(raw_text, "html.parser")

        # 1. Decompose style, script, head, meta, link, and right-hand sidebars
        for tag in soup.find_all(["style", "script", "head", "meta", "link", "nav", "aside", "header"]):
            tag.decompose()

        for nav in soup.find_all(class_=re.compile(r"(right|nav|menu|index|sidebar)", re.I)):
            nav.decompose()

        # 2. Convert <br> and <p> to newlines
        for br in soup.find_all(["br", "p"]):
            br.replace_with("\n")

        # 3. Extract leak blocks if structured
        blocks = [d for d in soup.find_all("div") if d.get("class") == ["block"] or (d.get("id") and re.match(r"^p\d+", d.get("id")))]
        if blocks:
            formatted_blocks = []
            for b in blocks:
                b_text = b.get_text()
                lines = [l.strip() for l in b_text.split("\n") if l.strip()]
                if lines:
                    formatted_blocks.append("\n".join(lines))
            if formatted_blocks:
                return ("\n\n" + "═" * 40 + "\n\n").join(formatted_blocks)

        # Fallback text extraction
        text = soup.get_text()
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"HTML clean error: {e}")
        s = re.sub(r"<style[\s\S]*?</style>", "", raw_text, flags=re.I)
        s = re.sub(r"<script[\s\S]*?</script>", "", s, flags=re.I)
        s = re.sub(r"<(br|p|div|tr)[^>]*>", "\n", s, flags=re.I)
        s = re.sub(r"<[^>]+>", "", s)
        lines = [l.strip() for l in s.split("\n") if l.strip()]
        return "\n".join(lines)

def safe_translate(text: str) -> str:
    if not text or not text.strip():
        return text

    cleaned = clean_html_report(text)

    modified = cleaned
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

async def ensure_connected() -> bool:
    """Ensures the Telegram client is connected and authorized. Automatically reconnects if TCP connection dropped."""
    global client
    if not client:
        if API_ID and API_HASH and API_ID != "your_api_id_here":
            try:
                api_id_int = int(API_ID)
                if TG_SESSION_STRING and TG_SESSION_STRING.strip():
                    client = TelegramClient(StringSession(TG_SESSION_STRING.strip()), api_id_int, API_HASH)
                else:
                    session_path = os.path.join(os.path.dirname(__file__), "user_session")
                    client = TelegramClient(session_path, api_id_int, API_HASH)
            except Exception as e:
                logger.error(f"Client creation failed: {e}")
                return False
        else:
            return False

    try:
        if not client.is_connected():
            logger.info("Reconnecting Telegram client...")
            await client.connect()
        return bool(client.is_connected() and await client.is_user_authorized())
    except Exception as e:
        logger.error(f"Error in ensure_connected: {e}")
        return False

# Keep-Alive Background Worker
async def keep_alive_worker():
    await asyncio.sleep(30)
    while True:
        try:
            await ensure_connected()
            render_url = os.getenv("RENDER_EXTERNAL_URL", "https://telegram-search-app.onrender.com")
            if render_url:
                urllib.request.urlopen(f"{render_url}/api/status", timeout=10)
                logger.info("Self-ping keep-alive successful.")
        except Exception:
            pass
        await asyncio.sleep(300)  # Ping every 5 minutes

@asynccontextmanager
async def lifespan(app: FastAPI):
    global client
    logger.info("Initializing Core Engine...")
    await ensure_connected()
    asyncio.create_task(keep_alive_worker())
    yield
    if client and client.is_connected():
        await client.disconnect()

app = FastAPI(title="Search Protocol", lifespan=lifespan)

class SearchRequest(BaseModel):
    query: str
    device_id: Optional[str] = "default_device"

@app.get("/api/status")
async def get_status(device_id: Optional[str] = "default_device"):
    is_connected = await ensure_connected()
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
    logger.info(f"Admin reset triggered for device [{req.device_id}].")
    return {
        "status": "success", 
        "message": f"Reset successful for device."
    }

async def fetch_all_paginated_pages(client: TelegramClient, target_bot: str, main_msg) -> List[str]:
    pages = []
    seen_texts = set()
    
    current_msg = main_msg
    page_count = 1
    max_pages = 12
    
    while current_msg and page_count <= max_pages:
        raw = (current_msg.raw_text or current_msg.message or "").strip()
        if raw and raw not in seen_texts:
            seen_texts.add(raw)
            pages.append(raw)
        
        if not current_msg.buttons:
            break
            
        next_button = None
        for row in current_msg.buttons:
            for btn in row:
                btn_text = btn.text.strip()
                if "➡️" in btn_text or "▶" in btn_text or "»" in btn_text:
                    next_button = btn
                    break
            if next_button:
                break
                
        if not next_button:
            break
            
        try:
            logger.info(f"Auto-fetching Next Page ({page_count + 1})...")
            await next_button.click()
            await asyncio.sleep(1.8)
            
            updated_messages = await client.get_messages(target_bot, ids=current_msg.id)
            if updated_messages:
                updated_text = (updated_messages.raw_text or updated_messages.message or "").strip()
                if updated_text == raw or updated_text in seen_texts:
                    break
                current_msg = updated_messages
                page_count += 1
            else:
                break
        except Exception as e:
            logger.warning(f"Pagination click ended/error: {e}")
            break
            
    return pages

async def try_download_full_file(client: TelegramClient, target_bot: str, main_msg, conv) -> Optional[str]:
    if not main_msg or not main_msg.buttons:
        return None

    download_button = None
    for row in main_msg.buttons:
        for btn in row:
            btn_text = btn.text.lower()
            if "download" in btn_text or "скачать" in btn_text or "file" in btn_text:
                download_button = btn
                break
        if download_button:
            break

    if not download_button:
        return None

    try:
        logger.info("Auto-clicking [Download] button for full dump...")
        await download_button.click()
        
        file_msg = await conv.get_response(timeout=8)
        if file_msg and file_msg.media:
            downloaded_bytes = await client.download_media(file_msg, bytes)
            if downloaded_bytes:
                try:
                    text_content = downloaded_bytes.decode("utf-8", errors="ignore")
                    cleaned_dump = clean_html_report(text_content)
                    if len(cleaned_dump.strip()) > 20:
                        logger.info(f"Successfully downloaded and cleaned full file dump ({len(cleaned_dump)} chars).")
                        return cleaned_dump.strip()
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"Download button extraction: {e}")

    return None

@app.post("/api/search")
async def search_number(req: SearchRequest):
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
                "message": f"Access Limit: {MAX_SEARCH_LIMIT}/{MAX_SEARCH_LIMIT} searches used on this device. Device locked.",
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

    is_connected = await ensure_connected()
    if not is_connected:
        raise HTTPException(status_code=503, detail="Search system is offline. Please try again in 5 seconds.")

    async with query_lock:
        dev = get_device_info(device_id)
        if dev["search_count"] >= MAX_SEARCH_LIMIT:
            return JSONResponse(
                status_code=403,
                content={"error": "limit_reached", "message": "Device quota exceeded."}
            )
        elapsed = time.time() - dev["last_search_time"]
        if elapsed < COOLDOWN_SECONDS:
            remaining = int(COOLDOWN_SECONDS - elapsed)
            return JSONResponse(
                status_code=429,
                content={"error": "cooldown_active", "message": f"Cooldown: {remaining}s remaining.", "remaining_seconds": remaining}
            )

        try:
            logger.info(f"Querying database for [{cleaned_query}]")
            
            messages_collected = []
            async with client.conversation(BOT_USERNAME, timeout=40) as conv:
                await conv.send_message(cleaned_query)
                
                # 1. Wait for initial response (stats / header)
                first_response = await conv.get_response()
                first_text = (first_response.raw_text or first_response.message or "").strip()
                if first_text:
                    messages_collected.append(first_text)
                
                # 2. Wait for main data message
                main_data_msg = None
                try:
                    next_response = await conv.get_response(timeout=4)
                    main_data_msg = next_response
                except asyncio.TimeoutError:
                    if first_response.buttons:
                        main_data_msg = first_response

                # 3. Check for Full Download File first
                file_dump = None
                if main_data_msg:
                    file_dump = await try_download_full_file(client, BOT_USERNAME, main_data_msg, conv)

                if file_dump:
                    messages_collected.append(file_dump)
                elif main_data_msg:
                    # 4. Auto-Fetch all paginated pages (1/3, 2/3, 3/3...)
                    all_pages = await fetch_all_paginated_pages(client, BOT_USERNAME, main_data_msg)
                    if all_pages:
                        if len(all_pages) > 1:
                            for idx, pg in enumerate(all_pages):
                                formatted_page = f"[ PAGE {idx + 1} / {len(all_pages)} ]\n" + pg
                                messages_collected.append(formatted_page)
                        else:
                            messages_collected.append(all_pages[0])

            # Translate & format collected messages
            translated_messages = []
            for msg_text in messages_collected:
                trans = safe_translate(msg_text)
                translated_messages.append(trans)

            divider = "\n\n" + "═" * 42 + "\n\n"
            final_text = divider.join(translated_messages) if translated_messages else "No response returned."
            
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
            raise HTTPException(status_code=504, detail="Operation timed out. Please try again.")
        except errors.FloodWaitError as e:
            raise HTTPException(status_code=429, detail=f"Rate limit reached. Please wait {e.seconds} seconds.")
        except Exception as e:
            logger.error(f"Query error: {e}")
            raise HTTPException(status_code=500, detail="Database query processing error.")

static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def serve_index():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Service active."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=PORT, reload=False)
