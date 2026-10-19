import math
import os
import sqlite3
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple
import config

# Absolute path so DB same rahe chahe bot kisi bhi folder se start ho (can be overridden by DB_PATH env var)
DB_PATH = os.getenv("DB_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_data.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _utc_day_start() -> float:
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, now.day, tzinfo=timezone.utc).timestamp()


def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")

    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            balance REAL DEFAULT 0.0,
            referred_by INTEGER,
            total_referrals INTEGER DEFAULT 0,
            ads_watched_total INTEGER DEFAULT 0,
            tasks_completed INTEGER DEFAULT 0,
            last_bonus_time REAL DEFAULT 0,
            joined_at REAL
        )
    """)

    # Try adding columns if existing database table is older
    for col, col_type in [
        ("ads_watched_total", "INTEGER DEFAULT 0"),
        ("tasks_completed", "INTEGER DEFAULT 0"),
        ("ad_earned_total", "REAL DEFAULT 0.0"),
        ("last_ad_time", "REAL DEFAULT 0"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass

    # Every rewarded ad view (daily limit + audit trail)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ad_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            source TEXT,
            created_at REAL
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ad_views_user_time ON ad_views(user_id, created_at)")

    # Completed tasks per user
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_tasks (
            user_id INTEGER,
            task_id INTEGER,
            completed_at REAL,
            PRIMARY KEY (user_id, task_id)
        )
    """)

    # Withdrawals table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            method TEXT DEFAULT 'USDT',
            payment_details TEXT,
            status TEXT DEFAULT 'PENDING',
            created_at REAL
        )
    """)
    for col, col_type in [
        ("method", "TEXT DEFAULT 'USDT'"),
        ("payment_details", "TEXT"),
        ("status", "TEXT DEFAULT 'PENDING'"),
        ("created_at", "REAL"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE withdrawals ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass

    # App Settings table for Admin Panel dynamic control
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # Initialize default settings if missing
    defaults = {
        "ad_reward": str(config.AD_REWARD_USD),
        "referral_reward": str(config.REFERRAL_REWARD_USD),
        "task_reward": str(config.TASK_REWARD_USD),
        "daily_ad_limit": str(config.DAILY_AD_LIMIT),
        "min_withdrawal": str(config.MIN_WITHDRAWAL_USD),
        "required_invites": str(config.REQUIRED_INVITES),
        "required_ads": str(config.REQUIRED_ADS),
        "adsgram_block_id": str(config.ADSGRAM_BLOCK_ID),
        "task_1_url": config.TASKS[0]["url"] if config.TASKS else "https://t.me/Payjust_bot",
        "task_1_chat": config.TASKS[0].get("chat") or "",
        "task_4_url": config.TASKS[-1]["url"] if len(config.TASKS) > 1 else "https://t.me/Payjust_bot",
        "task_4_chat": config.TASKS[-1].get("chat") or "",
    }
    for k, v in defaults.items():
        cursor.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)", (k, v))

    conn.commit()
    conn.close()


# ---------------- SETTINGS ----------------
ALLOWED_SETTINGS = {
    "ad_reward": float,
    "referral_reward": float,
    "task_reward": float,
    "daily_ad_limit": int,
    "min_withdrawal": float,
    "required_invites": int,
    "required_ads": int,
    "adsgram_block_id": str,
    "task_1_url": str,
    "task_1_chat": str,
    "task_4_url": str,
    "task_4_chat": str,
}

FALLBACK_SETTINGS = {
    "ad_reward": config.AD_REWARD_USD,
    "referral_reward": config.REFERRAL_REWARD_USD,
    "task_reward": config.TASK_REWARD_USD,
    "daily_ad_limit": config.DAILY_AD_LIMIT,
    "min_withdrawal": config.MIN_WITHDRAWAL_USD,
    "required_invites": config.REQUIRED_INVITES,
    "required_ads": config.REQUIRED_ADS,
    "adsgram_block_id": str(config.ADSGRAM_BLOCK_ID),
    "task_1_url": "https://t.me/Payjust_bot",
    "task_1_chat": "",
    "task_4_url": "https://t.me/Payjust_bot",
    "task_4_chat": "",
}


def get_setting(key: str, default: Any = None) -> str:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else str(default if default is not None else FALLBACK_SETTINGS.get(key, ""))


def set_setting(key: str, value: Any):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO app_settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = ?
    """, (key, str(value), str(value)))
    conn.commit()
    conn.close()


