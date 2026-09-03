import os
import asyncio
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession

load_dotenv(r"D:\Antigravity\General_Conversations\telegram\.env")
API_ID = int(os.getenv("TG_API_ID"))
API_HASH = os.getenv("TG_API_HASH")
PHONE = os.getenv("TG_PHONE")

async def main():
    print("=" * 60)
    print(" Fresh Telegram Cloud Session Generator")
    print("=" * 60)
    
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.start(phone=PHONE)
    
    if await client.is_user_authorized():
        me = await client.get_me()
        session_str = client.session.save()
        
        print(f"\n[+] SUCCESS! Logged in as: {me.first_name} (@{me.username or 'NoUsername'})")
        print("\n" + "=" * 60)
        print("YOUR NEW TG_SESSION_STRING FOR RENDER.COM:")
        print("=" * 60)
        print(session_str)
        print("=" * 60 + "\n")
        
        env_path = r"D:\Antigravity\General_Conversations\telegram\.env"
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        new_lines = [l for l in lines if not l.startswith("TG_SESSION_STRING=")]
        new_lines.append(f"TG_SESSION_STRING={session_str}\n")
        
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
            
        print("[+] .env file updated with new session string!")
    else:
        print("[!] Login failed.")
        
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
