import asyncio
import logging
import html
import json
from aiohttp import web
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    MenuButtonWebApp,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

import config
import database as db
from api import create_api_app

# Setup Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def get_main_keyboard():
    """Persistent reply keyboard providing 1-click access to the Mini App."""
    keyboard = [
        [KeyboardButton("🚀 Open Payjust App", web_app=WebAppInfo(url=config.WEBAPP_URL))],
        [KeyboardButton("👥 My Invite Link"), KeyboardButton("💳 Withdrawal Info")],
        [KeyboardButton("💰 My Balance"), KeyboardButton("ℹ️ About & Support")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    first_name = user.first_name or "User"
    username = user.username or ""

    # Referral handling
    referrer_id = None
    if context.args and len(context.args) > 0 and context.args[0].isdigit():
        referrer_id = int(context.args[0])
        if referrer_id == user_id or not db.get_user(referrer_id):
            referrer_id = None  # self-referral ya unknown referrer ignore

    is_new = db.register_user(user_id, first_name, username, referrer_id)
    if is_new and referrer_id:
        ref_reward = float(db.get_setting("referral_reward", config.REFERRAL_REWARD_USD))
        if db.credit_referral(referrer_id, ref_reward):
            try:
                await context.bot.send_message(
                    chat_id=referrer_id,
                    text=(
                        f"🎉 <b>New Referral Joined!</b>\n"
                        f"👤 <b>{html.escape(first_name)}</b> joined using your invite link.\n"
                        f"➕ <b>+${ref_reward:.2f}</b> added to your balance!"
                    ),
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.info(f"Referrer notification failed: {e}")

    # Welcome Message matching client Screenshot 1 exactly
    ad_reward = db.get_setting("ad_reward", config.AD_REWARD_USD)
    ref_reward = db.get_setting("referral_reward", config.REFERRAL_REWARD_USD)
    task_reward = db.get_setting("task_reward", config.TASK_REWARD_USD)

    welcome_text = (
        f"<b>Welcome to Payjust +$</b>\n"
        f"Payjust, the first and easiest way of earning money inside telegram.\n\n"
        f"💰 <b>Earning Ways:</b>\n"
        f"✓ Per watching 10sec Ad {ad_reward}$\n"
        f"✓ Per inviting friend {ref_reward}$\n"
        f"✓ Per completing task {task_reward}$\n\n"
        f"💳 <b>Payment methods:</b>\n"
        f"Crypto • PayPal • Mobile Topup\n\n"
        f"Launch the app and start earning now\n"
        f"👇"
    )

    inline_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("Start Earning 🚀💰", web_app=WebAppInfo(url=config.WEBAPP_URL))]
    ])

    await update.message.reply_text(welcome_text, reply_markup=inline_markup, parse_mode="HTML")
    await update.message.reply_text("💡 You can also use the menu button below anytime to open the app:", reply_markup=get_main_keyboard())


