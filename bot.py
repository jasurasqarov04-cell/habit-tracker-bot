"""
Habit Tracker Bot — клавиатурные кнопки + пошаговое добавление
"""

import os
import logging
from datetime import datetime, time
import pytz
from dotenv import load_dotenv

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters, ContextTypes
)

from sheets_helper import SheetsHelper

load_dotenv()
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN")
ALLOWED_USER_ID = os.getenv("ALLOWED_USER_ID")
TIMEZONE        = os.getenv("TIMEZONE", "Asia/Tashkent")
DASHBOARD_URL   = os.getenv("DASHBOARD_URL", "")

sheets = SheetsHelper()

# ── Conversation states ───────────────────────────────────────────────────────
ADD_NAME, ADD_PLAN_AMOUNT, ADD_PLAN_UNIT = range(3)
DONE_AMOUNT = 10
DELETE_CONFIRM = 20

# ── Main keyboard ─────────────────────────────────────────────────────────────
MAIN_KB = ReplyKeyboardMarkup([
    [KeyboardButton("✅ Сделано"),   KeyboardButton("📋 Планы на сегодня")],
    [KeyboardButton("➕ Добавить"),  KeyboardButton("📝 Список")],
    [KeyboardButton("🗑 Удалить"),   KeyboardButton("📊 Статистика")],
    [KeyboardButton("📈 Дашборд")],
], resize_keyboard=True)

CANCEL_KB = ReplyKeyboardMarkup(
    [[KeyboardButton("❌ Отмена")]], resize_keyboard=True
)


async def check_access(update: Update) -> bool:
    if not ALLOWED_USER_ID:
        return True
    if str(update.effective_user.id) != str(ALLOWED_USER_ID):
        await update.message.reply_text("Этот бот приватный.")
        return False
    return True


def get_tz():
    return pytz.timezone(TIMEZONE)


def today_str():
    return datetime.now(get_tz()).strftime("%Y-%m-%d")


def time_str():
    return datetime.now(get_tz()).strftime("%H:%M")


def fmt_amount(v: float) -> str:
    return str(int(v)) if v == int(v) else str(v)


def progress_bar(pct: int, length: int = 8) -> str:
    filled = int(pct / 100 * length)
    empty  = length - filled
    if pct >= 70:   block = "🟩"
    elif pct >= 40: block = "🟨"
    else:           block = "🟥"
    return block * filled + "⬜" * empty


# ── /start ────────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    user = update.effective_user
    sheets.register_user(str(user.id), user.first_name)
    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\nВыбери действие:",
        reply_markup=MAIN_KB
    )


# ── ДОБАВИТЬ ЗАДАЧУ (пошагово) ────────────────────────────────────────────────

async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    await update.message.reply_text(
        "Введи название задачи/привычки:\n\nНапример: Отжимания",
        reply_markup=CANCEL_KB
    )
    return ADD_NAME


async def add_get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ Отмена":
        return await cancel(update, context)

    user_id = str(update.effective_user.id)
    result  = sheets.add_habit(user_id, text)
    context.user_data['new_habit'] = text

    if result == "exists":
        await update.message.reply_text(
            f"Задача «{text}» уже есть.\n\nТеперь задай план — сколько нужно делать?\n"
            "Введи число (например: 50) или напиши «нет» чтобы пропустить:",
            reply_markup=CANCEL_KB
        )
    else:
        await update.message.reply_text(
            f"✅ Задача «{text}» добавлена!\n\n"
            "Теперь задай план — сколько нужно делать?\n"
            "Введи число (например: 50) или напиши «нет» чтобы пропустить:",
            reply_markup=CANCEL_KB
        )
    return ADD_PLAN_AMOUNT


