"""Main entry — Telegram bot, scheduler, all command handlers wired together."""

import asyncio
import logging
import secrets
import yaml
from datetime import datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, CallbackQueryHandler, CommandHandler,
    ContextTypes, MessageHandler, filters,
)

import storage
import parsing
from integrations import homekit, weather, trash, alerts, geocode
from integrations import gmail_client, calendar_client, event_extractor

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "config.yaml"

log = logging.getLogger("bot")


# ---------- config ----------

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Missing {CONFIG_PATH}. Copy config.example.yaml to config.yaml and fill it in.")
    return yaml.safe_load(CONFIG_PATH.read_text())


CFG = load_config()
AUTHORIZED_USER_ID: int = CFG["telegram"]["authorized_user_id"]


# ---------- auth gate ----------

def authorized(handler):
    """Decorator: bounce non-authorized users."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user is None or user.id != AUTHORIZED_USER_ID:
            log.warning("rejected message from %s", user)
            if update.message:
                await update.message.reply_text("Not authorized.")
            return
        return await handler(update, context)
    return wrapper


# ---------- helpers ----------

async def send(update_or_chat, text: str, **kwargs):
    if hasattr(update_or_chat, "message") and update_or_chat.message:
        return await update_or_chat.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, **kwargs)
    return await update_or_chat.bot.send_message(
        chat_id=AUTHORIZED_USER_ID, text=text, parse_mode=ParseMode.MARKDOWN, **kwargs
    )


def require_location(update_or_msg=None) -> dict | None:
    """Return location dict or None. Caller responsible for messaging."""
    return storage.get_location()


# ---------- generic commands ----------

@authorized
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not storage.get_location():
        await send(update,
            "👋 Hi Mari. Before we start, where are you?\n\n"
            "Send: `/setlocation <postcode> <house number>`\n"
            "e.g. `/setlocation 1011AB 42`\n\n"
            "I'll use this for weather + trash pickup."
        )
        return
    await send(update, _help_text())


@authorized
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send(update, _help_text())


def _help_text() -> str:
    loc = storage.get_location()
    loc_line = f"📍 {loc['address']}" if loc else "📍 Location not set — `/setlocation <postcode> <hnr>`"
    return (
        f"*Mari's bot* — {loc_line}\n\n"
        "*Reminders*\n"
        "  /remind every Tuesday 19:00 take out trash\n"
        "  /remind tomorrow 9am dentist\n"
        "  /remind in 2 hours water plants\n"
        "  /list — show active reminders\n"
        "  /delete <id> — remove one\n\n"
        "*Home*\n"
        "  /lights on  | /lights off  | /scene <name>\n"
        "  /lock front_door | /unlock front_door\n"
        "  /shortcuts — list available Apple Shortcuts\n\n"
        "*Info*\n"
        "  /weather — current + today's forecast\n"
        "  /trash — upcoming pickups\n"
        "  /today — today's calendar events\n"
        "  /briefing — full morning briefing now\n\n"
        "*Settings*\n"
        "  /setlocation <postcode> <hnr> — change address\n"
        "  /location — show current address"
    )


# ---------- location ----------

@authorized
async def cmd_setlocation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await send(update,
            "Usage: `/setlocation <postcode> <house number>`\n"
            "e.g. `/setlocation 1011AB 42`"
        )
        return
    postcode = context.args[0]
    house_number = " ".join(context.args[1:])  # in case of "42 A"

    await update.message.chat.send_action("typing")
    try:
        result = geocode.geocode_nl(postcode, house_number)
    except geocode.GeocodeError as e:
        await send(update, f"⚠️ {e}")
        return

    storage.set_setting("location", {
        "postcode": postcode.replace(" ", "").upper(),
        "house_number": str(house_number),
        "lat": result["lat"],
        "lon": result["lon"],
        "address": result["address"],
    })
    await send(update,
        f"✅ Location set:\n  *{result['address']}*\n  ({result['lat']:.4f}, {result['lon']:.4f})\n\n"
        f"Try `/weather` or `/trash` next."
    )


@authorized
async def cmd_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    loc = storage.get_location()
    if not loc:
        await send(update, "📍 No location set. Use `/setlocation <postcode> <hnr>`.")
        return
    await send(update,
        f"📍 *{loc['address']}*\n"
        f"  Postcode: {loc['postcode']}\n"
        f"  House #: {loc['house_number']}\n"
        f"  Coords: {loc['lat']:.4f}, {loc['lon']:.4f}"
    )


# ---------- reminders ----------

@authorized
async def cmd_remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args).strip()
    if not text:
        await send(update, "Usage: `/remind every Tuesday 19:00 take out trash`")
        return
    try:
        kind, spec, body = parsing.parse(text)
    except parsing.ParseError as e:
        await send(update, str(e))
        return

    rid = storage.add_reminder(body, kind, spec)
    _schedule_reminder(context.application, rid, kind, spec, body)

    when_str = spec if kind == "once" else f"cron `{spec}`"
    await send(update, f"✅ Reminder #{rid} scheduled\n  → {body}\n  → {when_str}")


@authorized
async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = storage.list_reminders()
    if not rows:
        await send(update, "No active reminders.")
        return
    lines = ["*Active reminders:*"]
    for r in rows:
        lines.append(f"  #{r['id']} — {r['text']}  _({r['schedule_kind']}: {r['schedule_spec']})_")
    await send(update, "\n".join(lines))


@authorized
async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await send(update, "Usage: `/delete 3`")
        return
    try:
        rid = int(context.args[0])
    except ValueError:
        await send(update, "ID must be a number.")
        return
    ok = storage.delete_reminder(rid)
    job_id = f"reminder-{rid}"
    sched: AsyncIOScheduler = context.application.bot_data["scheduler"]
    if sched.get_job(job_id):
        sched.remove_job(job_id)
    await send(update, "🗑 Deleted." if ok else "Not found.")


def _schedule_reminder(app, rid: int, kind: str, spec: str, text: str):
    sched: AsyncIOScheduler = app.bot_data["scheduler"]
    job_id = f"reminder-{rid}"
    if sched.get_job(job_id):
        sched.remove_job(job_id)
    if kind == "cron":
        m, h, dom, mon, dow = spec.split()
        trigger = CronTrigger(minute=m, hour=h, day=dom, month=mon, day_of_week=dow,
                              timezone="Europe/Amsterdam")
    else:
        trigger = DateTrigger(run_date=datetime.fromisoformat(spec))
    sched.add_job(
        _fire_reminder, trigger, args=[app, rid, text],
        id=job_id, replace_existing=True,
    )


async def _fire_reminder(app, rid: int, text: str):
    log.info("firing reminder #%s: %s", rid, text)
    await app.bot.send_message(
        chat_id=AUTHORIZED_USER_ID,
        text=f"🔔 *Reminder*\n{text}",
        parse_mode=ParseMode.MARKDOWN,
    )


# ---------- HomeKit ----------

@authorized
async def cmd_lights(update: Update, context: ContextTypes.DEFAULT_TYPE):
    arg = (context.args[0] if context.args else "").lower()
    cfg = CFG["homekit"]["lights"]
    if arg in ("on", "off"):
        try:
            await homekit.run_shortcut(cfg[arg])
            await send(update, f"💡 Lights {arg}.")
        except homekit.ShortcutError as e:
            await send(update, f"⚠️ {e}")
        return
    await send(update, "Usage: `/lights on` or `/lights off`")


@authorized
async def cmd_scene(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        scenes = ", ".join(CFG["homekit"]["lights"].get("scenes", {}).keys()) or "(none configured)"
        await send(update, f"Usage: `/scene <name>`\nAvailable: {scenes}")
        return
    name = context.args[0].lower()
    scenes = CFG["homekit"]["lights"].get("scenes", {})
    if name not in scenes:
        await send(update, f"Unknown scene `{name}`.")
        return
    try:
        await homekit.run_shortcut(scenes[name])
        await send(update, f"🎬 Scene: {name}")
    except homekit.ShortcutError as e:
        await send(update, f"⚠️ {e}")


@authorized
async def cmd_lock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _lock_action(update, context, action="lock")


@authorized
async def cmd_unlock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _lock_action(update, context, action="unlock")


async def _lock_action(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str):
    if not context.args:
        names = ", ".join(CFG["homekit"]["locks"].keys())
        await send(update, f"Usage: `/{action} <lock>`\nAvailable: {names}")
        return
    lock_key = context.args[0]
    locks = CFG["homekit"]["locks"]
    if lock_key not in locks:
        await send(update, f"Unknown lock `{lock_key}`.")
        return
    cfg = locks[lock_key]
    shortcut_name = cfg[action]

    if cfg.get("require_confirmation", True):
        token = secrets.token_urlsafe(8)
        storage.stash_confirmation(token, action, {"shortcut": shortcut_name, "lock": lock_key})
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(f"✅ Confirm {action}", callback_data=f"lk:{token}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"lkx:{token}"),
        ]])
        await update.message.reply_text(f"Confirm: *{action} {lock_key}*?", reply_markup=kb,
                                        parse_mode=ParseMode.MARKDOWN)
        return

    try:
        await homekit.run_shortcut(shortcut_name)
        await send(update, f"🔒 {action.title()}ed {lock_key}.")
    except homekit.ShortcutError as e:
        await send(update, f"⚠️ {e}")


@authorized
async def cmd_shortcuts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    names = await homekit.list_shortcuts()
    head = names[:60]
    suffix = f"\n…and {len(names) - 60} more" if len(names) > 60 else ""
    await send(update, "*Installed shortcuts:*\n" + "\n".join(f"  • {n}" for n in head) + suffix)


# ---------- info commands ----------

@authorized
async def cmd_weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    loc = storage.get_location()
    if not loc:
        await send(update, "📍 Set your location first: `/setlocation <postcode> <hnr>`")
        return
    w = weather.fetch_weather(loc["lat"], loc["lon"])
    msg = weather.format_weather(w)
    a = alerts.fetch_alerts()
    if a:
        msg += "\n\n" + alerts.format_alerts(a)
    await send(update, msg)


@authorized
async def cmd_trash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    loc = storage.get_location()
    if not loc:
        await send(update, "📍 Set your location first: `/setlocation <postcode> <hnr>`")
        return
    msg = trash.format_upcoming(loc["postcode"], loc["house_number"])
    await send(update, msg)


@authorized
async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    events = calendar_client.list_today_events(CFG["email_scan"]["target_calendar_id"])
    await send(update, calendar_client.format_today_events(events))


@authorized
async def cmd_briefing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = await build_briefing()
    await send(update, text)


async def build_briefing() -> str:
    loc = storage.get_location()
    parts = ["☀️ *Morning briefing*", ""]
    if not loc:
        parts.append("📍 Location not set — weather and trash skipped.\n"
                     "Run `/setlocation <postcode> <hnr>` to enable.")
    else:
        if CFG["briefing"].get("include_weather", True):
            parts.append(weather.format_weather(weather.fetch_weather(loc["lat"], loc["lon"])))
        if CFG["briefing"].get("include_trash", True):
            upcoming = trash.format_today_tomorrow(loc["postcode"], loc["house_number"])
            if upcoming:
                parts.append(upcoming)

    if CFG["briefing"].get("include_calendar_today", True):
        try:
            events = calendar_client.list_today_events(CFG["email_scan"]["target_calendar_id"])
            parts.append(calendar_client.format_today_events(events))
        except Exception as e:
            parts.append(f"📅 (calendar unavailable: {e})")

    a = alerts.fetch_alerts()
    if a:
        parts.append(alerts.format_alerts(a))
    return "\n\n".join(parts)


# ---------- inline button callbacks ----------

async def cb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != AUTHORIZED_USER_ID:
        await query.edit_message_text("Not authorized.")
        return

    data = query.data or ""
    if data.startswith("lk:") or data.startswith("lkx:"):
        token = data.split(":", 1)[1]
        confirmed = data.startswith("lk:")
        rec = storage.pop_confirmation(token)
        if not rec:
            await query.edit_message_text("Confirmation expired.")
            return
        kind, payload = rec
        if not confirmed:
            await query.edit_message_text(f"❌ {kind} cancelled.")
            return
        try:
            await homekit.run_shortcut(payload["shortcut"])
            await query.edit_message_text(f"🔒 {kind.title()}ed {payload['lock']}.")
        except homekit.ShortcutError as e:
            await query.edit_message_text(f"⚠️ {e}")
        return

    if data.startswith("ev:") or data.startswith("evx:"):
        token = data.split(":", 1)[1]
        rec = storage.pop_confirmation(token)
        if not rec:
            await query.edit_message_text("Confirmation expired.")
            return
        _, payload = rec
        if data.startswith("evx:"):
            storage.mark_email_processed(payload["message_id"], event_added=False)
            await query.edit_message_text("❌ Skipped.")
            return
        try:
            ev = calendar_client.create_event(
                CFG["email_scan"]["target_calendar_id"],
                summary=payload["summary"],
                start=datetime.fromisoformat(payload["start_iso"]),
                end=datetime.fromisoformat(payload["end_iso"]),
                description=payload.get("description"),
                location=payload.get("location"),
            )
            storage.mark_email_processed(payload["message_id"], event_added=True,
                                         calendar_event_id=ev.get("id"))
            link = ev.get("htmlLink", "")
            await query.edit_message_text(f"✅ Added: {payload['summary']}\n{link}")
        except Exception as e:
            log.exception("calendar insert failed")
            await query.edit_message_text(f"⚠️ Insert failed: {e}")


# ---------- scheduled jobs ----------

async def job_morning_briefing(app):
    text = await build_briefing()
    await app.bot.send_message(chat_id=AUTHORIZED_USER_ID, text=text, parse_mode=ParseMode.MARKDOWN)


async def job_poll_email(app):
    """Poll Gmail, propose any detected events to the user."""
    cfg = CFG["email_scan"]
    api_key = (CFG.get("llm") or {}).get("anthropic_api_key", "")
    if not api_key:
        log.debug("email scan disabled (no anthropic_api_key)")
        return

    try:
        ids = gmail_client.list_recent_messages(
            labels=cfg.get("labels", ["INBOX"]),
            lookback_days=1,
        )
    except Exception as e:
        log.warning("gmail list failed: %s", e)
        return

    for mid in ids:
        if storage.is_email_processed(mid):
            continue
        try:
            email = gmail_client.get_message(mid)
        except Exception as e:
            log.warning("fetch %s failed: %s", mid, e)
            continue

        try:
            result = event_extractor.extract_event(api_key, CFG["llm"]["model"], email)
        except Exception as e:
            log.warning("extractor failed: %s", e)
            storage.mark_email_processed(mid, event_added=False)
            continue

        if not result.get("event") or result.get("confidence", 0) < 0.6:
            storage.mark_email_processed(mid, event_added=False)
            continue

        token = secrets.token_urlsafe(8)
        payload = {
            "message_id": mid,
            "summary": result["summary"],
            "start_iso": result["start_iso"],
            "end_iso": result["end_iso"],
            "location": result.get("location"),
            "description": f"Auto-detected from email:\n{email.get('subject','')}\n— {email.get('from','')}",
        }
        storage.stash_confirmation(token, "event", payload)
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Add", callback_data=f"ev:{token}"),
            InlineKeyboardButton("❌ Skip", callback_data=f"evx:{token}"),
        ]])
        msg = (
            "📧 *Possible event from email*\n"
            f"  *{result['summary']}*\n"
            f"  {result['start_iso']} → {result['end_iso']}\n"
            f"  {result.get('location') or ''}\n"
            f"  _from: {email.get('from','')}_"
        )
        await app.bot.send_message(
            chat_id=AUTHORIZED_USER_ID, text=msg,
            reply_markup=kb, parse_mode=ParseMode.MARKDOWN,
        )


# ---------- bootstrap ----------

async def post_init(app):
    storage.init_db()
    sched = AsyncIOScheduler(timezone="Europe/Amsterdam")
    app.bot_data["scheduler"] = sched

    # Hydrate reminders from DB
    for r in storage.list_reminders():
        try:
            _schedule_reminder(app, r["id"], r["schedule_kind"], r["schedule_spec"], r["text"])
        except Exception as e:
            log.warning("skip reminder %s: %s", r["id"], e)

    # Daily briefing
    h, m = CFG["briefing"]["time"].split(":")
    sched.add_job(
        job_morning_briefing, CronTrigger(hour=int(h), minute=int(m), timezone="Europe/Amsterdam"),
        args=[app], id="morning-briefing", replace_existing=True,
    )

    # Email polling
    poll = int(CFG.get("email_scan", {}).get("poll_minutes", 30))
    sched.add_job(
        job_poll_email, "interval", minutes=poll,
        args=[app], id="email-poll", replace_existing=True,
        next_run_time=datetime.now() + timedelta(seconds=30),
    )

    sched.start()
    log.info("scheduler started, %d jobs", len(sched.get_jobs()))

    # First-run nudge if location not set
    if not storage.get_location():
        try:
            await app.bot.send_message(
                chat_id=AUTHORIZED_USER_ID,
                text=(
                    "👋 Bot is up. One thing left: send me your address.\n\n"
                    "`/setlocation <postcode> <house number>`\n"
                    "e.g. `/setlocation 1011AB 42`"
                ),
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            log.warning("welcome message failed: %s", e)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(ROOT / "bot.log"), logging.StreamHandler()],
    )

    app = (
        ApplicationBuilder()
        .token(CFG["telegram"]["bot_token"])
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("setlocation", cmd_setlocation))
    app.add_handler(CommandHandler("location", cmd_location))
    app.add_handler(CommandHandler("remind", cmd_remind))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("delete", cmd_delete))
    app.add_handler(CommandHandler("lights", cmd_lights))
    app.add_handler(CommandHandler("scene", cmd_scene))
    app.add_handler(CommandHandler("lock", cmd_lock))
    app.add_handler(CommandHandler("unlock", cmd_unlock))
    app.add_handler(CommandHandler("shortcuts", cmd_shortcuts))
    app.add_handler(CommandHandler("weather", cmd_weather))
    app.add_handler(CommandHandler("trash", cmd_trash))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("briefing", cmd_briefing))
    app.add_handler(CallbackQueryHandler(cb_handler))

    log.info("starting polling")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