# ========== LEGACY WEBAPP sendData ==========
async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Purana flow: client khud 'amount' bhejta tha -> koi bhi fake amount credit kar sakta tha.
    Ab saare rewards API (api.py) se verified initData ke saath aate hain, isliye yahan kuch credit nahi hota.
    """
    try:
        data = json.loads(update.effective_message.web_app_data.data)
    except Exception:
        data = {}
    logger.info(f"Ignored legacy web_app_data from {update.effective_user.id}: {data.get('event')}")
    await update.message.reply_text(
        "ℹ️ App update ho gaya hai. Please app dobara open karein 👇",
        reply_markup=get_main_keyboard(),
    )


# ========== INVITE LINK & WITHDRAWAL INFO ==========
async def handle_invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ref_link = f"https://t.me/{context.bot.username}?start={user_id}"
    ref_reward = db.get_setting("referral_reward", config.REFERRAL_REWARD_USD)

    text = (
        f"👥 <b>Your Referral Program</b>\n\n"
        f"Invite friends and earn <b>${ref_reward}</b> for every friend who joins!\n\n"
        f"🔗 <b>Your Personal Invite Link:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"Share this link on WhatsApp & Telegram groups to earn faster!"
    )
    from urllib.parse import quote
    share_text = f"Join Payjust +$ and earn rewards daily! Complete short ads and tasks: {ref_link}"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Share on Telegram", url=f"https://t.me/share/url?url={quote(ref_link)}&text={quote(share_text)}")],
        [InlineKeyboardButton("📱 Share on WhatsApp", url=f"https://api.whatsapp.com/send?text={quote(share_text)}")]
    ])
    await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")


async def handle_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    db.ensure_user(u.id, u.first_name or "User", u.username or "")
    row = db.get_user(u.id)
    await update.message.reply_text(
        f"💰 <b>Your Wallet</b>\n\n"
        f"Balance: <b>${row['balance']:.2f}</b>\n"
        f"Ads watched: <b>{row['ads_watched_total']}</b> (today {db.ads_watched_today(u.id)})\n"
        f"Friends invited: <b>{row['total_referrals']}</b>\n"
        f"Tasks done: <b>{len(db.get_completed_tasks(u.id))}/{len(config.TASKS)}</b>",
        parse_mode="HTML",
    )


async def handle_withdraw_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    min_w = db.get_setting("min_withdrawal", config.MIN_WITHDRAWAL_USD)
    req_inv = db.get_setting("required_invites", config.REQUIRED_INVITES)
    req_ads = db.get_setting("required_ads", config.REQUIRED_ADS)

    text = (
        f"💳 <b>Withdrawal Rules & Requirements:</b>\n\n"
        f"1. Minimum Balance: <b>${min_w}</b>\n"
        f"2. Invite Friends: <b>{req_inv} friends</b>\n"
        f"3. Complete All Tasks\n"
        f"4. Watch Ads: <b>{req_ads} ads total</b>\n\n"
        f"🚀 Open the app to check your progress and submit withdrawal request!"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Open App & Check 🚀", web_app=WebAppInfo(url=config.WEBAPP_URL))]
    ])
    await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")


async def handle_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"ℹ️ <b>About Payjust +$</b>\n\n"
        f"Payjust is a rewards platform monetized via official sponsor ads.\n"
        f"• Zero investment required\n"
        f"• Payouts via USDT TRC20, PayPal, Mobile Top-Up (manual admin review)\n\n"
        f"Support: @Mahadev5772"
    )
    await update.message.reply_text(text, parse_mode="HTML")


# ========== ADMIN PANEL COMMAND (/admin) ==========
def _admin_panel():
    stats = db.get_stats_summary()
    settings = db.get_all_settings()
    text = (
        f"👑 <b>Payjust Admin Panel</b>\n\n"
        f"📊 <b>System Statistics:</b>\n"
        f"• Total Users: <b>{stats['total_users']}</b>\n"
        f"• Total Balance in System: <b>${stats['total_balance']}</b>\n"
        f"• Total Ads Watched: <b>{stats['total_ads']}</b> (today {stats['ads_today']})\n"
        f"• Pending Withdrawals: <b>{stats['pending_withdrawals']}</b>\n\n"
        f"⚙️ <b>Live Settings:</b>\n"
        f"• Ad Reward: <b>${settings.get('ad_reward')}</b>\n"
        f"• Referral Reward: <b>${settings.get('referral_reward')}</b>\n"
        f"• Task Reward: <b>${settings.get('task_reward')}</b>\n"
        f"• Daily Ad Limit: <b>{settings.get('daily_ad_limit')}</b>\n"
        f"• Min Withdrawal: <b>${settings.get('min_withdrawal')}</b>\n"
        f"• Required Invites: <b>{settings.get('required_invites')}</b>\n"
        f"• Required Ads: <b>{settings.get('required_ads')}</b>\n"
        f"• Adsgram Block: <b>{settings.get('adsgram_block_id')}</b> "
        f"({'TEST/DEBUG' if config.ADSGRAM_DEBUG else 'LIVE'})\n"
        f"• API: <code>{config.API_PUBLIC_URL or 'NOT SET ⚠️'}</code>\n"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 View Pending Payouts", callback_data="adm_view_payouts")],
        [InlineKeyboardButton("✏️ Set Ad Reward", callback_data="adm_set_ad_reward"), InlineKeyboardButton("✏️ Set Ref Reward", callback_data="adm_set_referral_reward")],
        [InlineKeyboardButton("✏️ Set Min Withdraw", callback_data="adm_set_min_withdrawal"), InlineKeyboardButton("✏️ Set Req Invites", callback_data="adm_set_required_invites")],
        [InlineKeyboardButton("✏️ Set Daily Limit", callback_data="adm_set_daily_ad_limit"), InlineKeyboardButton("✏️ Set Req Ads", callback_data="adm_set_required_ads")],
        [InlineKeyboardButton("✏️ Set Adsgram Block", callback_data="adm_set_adsgram_block_id")],
        [InlineKeyboardButton("🔄 Refresh Stats", callback_data="adm_refresh")]
    ])
    return text, kb


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != config.ADMIN_ID:
        await update.message.reply_text("⛔ You are not authorized to view the admin panel.")
        return
    text, kb = _admin_panel()
    await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")


# Admin Callback Handler
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if update.effective_user.id != config.ADMIN_ID:
        await query.answer("⛔ Not authorized", show_alert=True)
        return
    await query.answer()
    data = query.data

    if data.startswith("adm_app_") or data.startswith("adm_rej_"):
        approve = data.startswith("adm_app_")
        try:
            w_id = int(data.split("_")[2])
        except (IndexError, ValueError):
            return
        w = db.resolve_withdrawal(w_id, approve)
        if not w:
            await query.edit_message_text(f"ℹ️ Request #{w_id} already processed ya exist nahi karti.")
            return
        if approve:
            await query.edit_message_text(f"✅ Request #{w_id} <b>APPROVED</b> (${w['amount']:.2f}).", parse_mode="HTML")
            user_text = f"🎉 <b>Payout Sent!</b>\n\nYour withdrawal request #{w_id} has been approved and processed."
        else:
            await query.edit_message_text(f"❌ Request #{w_id} <b>REJECTED</b> and ${w['amount']:.2f} refunded.", parse_mode="HTML")
            user_text = f"⚠️ Your withdrawal request #{w_id} was rejected. <b>${w['amount']:.2f}</b> has been refunded to your wallet."
        try:
            await context.bot.send_message(chat_id=w["user_id"], text=user_text, parse_mode="HTML")
        except Exception:
            pass

    elif data == "adm_view_payouts":
        payouts = db.get_pending_withdrawals(limit=10)
        if not payouts:
            await query.edit_message_text("✅ No pending withdrawal requests right now.")
            return
        await query.edit_message_text("📋 <b>Pending Withdrawal Requests:</b>", parse_mode="HTML")
        for p in payouts:
            await context.bot.send_message(
                chat_id=config.ADMIN_ID,
                text=(
                    f"#{p['id']} • <b>${p['amount']:.2f}</b> • {html.escape(p['method'] or '')}\n"
                    f"👤 {html.escape(p.get('first_name') or '')} (<code>{p['user_id']}</code>)\n"
                    f"💳 <code>{html.escape(p['payment_details'] or '')}</code>"
                ),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ Approve", callback_data=f"adm_app_{p['id']}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"adm_rej_{p['id']}"),
                ]]),
            )

    elif data.startswith("adm_set_"):
        key = data[len("adm_set_"):]
        if key not in db.ALLOWED_SETTINGS:
            return
        context.user_data["awaiting_setting"] = key
        await context.bot.send_message(
            chat_id=config.ADMIN_ID,
            text=f"✏️ <b>{key}</b> ki nayi value bhejein (current: <code>{db.get_setting(key)}</code>)\n/cancel se cancel karein.",
            parse_mode="HTML",
        )

    elif data == "adm_refresh":
        text, kb = _admin_panel()
        await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")


async def admin_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin ne 'Set ...' button dabaya ho to agla text message us setting ki value hai."""
    if update.effective_user.id != config.ADMIN_ID:
        return
    key = context.user_data.get("awaiting_setting")
    if not key:
        return
    raw = update.message.text.strip()
    try:
        value = db.ALLOWED_SETTINGS[key](raw)
        if isinstance(value, (int, float)) and value < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ Invalid value. Number bhejein (ya /cancel).")
        return
    db.set_setting(key, value)
    context.user_data.pop("awaiting_setting", None)
    await update.message.reply_text(f"✅ <b>{key}</b> = <code>{value}</code> saved.", parse_mode="HTML")


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("awaiting_setting", None)
    await update.message.reply_text("❎ Cancelled.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Unhandled bot error", exc_info=context.error)