async def add_get_plan_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ Отмена":
        return await cancel(update, context)

    if text.lower() in ("нет", "no", "skip", "-"):
        habit = context.user_data.get('new_habit', '')
        await update.message.reply_text(
            f"Задача «{habit}» добавлена без плана.\n\nОтмечай выполнение кнопкой «✅ Сделано»",
            reply_markup=MAIN_KB
        )
        return ConversationHandler.END

    try:
        amount = float(text.replace(",", "."))
        context.user_data['plan_amount'] = amount
        await update.message.reply_text(
            f"Отлично! {fmt_amount(amount)} — это сколько?\n\n"
            "Введи единицу измерения:\n"
            "раз / минут / км / страниц / стаканов / часов / или своё",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("раз"),    KeyboardButton("минут")],
                [KeyboardButton("км"),     KeyboardButton("страниц")],
                [KeyboardButton("стаканов"), KeyboardButton("часов")],
                [KeyboardButton("❌ Отмена")],
            ], resize_keyboard=True)
        )
        return ADD_PLAN_UNIT
    except ValueError:
        await update.message.reply_text(
            "Введи число, например: 50\nИли напиши «нет» чтобы пропустить план:"
        )
        return ADD_PLAN_AMOUNT


async def add_get_plan_unit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ Отмена":
        return await cancel(update, context)

    user_id = str(update.effective_user.id)
    habit   = context.user_data.get('new_habit', '')
    amount  = context.user_data.get('plan_amount', 0)
    unit    = text

    sheets.set_plan(user_id, habit, amount, unit)

    await update.message.reply_text(
        f"🎯 План задан!\n\n"
        f"Задача: {habit}\n"
        f"Цель: {fmt_amount(amount)} {unit} в день\n\n"
        f"Отмечай выполнение кнопкой «✅ Сделано»",
        reply_markup=MAIN_KB
    )
    return ConversationHandler.END


# ── СДЕЛАНО — выбор задачи + ввод количества ─────────────────────────────────