def get_all_settings() -> Dict[str, str]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM app_settings")
    rows = cursor.fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


def get_typed_settings() -> Dict[str, Any]:
    raw = get_all_settings()
    out: Dict[str, Any] = {}
    for k, caster in ALLOWED_SETTINGS.items():
        val = raw.get(k)
        try:
            parsed = caster(val) if val not in (None, "") else FALLBACK_SETTINGS.get(k)
            if isinstance(parsed, float) and not math.isfinite(parsed):
                parsed = FALLBACK_SETTINGS.get(k)
            out[k] = parsed
        except (TypeError, ValueError):
            out[k] = FALLBACK_SETTINGS.get(k)
    return out


def get_active_tasks() -> List[Dict[str, Any]]:
    s = get_all_settings()
    out = []
    for t in config.TASKS:
        tid = t["id"]
        url = (s.get(f"task_{tid}_url") or t.get("url") or "https://t.me/Payjust_bot").strip()
        chat = (s.get(f"task_{tid}_chat") or t.get("chat") or "").strip() or None
        out.append({
            "id": tid,
            "icon": t["icon"],
            "title": t["title"],
            "url": url,
            "chat": chat,
        })
    return out


# ---------------- USERS ----------------
def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def register_user(user_id: int, first_name: str, username: str, referrer_id: Optional[int] = None) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    existing = cursor.fetchone()
    if existing:
        if first_name and first_name != "User":
            cursor.execute(
                "UPDATE users SET first_name = ?, username = ? WHERE user_id = ?",
                (first_name, username or existing["username"] or "", user_id),
            )
        # Agar user ne pehle Mini App khol liya tha (ensure_user) aur ab /start <referrer_id> dabaya hai:
        if (
            referrer_id
            and referrer_id != user_id
            and not existing["referred_by"]
            and (existing["ads_watched_total"] or 0) == 0
            and (existing["tasks_completed"] or 0) == 0
            and (existing["total_referrals"] or 0) == 0
        ):
            cursor.execute("UPDATE users SET referred_by = ? WHERE user_id = ?", (referrer_id, user_id))
            conn.commit()
            conn.close()
            return True
        conn.commit()
        conn.close()
        return False

    now = time.time()
    cursor.execute("""
        INSERT INTO users (user_id, first_name, username, balance, referred_by, total_referrals, ads_watched_total, tasks_completed, joined_at)
        VALUES (?, ?, ?, 0.0, ?, 0, 0, 0, ?)
    """, (user_id, first_name, username, referrer_id, now))
    conn.commit()
    conn.close()
    return True


def ensure_user(user_id: int, first_name: str = "User", username: str = ""):
    """Mini App se aaye user ko register kar do agar /start nahi kiya tha."""
    register_user(user_id, first_name, username, None)


def credit_referral(referrer_id: int, reward: float) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users
        SET balance = balance + ?, total_referrals = total_referrals + 1
        WHERE user_id = ?
    """, (reward, referrer_id))
    ok = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return ok


def credit_points(user_id: int, amount: float):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users
        SET balance = balance + ?
        WHERE user_id = ?
    """, (amount, user_id))
    conn.commit()
    conn.close()


# ---------------- ADS ----------------
def ads_watched_today(user_id: int) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) AS c FROM ad_views WHERE user_id = ? AND created_at >= ?",
        (user_id, _utc_day_start()),
    )
    c = cursor.fetchone()["c"]
    conn.close()
    return c or 0


def credit_ad_view(user_id: int, amount: float, source: str = "client") -> Tuple[bool, str]:
    """
    Atomic ad reward: daily limit + cooldown server-side enforce hota hai.
    Returns (ok, reason).
    """
    settings = get_typed_settings()
    daily_limit = settings["daily_ad_limit"] or config.DAILY_AD_LIMIT
    now = time.time()

    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT last_ad_time FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            conn.rollback()
            return False, "user_not_found"

        if source == "client" and now - (row["last_ad_time"] or 0) < config.AD_COOLDOWN_SECONDS:
            conn.rollback()
            return False, "cooldown"

        today = conn.execute(
            "SELECT COUNT(*) AS c FROM ad_views WHERE user_id = ? AND created_at >= ?",
            (user_id, _utc_day_start()),
        ).fetchone()["c"]
        if today >= daily_limit:
            conn.rollback()
            return False, "daily_limit"

        conn.execute("""
            UPDATE users
            SET balance = balance + ?, ads_watched_total = ads_watched_total + 1,
                ad_earned_total = COALESCE(ad_earned_total, 0) + ?, last_ad_time = ?
            WHERE user_id = ?
        """, (amount, amount, now, user_id))
        conn.execute(
            "INSERT INTO ad_views (user_id, amount, source, created_at) VALUES (?, ?, ?, ?)",
            (user_id, amount, source, now),
        )
        conn.commit()
        return True, "ok"
    finally:
        conn.close()