async def run():
    db.init_db()
    if not config.API_PUBLIC_URL:
        logger.warning(
            "⚠️ API_PUBLIC_URL set nahi hai! Mini App balance/ads sync nahi kar payega. "
            "HTTPS public URL (Render/Railway/VPS/cloudflared) set karein."
        )

    app = ApplicationBuilder().token(config.BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("balance", handle_balance))
    app.add_handler(CommandHandler("cancel", cancel_command))

    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))
    app.add_handler(MessageHandler(filters.Regex("^👥 My Invite Link$"), handle_invite))
    app.add_handler(MessageHandler(filters.Regex("^💳 Withdrawal Info$"), handle_withdraw_info))
    app.add_handler(MessageHandler(filters.Regex("^💰 My Balance$"), handle_balance))
    app.add_handler(MessageHandler(filters.Regex("^ℹ️ About & Support$"), handle_about))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text_input))

    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^adm_"))
    app.add_error_handler(error_handler)

    await app.initialize()
    bot_username = app.bot.username

    # Chat ke niche permanent "Open App" menu button
    try:
        await app.bot.set_chat_menu_button(
    # 1. Start API server FIRST so Render port detection passes immediately
    api_app = create_api_app(app.bot, bot_username)
    runner = web.AppRunner(api_app)
    await runner.setup()
    site = web.TCPSite(runner, config.API_HOST, config.API_PORT)
    await site.start()
    print(f"🌐 API listening on http://{config.API_HOST}:{config.API_PORT} (public: {config.API_PUBLIC_URL or 'NOT SET'})", flush=True)
    print(f"📱 WebApp URL: {config.WEBAPP_URL}", flush=True)

    # 2. Set permanent menu button
    try:
        await app.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="Open App", web_app=WebAppInfo(url=config.WEBAPP_URL))
        )
        print("✅ Menu button configured", flush=True)
    except Exception as e:
        logger.warning(f"Menu button set failed: {e}")

    # 3. Start Telegram Polling
    await app.start()
    await app.updater.start_polling(drop_pending_updates=False)
    print(f"🤖 @{bot_username} running (bot + API). Press Ctrl+C to stop.", flush=True)

    try:
        await asyncio.Event().wait()
    finally:
        print("Stopping bot and API server...", flush=True)
        try:
            await app.updater.stop()
            await app.stop()
            await app.shutdown()
        except Exception:
            pass
        await runner.cleanup()


def main():
    import sys
    print(">>> Starting Payjust Bot process...", flush=True)
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit):
        print(">>> Bot process stopped gracefully.", flush=True)
    except Exception as e:
        import traceback
        print(">>> FATAL ERROR IN BOT PROCESS:", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        sys.exit(1)


if __name__ == "__main__":
    main()