async def done_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    user_id = str(update.effective_user.id)
    habits  = sheets.get_habits(user_id)
    plans   = sheets.get_all_plans(user_id)
    amounts = sheets.get_today_amounts(user_id, today_str())

    if not habits:
        await update.message.reply_text(
            "У тебя нет задач. Нажми «➕ Добавить»",
            reply_markup=MAIN_KB
        )
        return ConversationHandler.END

    # Build inline keyboard with habits
    buttons = []
    for h in habits:
        plan = plans.get(h)
        done = amounts.get(h, 0.0)
        if plan and plan["target_amount"] > 0:
            target = plan["target_amount"]
            unit   = plan["unit"]
            pct    = min(int(done / target * 100), 100)
            label  = f"{h}  {fmt_amount(done)}/{fmt_amount(target)} {unit} ({pct}%)"
        else:
            label = h
        buttons.append([InlineKeyboardButton(label, callback_data=f"done_pick:{h}")])

    await update.message.reply_text(
        "Выбери задачу:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return ConversationHandler.END


async def done_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    habit_name = query.data.split(":", 1)[1]
    user_id    = str(query.from_user.id)
    plan       = sheets.get_plan(user_id, habit_name)
    context.user_data['done_habit'] = habit_name

    if plan and plan["target_amount"] > 0:
        target = plan["target_amount"]
        unit   = plan["unit"]
        amounts = sheets.get_today_amounts(user_id, today_str())
        done_so_far = amounts.get(habit_name, 0.0)
        remaining   = max(target - done_so_far, 0)

        await query.edit_message_text(
            f"✅ {habit_name}\n\n"
            f"План: {fmt_amount(target)} {unit}\n"
            f"Уже сделано сегодня: {fmt_amount(done_so_far)} {unit}\n"
            f"Осталось: {fmt_amount(remaining)} {unit}\n\n"
            f"Сколько сделал сейчас? Введи число:"
        )
        return DONE_AMOUNT
    else:
        # No plan — just mark done
        sheets.record_checkin(user_id, habit_name, "done", today_str(), time_str(), 0)
        await query.edit_message_text(f"✅ {habit_name} — выполнено!")
        return ConversationHandler.END


async def done_get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ Отмена":
        return await cancel(update, context)

    user_id    = str(update.effective_user.id)
    habit_name = context.user_data.get('done_habit', '')

    try:
        amount = float(text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("Введи число, например: 45")
        return DONE_AMOUNT

    sheets.record_checkin(user_id, habit_name, "done", today_str(), time_str(), amount)

    plan = sheets.get_plan(user_id, habit_name)
    if plan and plan["target_amount"] > 0:
        target = plan["target_amount"]
        unit   = plan["unit"]
        amounts = sheets.get_today_amounts(user_id, today_str())
        total_done = amounts.get(habit_name, amount)
        pct  = min(int(total_done / target * 100), 100)
        bar  = progress_bar(pct)

        msg = (
            f"✅ {habit_name}\n\n"
            f"{bar} {fmt_amount(total_done)}/{fmt_amount(target)} {unit} ({pct}%)"
        )
        if pct >= 100:
            msg += "\n\n🎉 Цель достигнута!"
    else:
        msg = f"✅ {habit_name} — выполнено!"

    await update.message.reply_text(msg, reply_markup=MAIN_KB)
    return ConversationHandler.END


# ── ПЛАНЫ НА СЕГОДНЯ ─────────────────────────────────────────────────────────

async def plans_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    user_id = str(update.effective_user.id)
    habits  = sheets.get_habits(user_id)
    plans   = sheets.get_all_plans(user_id)
    amounts = sheets.get_today_amounts(user_id, today_str())
    done_today = sheets.get_done_today(user_id, today_str())
    tz     = get_tz()
    date_display = datetime.now(tz).strftime("%d.%m.%Y")

    if not habits:
        await update.message.reply_text("Нет задач. Нажми «➕ Добавить»", reply_markup=MAIN_KB)
        return

    lines = [f"📋 Планы на сегодня — {date_display}\n"]
    done_count = 0
    total = len(habits)

    for h in habits:
        plan   = plans.get(h)
        done_v = amounts.get(h, 0.0)
        is_done = h in done_today

        if plan and plan["target_amount"] > 0:
            target = plan["target_amount"]
            unit   = plan["unit"]
            pct    = min(int(done_v / target * 100), 100)
            bar    = progress_bar(pct, length=6)

            if done_v >= target:
                status = "✅"
                done_count += 1
            elif done_v > 0:
                status = "🔄"
            else:
                status = "⬜"

            lines.append(f"{status} {h}")
            lines.append(f"   {bar} {fmt_amount(done_v)}/{fmt_amount(target)} {unit} ({pct}%)")
        else:
            if is_done:
                lines.append(f"✅ {h}")
                done_count += 1
            else:
                lines.append(f"⬜ {h}")

    overall_pct = int(done_count / total * 100) if total else 0
    bar = progress_bar(overall_pct)
    lines.append(f"\n{bar} {done_count}/{total} ({overall_pct}%)")

    await update.message.reply_text("\n".join(lines), reply_markup=MAIN_KB)


# ── СПИСОК ────────────────────────────────────────────────────────────────────

async def list_habits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    user_id = str(update.effective_user.id)
    habits  = sheets.get_habits(user_id)
    plans   = sheets.get_all_plans(user_id)

    if not habits:
        await update.message.reply_text("Нет задач. Нажми «➕ Добавить»", reply_markup=MAIN_KB)
        return

    lines = ["📝 Твои задачи:\n"]
    for i, h in enumerate(habits, 1):
        plan = plans.get(h)
        if plan:
            lines.append(f"{i}. {h} — план: {fmt_amount(plan['target_amount'])} {plan['unit']}")
        else:
            lines.append(f"{i}. {h}")

    await update.message.reply_text("\n".join(lines), reply_markup=MAIN_KB)


# ── УДАЛИТЬ ───────────────────────────────────────────────────────────────────

async def delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    user_id = str(update.effective_user.id)
    habits  = sheets.get_habits(user_id)

    if not habits:
        await update.message.reply_text("Нет задач для удаления.", reply_markup=MAIN_KB)
        return ConversationHandler.END

    buttons = [[InlineKeyboardButton(h, callback_data=f"del_pick:{h}")] for h in habits]
    await update.message.reply_text(
        "Какую задачу удалить?",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return ConversationHandler.END


async def delete_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    habit_name = query.data.split(":", 1)[1]
    user_id    = str(query.from_user.id)

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Да, удалить", callback_data=f"del_confirm:{habit_name}"),
            InlineKeyboardButton("❌ Отмена",      callback_data="del_cancel"),
        ]
    ])
    await query.edit_message_text(
        f"Удалить задачу «{habit_name}»?\nПлан тоже удалится автоматически.",
        reply_markup=buttons
    )