# ---------------- TASKS ----------------
def get_completed_tasks(user_id: int) -> List[int]:
    conn = get_connection()
    rows = conn.execute("SELECT task_id FROM user_tasks WHERE user_id = ?", (user_id,)).fetchall()
    conn.close()
    return [r["task_id"] for r in rows]


def complete_task(user_id: int, task_id: int, reward: float) -> bool:
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            "INSERT OR IGNORE INTO user_tasks (user_id, task_id, completed_at) VALUES (?, ?, ?)",
            (user_id, task_id, time.time()),
        )
        if cur.rowcount == 0:
            conn.rollback()
            return False  # already done
        conn.execute(
            "UPDATE users SET balance = balance + ?, tasks_completed = tasks_completed + 1 WHERE user_id = ?",
            (reward, user_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


# ---------------- WITHDRAWALS ----------------
def create_withdrawal(user_id: int, amount: float, method: str, payment_details: str) -> Optional[int]:
    if not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount <= 0:
        return None
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if not row or not math.isfinite(row["balance"]) or row["balance"] < amount:
            conn.rollback()
            return None

        now = time.time()
        conn.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
        cur = conn.execute("""
            INSERT INTO withdrawals (user_id, amount, method, payment_details, status, created_at)
            VALUES (?, ?, ?, ?, 'PENDING', ?)
        """, (user_id, amount, method, payment_details, now))
        withdrawal_id = cur.lastrowid
        conn.commit()
        return withdrawal_id
    finally:
        conn.close()


def get_withdrawal(withdrawal_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM withdrawals WHERE id = ?", (withdrawal_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_withdrawals(user_id: int, limit: int = 5) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, amount, method, payment_details AS address, status, created_at FROM withdrawals WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        items = [dict(r) for r in rows]
    except sqlite3.OperationalError:
        rows = conn.execute(
            "SELECT id, amount, payment_details AS address, status, created_at FROM withdrawals WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        items = [{**dict(r), "method": "USDT"} for r in rows]
    finally:
        conn.close()
    for it in items:
        if str(it.get("status") or "").upper() == "APPROVED":
            it["status"] = "PAID"
    return items


def get_pending_withdrawals(limit: int = 10) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT w.*, u.first_name, u.username
        FROM withdrawals w
        LEFT JOIN users u ON w.user_id = u.user_id
        WHERE w.status = 'PENDING'
        ORDER BY w.created_at DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_withdrawal_status(withdrawal_id: int, new_status: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE withdrawals SET status = ? WHERE id = ?", (new_status, withdrawal_id))
    conn.commit()
    conn.close()


def resolve_withdrawal(withdrawal_id: int, approve: bool) -> Optional[Dict[str, Any]]:
    """
    PENDING -> APPROVED/REJECTED sirf ek baar (double-click se double refund nahi hoga).
    Reject par amount DB se refund hota hai (callback_data se nahi).
    """
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM withdrawals WHERE id = ?", (withdrawal_id,)).fetchone()
        if not row or row["status"] != "PENDING":
            conn.rollback()
            return None
        new_status = "APPROVED" if approve else "REJECTED"
        conn.execute("UPDATE withdrawals SET status = ? WHERE id = ?", (new_status, withdrawal_id))
        if not approve:
            conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (row["amount"], row["user_id"]))
        conn.commit()
        result = dict(row)
        result["status"] = new_status
        return result
    finally:
        conn.close()


def get_stats_summary() -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as total_users, SUM(balance) as total_bal, SUM(ads_watched_total) as total_ads FROM users")
    u_row = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) as pending_w FROM withdrawals WHERE status = 'PENDING'")
    w_row = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) as c FROM ad_views WHERE created_at >= ?", (_utc_day_start(),))
    today_ads = cursor.fetchone()["c"]
    conn.close()
    return {
        "total_users": u_row["total_users"] or 0,
        "total_balance": round(u_row["total_bal"] or 0.0, 2),
        "total_ads": u_row["total_ads"] or 0,
        "ads_today": today_ads or 0,
        "pending_withdrawals": w_row["pending_w"] or 0
    }
