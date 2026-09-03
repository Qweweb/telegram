import os
import asyncio
from dotenv import load_dotenv
from telethon import TelegramClient

load_dotenv()

API_ID = os.getenv("TG_API_ID")
API_HASH = os.getenv("TG_API_HASH")
PHONE = os.getenv("TG_PHONE")
BOT_USERNAME = os.getenv("BOT_USERNAME", "SoSOsintX_bot")

async def setup():
    print("=" * 50)
    print(" Telegram Session Setup Utility")
    print("=" * 50)
    
    if not API_ID or not API_HASH or API_ID == "your_api_id_here":
        print("\n[!] Please update your TG_API_ID and TG_API_HASH in .env first!")
        print("    Get them from https://my.telegram.org (under API development tools).")
        return

    try:
        api_id_int = int(API_ID)
    except ValueError:
        print("[!] TG_API_ID must be a valid integer.")
        return

    session_path = os.path.join(os.path.dirname(__file__), "user_session")
    client = TelegramClient(session_path, api_id_int, API_HASH)
    
    print("\n[*] Connecting to Telegram...")
    await client.start(phone=PHONE)

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"\n[+] Successfully logged in as: {me.first_name} (@{me.username or 'NoUsername'})")
        print(f"[+] Session saved to: {session_path}.session")
        
        try:
            print(f"[*] Checking target bot @{BOT_USERNAME}...")
            bot_entity = await client.get_entity(BOT_USERNAME)
            print(f"[+] Found target bot: {bot_entity.first_name} (@{bot_entity.username})")
        except Exception as e:
            print(f"[!] Warning: Could not find bot @{BOT_USERNAME}: {e}")
            
        print("\n[+] Setup completed successfully! You can now run 'python app.py' or 'run.bat'.")
    else:
        print("\n[!] Authorization failed.")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(setup())
