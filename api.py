"""
Mini App backend API (aiohttp), bot ke saath same process me chalta hai.

Pehle Mini App sab kuch localStorage me rakhta tha aur tg.sendData() se bot ko bhejta tha.
sendData() sirf Reply-Keyboard button se khule Mini App me kaam karta hai (inline button /
menu button se nahi) aur har call par Mini App BAND kar deta hai — isliye rewards kabhi DB tak
nahi pahunchte the. Ab Mini App har action is API ko bhejta hai, aur yahan Telegram initData
ka HMAC verify karke hi kuch bhi credit hota hai.
"""
import hashlib
import hmac
import html
import json
import logging
import time
from urllib.parse import parse_qsl

from aiohttp import web
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import config
import database as db

logger = logging.getLogger("api")

INIT_DATA_MAX_AGE = 24 * 3600  # seconds


# ---------------- AUTH ----------------
def verify_init_data(init_data: str):
    """Telegram WebApp initData verify karo. Valid ho to user dict return, warna None."""
    if not init_data:
        return None
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except ValueError:
        return None
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
    calc_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc_hash, received_hash):
        return None

    try:
        if time.time() - int(pairs.get("auth_date", "0")) > INIT_DATA_MAX_AGE:
            return None
        user = json.loads(pairs.get("user", "{}"))
    except (ValueError, TypeError):
        return None
    return user if user.get("id") else None


async def _auth(request: web.Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    user = verify_init_data(body.get("initData", ""))
    if not user:
        raise web.HTTPUnauthorized(
            text=json.dumps({"ok": False, "error": "invalid_init_data"}),
            content_type="application/json",
        )
    db.ensure_user(int(user["id"]), user.get("first_name") or "User", user.get("username") or "")
    return int(user["id"]), user, body


# ---------------- HELPERS ----------------
def _requirements(user_row, settings, tasks_done):
    return {
        "balance": user_row["balance"] >= settings["min_withdrawal"],
        "invites": user_row["total_referrals"] >= settings["required_invites"],
        "tasks": len(tasks_done) >= len(config.TASKS),
        "ads": user_row["ads_watched_total"] >= settings["required_ads"],
    }


def build_state(user_id: int, bot_username: str):
    u = db.get_user(user_id)
    s = db.get_typed_settings()
    tasks_done = db.get_completed_tasks(user_id)
    return {
        "ok": True,
        "user": {
            "id": user_id,
            "balance": round(u["balance"], 2),
            "adsWatchedToday": db.ads_watched_today(user_id),
            "totalAdsWatched": u["ads_watched_total"],
            "totalEarnedFromAds": round(u.get("ad_earned_total") or 0.0, 2),
            "friendsInvited": u["total_referrals"],
            "tasksDone": tasks_done,
            "withdrawals": db.get_user_withdrawals(user_id),
        },
        "settings": {
            "adReward": s["ad_reward"],
            "dailyAdLimit": s["daily_ad_limit"],
            "refReward": s["referral_reward"],
            "taskReward": s["task_reward"],
            "minWithdrawal": s["min_withdrawal"],
            "requiredInvites": s["required_invites"],
            "requiredAds": s["required_ads"],
            "adCooldown": config.AD_COOLDOWN_SECONDS,
        },
        "adsgram": {
            "blockId": s["adsgram_block_id"] or config.ADSGRAM_BLOCK_ID,
            "debug": config.ADSGRAM_DEBUG,
            "useRewardUrl": config.ADSGRAM_USE_REWARD_URL,
        },
        "tasks": [{k: t[k] for k in ("id", "icon", "title", "url")} for t in config.TASKS],
        "requirements": _requirements(u, s, tasks_done),
        "botUsername": bot_username,
        "isAdmin": user_id == config.ADMIN_ID,
    }


def _json(data, status=200):
    return web.json_response(data, status=status)


# ---------------- HANDLERS ----------------
async def health(request):
    return _json({"ok": True, "time": int(time.time())})


async def state(request):
    user_id, _, _ = await _auth(request)
    return _json(build_state(user_id, request.app["bot_username"]))


async def ad_claim(request):
    user_id, _, _ = await _auth(request)
    if config.ADSGRAM_USE_REWARD_URL:
        # Reward sirf Adsgram server callback se aayega; client sirf fresh state le.
        return _json({**build_state(user_id, request.app["bot_username"]), "credited": False, "reason": "server_callback"})

    amount = db.get_typed_settings()["ad_reward"]
    ok, reason = db.credit_ad_view(user_id, amount, source="client")
    data = build_state(user_id, request.app["bot_username"])
    data.update({"credited": ok, "reason": reason, "amount": amount})
    return _json(data, 200 if ok else 429)


async def adsgram_reward_callback(request):
    """Adsgram Reward URL: https://<api>/adsgram/reward?userid=[userId]&secret=<secret>"""
    if request.query.get("secret") != config.ADSGRAM_REWARD_SECRET:
        return _json({"ok": False}, 403)
    try:
        user_id = int(request.query.get("userid", ""))
    except ValueError:
        return _json({"ok": False, "error": "bad_userid"}, 400)
    db.ensure_user(user_id)
    amount = db.get_typed_settings()["ad_reward"]
    ok, reason = db.credit_ad_view(user_id, amount, source="adsgram")
    logger.info(f"Adsgram callback user={user_id} ok={ok} reason={reason}")
    return _json({"ok": ok, "reason": reason})


async def task_claim(request):
    user_id, _, body = await _auth(request)
    bot = request.app["bot"]
    try:
        task_id = int(body.get("taskId"))
    except (TypeError, ValueError):
        return _json({"ok": False, "error": "bad_task"}, 400)
    task = next((t for t in config.TASKS if t["id"] == task_id), None)
    if not task:
        return _json({"ok": False, "error": "bad_task"}, 400)

    if task.get("chat"):
        try:
            member = await bot.get_chat_member(task["chat"], user_id)
            if member.status in ("left", "kicked"):
                return _json({"ok": False, "error": "not_joined"}, 400)
        except Exception as e:
            logger.warning(f"Task verify failed ({task['chat']}): {e}")
            return _json({"ok": False, "error": "verify_failed"}, 400)

    reward = db.get_typed_settings()["task_reward"]
    credited = db.complete_task(user_id, task_id, reward)
    data = build_state(user_id, request.app["bot_username"])
    data.update({"credited": credited, "amount": reward})
    return _json(data)


async def withdraw(request):
    user_id, tg_user, body = await _auth(request)
    bot = request.app["bot"]
    try:
        amount = round(float(body.get("amount", 0)), 2)
    except (TypeError, ValueError):
        return _json({"ok": False, "error": "bad_amount"}, 400)
    method = str(body.get("method", "USDT TRC20"))[:40]
    address = str(body.get("address", "")).strip()[:200]

    u = db.get_user(user_id)
    s = db.get_typed_settings()
    req = _requirements(u, s, db.get_completed_tasks(user_id))
    if not all(req.values()):
        return _json({"ok": False, "error": "requirements", "requirements": req}, 400)
    if amount < s["min_withdrawal"]:
        return _json({"ok": False, "error": "below_min"}, 400)
    if not address:
        return _json({"ok": False, "error": "no_address"}, 400)

    w_id = db.create_withdrawal(user_id, amount, method, address)
    if not w_id:
        return _json({"ok": False, "error": "insufficient_balance"}, 400)

    first_name = tg_user.get("first_name") or "User"
    try:
        await bot.send_message(
            chat_id=user_id,
            text=(
                f"✅ <b>Withdrawal Request Submitted!</b>\n\n"
                f"🆔 Request ID: <b>#{w_id}</b>\n"
                f"💵 Amount: <b>${amount:.2f}</b>\n"
                f"🏦 Method: <b>{html.escape(method)}</b>\n"
                f"💳 Address: <code>{html.escape(address)}</code>\n"
                f"⏳ Status: <b>PENDING (Under review)</b>"
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.info(f"User notify failed: {e}")

    if config.ADMIN_ID:
        try:
            await bot.send_message(
                chat_id=config.ADMIN_ID,
                text=(
                    f"🔔 <b>New Withdrawal Request (#{w_id})</b>\n\n"
                    f"👤 User: <b>{html.escape(first_name)}</b> (<code>{user_id}</code>)\n"
                    f"💵 Amount: <b>${amount:.2f}</b>\n"
                    f"🏦 Method: <b>{html.escape(method)}</b>\n"
                    f"💳 Address: <code>{html.escape(address)}</code>\n"
                    f"📊 Ads: {u['ads_watched_total']} | Invites: {u['total_referrals']}"
                ),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ Approve", callback_data=f"adm_app_{w_id}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"adm_rej_{w_id}"),
                ]]),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"Admin notify error: {e}")

    data = build_state(user_id, request.app["bot_username"])
    data.update({"withdrawalId": w_id})
    return _json(data)


