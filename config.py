# Bot Configuration File
import os

# Telegram Bot Token (Get from @BotFather)
# NOTE: token ko code me rakhna risky hai — production me env variable use karein.
BOT_TOKEN = os.getenv("BOT_TOKEN", "8571462279:AAHn9wmFNiububdC_LKlplGNmTfqjQ2vptM")

# Admin Telegram ID (Surendra Chaudhary)
ADMIN_ID = int(os.getenv("ADMIN_ID") or 8828732820)

# Currency & Rewards Configuration (USD based as per client requirements)
CURRENCY = "USD"
AD_REWARD_USD = float(os.getenv("AD_REWARD_USD", "0.30"))           # $0.30 per ad
REFERRAL_REWARD_USD = float(os.getenv("REFERRAL_REWARD_USD", "0.75")) # $0.75 per friend
TASK_REWARD_USD = float(os.getenv("TASK_REWARD_USD", "0.10"))       # $0.10 per task
DAILY_AD_LIMIT = int(os.getenv("DAILY_AD_LIMIT", "15"))             # 15 ads per day
MIN_WITHDRAWAL_USD = float(os.getenv("MIN_WITHDRAWAL_USD", "10.00")) # Min $10.00
REQUIRED_INVITES = int(os.getenv("REQUIRED_INVITES", "5"))          # 5 friends required to withdraw
REQUIRED_ADS = int(os.getenv("REQUIRED_ADS", "80"))                 # 80 ads required to withdraw

# Anti-cheat: do ad rewards ke beech minimum gap (seconds). Ek real video ad ~15s+ hota hai.
AD_COOLDOWN_SECONDS = int(os.getenv("AD_COOLDOWN_SECONDS", "15"))

# Mandatory Channels (if any)
MANDATORY_CHANNELS = []

# Tasks (server-side source of truth).
# "chat" set karenge (e.g. "@mychannel") aur bot us channel me ADMIN hoga
# to join verify hoga; warna sirf link open karke claim hoga.
TASKS = [
    {"id": 1, "icon": "📢", "title": "Join Official Telegram", "url": "https://t.me/Payjust_bot", "chat": None},
    {"id": 2, "icon": "▶️", "title": "Subscribe to YouTube", "url": "https://youtube.com", "chat": None},
    {"id": 3, "icon": "🐦", "title": "Follow on Twitter / X", "url": "https://twitter.com", "chat": None},
    {"id": 4, "icon": "👥", "title": "Join Partner Group", "url": "https://t.me/Payjust_bot", "chat": None},
]

# Adsgram Configuration
ADSGRAM_BLOCK_ID = os.getenv("ADSGRAM_BLOCK_ID", "53853")
# Production me hamesha False. True = sirf Adsgram test ads (koi earning nahi, reward URL call nahi hota).
ADSGRAM_DEBUG = os.getenv("ADSGRAM_DEBUG", "false").lower() == "true"
# Optional: Adsgram dashboard me Reward URL set karein:
#   https://<API_PUBLIC_URL>/adsgram/reward?userid=[userId]&secret=<ADSGRAM_REWARD_SECRET>
# Jab ye True ho, client-side claim band ho jata hai aur reward sirf Adsgram server callback se milta hai (fraud-proof).
ADSGRAM_USE_REWARD_URL = os.getenv("ADSGRAM_USE_REWARD_URL", "false").lower() == "true"
ADSGRAM_REWARD_SECRET = os.getenv("ADSGRAM_REWARD_SECRET", "change-me-secret")

# Backend API server (Mini App isi se balance/ads/withdraw sync karta hai)
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("PORT") or os.getenv("API_PORT") or 8080)
# Public HTTPS URL jahan ye API reachable hai (Render/Railway/VPS ya cloudflared tunnel).
# Render sets RENDER_EXTERNAL_URL automatically (e.g. https://payjust-backend.onrender.com)
API_PUBLIC_URL = os.getenv("API_PUBLIC_URL", os.getenv("RENDER_EXTERNAL_URL", "https://payjust-bot.onrender.com")).rstrip("/")

# Mini App / Web App URL
_WEBAPP_BASE = os.getenv("WEBAPP_URL", "https://pay-just.netlify.app")


def build_webapp_url() -> str:
    """WebApp URL with API endpoint passed as query param (so Netlify redeploy na karna pade jab API URL badle)."""
    from urllib.parse import urlencode, quote
    params = {"v": "8"}
    if API_PUBLIC_URL:
        params["api"] = API_PUBLIC_URL
    sep = "&" if "?" in _WEBAPP_BASE else "?"
    return f"{_WEBAPP_BASE}{sep}{urlencode(params, quote_via=quote)}"


WEBAPP_URL = build_webapp_url()