async def delete_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "del_cancel":
        await query.edit_message_text("Отменено.")
        return

    habit_name = data.split(":", 1)[1]
    user_id    = str(query.from_user.id)

    sheets.remove_habit(user_id, habit_name)
    sheets.remove_plan(user_id, habit_name)  # auto-remove plan

    await query.edit_message_text(f"🗑 Задача «{habit_name}» и её план удалены.")


# ── СТАТИСТИКА ────────────────────────────────────────────────────────────────

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    user_id = str(update.effective_user.id)
    data    = sheets.get_stats(user_id, days=7)

    if not data:
        await update.message.reply_text("Нет данных. Начни отмечать задачи!", reply_markup=MAIN_KB)
        return

    lines = ["📊 Статистика за 7 дней:\n"]
    for habit, info in data.items():
        done_days = info["done"]
        total     = info["total"]
        pct       = int(done_days / total * 100) if total > 0 else 0
        bar       = progress_bar(pct)
        streak    = info.get("streak", 0)
        streak_str = f"  🔥{streak}" if streak >= 2 else ""
        plan       = info.get("plan")
        today_amt  = info.get("today_amount", 0.0)

        lines.append(f"{habit}{streak_str}")
        lines.append(f"{bar} {done_days}/{total} дней ({pct}%)")

        if plan and plan["target_amount"] > 0:
            target  = plan["target_amount"]
            unit    = plan["unit"]
            amt_pct = min(int(today_amt / target * 100), 100)
            amt_bar = progress_bar(amt_pct, length=6)
            lines.append(f"Сегодня: {amt_bar} {fmt_amount(today_amt)}/{fmt_amount(target)} {unit} ({amt_pct}%)")

        lines.append("")

    await update.message.reply_text("\n".join(lines), reply_markup=MAIN_KB)


# ── ДАШБОРД ───────────────────────────────────────────────────────────────────

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    uid = str(update.effective_user.id)

    if not DASHBOARD_URL:
        await update.message.reply_text("Добавь DASHBOARD_URL в переменные окружения.", reply_markup=MAIN_KB)
        return

    url = f"{DASHBOARD_URL}?uid={uid}"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📈 Открыть дашборд", url=url)]])
    await update.message.reply_text("Твой дашборд:", reply_markup=keyboard)


# ── ОТМЕНА ────────────────────────────────────────────────────────────────────

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Отменено.", reply_markup=MAIN_KB)
    return ConversationHandler.END


# ── Авто-пропуск ─────────────────────────────────────────────────────────────

async def auto_skip_job(context: ContextTypes.DEFAULT_TYPE):
    """В 23:55 записывает пропуск для невыполненных привычек"""
    users = sheets.get_all_users()
    tz    = get_tz()
    date  = datetime.now(tz).strftime("%Y-%m-%d")
    t     = datetime.now(tz).strftime("%H:%M")

    for user_id, name in users:
        habits     = sheets.get_habits(user_id)
        done_today = sheets.get_done_today(user_id, date)
        amounts    = sheets.get_today_amounts(user_id, date)

        for h in habits:
            if h in done_today:
                continue
            # Check if partially done (has amount but not marked done)
            if amounts.get(h, 0) > 0:
                continue
            # Mark as skipped
            sheets.record_checkin(user_id, h, "skip", date, t, 0)
            logger.info(f"Auto-skip: {user_id} / {h}")


