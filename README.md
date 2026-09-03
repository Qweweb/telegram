# Telegram Bot Bridge & Search App

A minimal, low-latency, rate-limited web application that connects your frontend query directly to a 3rd-party Telegram Bot (@SoSOsintX_bot) via MTProto (Telethon).

---

## 🚀 Setup & Installation Instructions (સ્ટેપ-બાય-સ્ટેપ સેટઅપ)

### સ્ટેપ 1: Dependencies Install કરો
`ash
pip install -r requirements.txt
`

### સ્ટેપ 2: .env ફાઈલમાં Telegram વિગતો ભરો
.env ફાઈલ ખોલો અને નીચેની વિગતો ભરો:
1. TG_API_ID: તમારા Telegram એકાઉન્ટનો API ID ([https://my.telegram.org](https://my.telegram.org) પરથી API development tools માંથી મળશે).
2. TG_API_HASH: તમારો API Hash.
3. TG_PHONE: તમારો મોબાઈલ નંબર દેશના કોડ સાથે (દા.ત. +919876543210).
4. BOT_USERNAME: SoSOsintX_bot (ડિફોલ્ટ સેટ કરેલું છે).
5. COOLDOWN_SECONDS: 600 (10 મિનિટ = 600 સેકન્ડ).

### સ્ટેપ 3: One-time Telegram Session સેટઅપ કરો
ટર્મિનલમાં આ કમાન્ડ ચલાવો:
`ash
python setup_session.py
`
- આ સ્ક્રિપ્ટ તમારા Telegram પર એક OTP મોકલશે.
- ટર્મિનલમાં OTP નાખીને એન્ટર આપો.
- આનાથી user_session.session ફાઈલ બનશે, જેથી વારંવાર લૉગિન કરવું નહીં પડે.

### સ્ટેપ 4: સર્વર શરૂ કરો
તમે ડબલ ક્લિક કરીને un.bat ચલાવી શકો છો, અથવા ટર્મિનલમાં:
`ash
python app.py
`
- બ્રાઉઝરમાં http://127.0.0.1:8000 ઓપન કરો.

---

## ✨ Features
- **Clean Dark Glassmorphism UI**: Minimalist cybersecurity dashboard look.
- **10-Minute Cooldown Guard**: Live countdown timer & progress bar between queries to keep your account safe from Telegram flood limits.
- **Persisted State**: Page reload will retain the remaining cooldown timer.
- **One-Click Copy**: Easily copy bot output with one click.
- **Async Low-Latency**: Direct MTProto connection to Telegram for the fastest possible response.