# Mini App (camelCase) -> DB (snake_case)
_ADMIN_KEY_MAP = {
    "adReward": "ad_reward",
    "dailyAdLimit": "daily_ad_limit",
    "refReward": "referral_reward",
    "taskReward": "task_reward",
    "minWithdrawal": "min_withdrawal",
    "requiredInvites": "required_invites",
    "requiredAds": "required_ads",
    "adsgramBlockId": "adsgram_block_id",
}


async def admin_settings(request):
    user_id, _, body = await _auth(request)
    if user_id != config.ADMIN_ID:
        return _json({"ok": False, "error": "forbidden"}, 403)
    incoming = body.get("settings") or {}
    for js_key, db_key in _ADMIN_KEY_MAP.items():
        if js_key in incoming and incoming[js_key] not in (None, ""):
            try:
                db.set_setting(db_key, db.ALLOWED_SETTINGS[db_key](incoming[js_key]))
            except (TypeError, ValueError):
                return _json({"ok": False, "error": f"bad_value:{js_key}"}, 400)
    return _json(build_state(user_id, request.app["bot_username"]))


# ---------------- APP ----------------
@web.middleware
async def cors_middleware(request, handler):
    if request.method == "OPTIONS":
        resp = web.Response(status=204)
    else:
        try:
            resp = await handler(request)
        except web.HTTPException as e:
            resp = e
        except Exception:
            logger.exception("API error")
            resp = web.json_response({"ok": False, "error": "server_error"}, status=500)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


def create_api_app(bot, bot_username: str) -> web.Application:
    app = web.Application(middlewares=[cors_middleware])
    app["bot"] = bot
    app["bot_username"] = bot_username
    app.router.add_get("/", health)
    app.router.add_get("/api/health", health)
    app.router.add_post("/api/state", state)
    app.router.add_post("/api/ad/claim", ad_claim)
    app.router.add_post("/api/task/claim", task_claim)
    app.router.add_post("/api/withdraw", withdraw)
    app.router.add_post("/api/admin/settings", admin_settings)
    app.router.add_get("/adsgram/reward", adsgram_reward_callback)
    async def _preflight(_request):
        return web.Response(status=204)

    app.router.add_route("OPTIONS", "/{tail:.*}", _preflight)
    return app