# ── Напоминание ───────────────────────────────────────────────────────────────

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    users = sheets.get_all_users()
    tz    = get_tz()
    date  = datetime.now(tz).strftime("%Y-%m-%d")
    plans_all = {}

    for user_id, name in users:
        habits     = sheets.get_habits(user_id)
        if not habits: continue
        done_today = sheets.get_done_today(user_id, date)
        amounts    = sheets.get_today_amounts(user_id, date)
        plans      = sheets.get_all_plans(user_id)
        pending    = [h for h in habits if h not in done_today]
        if not pending: continue

        lines = [f"⏰ {name}, не забудь!\n"]
        for h in pending:
            plan = plans.get(h)
            if plan and plan["target_amount"] > 0:
                target = plan["target_amount"]
                unit   = plan["unit"]
                done_v = amounts.get(h, 0.0)
                pct    = min(int(done_v / target * 100), 100)
                lines.append(f"⬜ {h}: {fmt_amount(done_v)}/{fmt_amount(target)} {unit} ({pct}%)")
            else:
                lines.append(f"⬜ {h}")

        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="\n".join(lines),
                reply_markup=MAIN_KB
            )
        except Exception as e:
            logger.warning(f"Reminder error {user_id}: {e}")


# ── Main text handler ─────────────────────────────────────────────────────────

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles keyboard button presses outside of conversations"""
    text = update.message.text

    if text == "✅ Сделано":
        return await done_start(update, context)
    elif text == "📋 Планы на сегодня":
        return await plans_today(update, context)
    elif text == "➕ Добавить":
        return await add_start(update, context)
    elif text == "📝 Список":
        return await list_habits(update, context)
    elif text == "🗑 Удалить":
        return await delete_start(update, context)
    elif text == "📊 Статистика":
        return await stats(update, context)
    elif text == "📈 Дашборд":
        return await report(update, context)


# ── Launch ────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Add habit conversation
    add_conv = ConversationHandler(
        entry_points=[
            CommandHandler("add", add_start),
            MessageHandler(filters.Regex("^➕ Добавить$"), add_start),
        ],
        states={
            ADD_NAME:         [MessageHandler(filters.TEXT & ~filters.COMMAND, add_get_name)],
            ADD_PLAN_AMOUNT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, add_get_plan_amount)],
            ADD_PLAN_UNIT:    [MessageHandler(filters.TEXT & ~filters.COMMAND, add_get_plan_unit)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.Regex("^❌ Отмена$"), cancel),
        ],
        allow_reentry=True,
    )

    # Done conversation
    done_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^✅ Сделано$"), done_start),
            CommandHandler("done", done_start),
        ],
        states={
            DONE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, done_get_amount)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.Regex("^❌ Отмена$"), cancel),
        ],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("help",   start))
    app.add_handler(add_conv)
    app.add_handler(done_conv)

    # Inline callbacks
    app.add_handler(CallbackQueryHandler(done_pick_callback,    pattern="^done_pick:"))
    app.add_handler(CallbackQueryHandler(delete_pick_callback,  pattern="^del_pick:"))
    app.add_handler(CallbackQueryHandler(delete_confirm_callback, pattern="^del_"))

    # Other commands
    app.add_handler(CommandHandler("list",    list_habits))
    app.add_handler(CommandHandler("stats",   stats))
    app.add_handler(CommandHandler("report",  report))
    app.add_handler(CommandHandler("today",   plans_today))

    # Text buttons
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & ~filters.Regex("^(➕ Добавить|✅ Сделано)$"),
        handle_text
    ))

    # Jobs
    tz = get_tz()
    jq = app.job_queue
    jq.run_daily(send_reminder,  time=time(21, 0, tzinfo=tz))
    jq.run_daily(auto_skip_job,  time=time(23, 55, tzinfo=tz))

    logger.info("Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
