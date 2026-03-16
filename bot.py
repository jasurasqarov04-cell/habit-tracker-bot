"""
Habit Tracker Telegram Bot
Управление привычками прямо из Telegram
"""

import os
import logging
from datetime import datetime, time
import pytz
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

from sheets_helper import SheetsHelper

load_dotenv()

ALLOWED_USER_ID = os.getenv("ALLOWED_USER_ID")


async def check_access(update: Update) -> bool:
    """Проверяет что пользователь — владелец бота"""
    if not ALLOWED_USER_ID:
        return True  # если не задан — открытый доступ
    if str(update.effective_user.id) != str(ALLOWED_USER_ID):
        await update.message.reply_text("⛔ Этот бот приватный.")
        return False
    return True


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Tashkent")

sheets = SheetsHelper()

# ─── Команды ───────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    user = update.effective_user
    name = user.first_name

    # Регистрируем пользователя в таблице
    sheets.register_user(str(user.id), name)

    text = (
        f"👋 Привет, {name}!\n\n"
        "Я твой личный трекер привычек. Вот что я умею:\n\n"
        "✅ /done `название` — отметить привычку выполненной\n"
        "❌ /skip `название` — отметить пропуск\n"
        "📊 /stats — статистика за последние 7 дней\n"
        "📅 /today — что нужно сделать сегодня\n"
        "➕ /add `название` — добавить новую привычку\n"
        "📋 /list — список всех привычек\n"
        "🗑 /remove `название` — удалить привычку\n"
        "📈 /report — ссылка на дашборд\n"
        "❓ /help — помощь\n\n"
        "Начни с добавления привычки:\n"
        "`/add Утренняя зарядка`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def add_habit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    user_id = str(update.effective_user.id)

    if not context.args:
        await update.message.reply_text(
            "⚠️ Укажи название привычки:\n`/add Утренняя зарядка`",
            parse_mode="Markdown"
        )
        return

    habit_name = " ".join(context.args).strip()
    result = sheets.add_habit(user_id, habit_name)

    if result == "exists":
        await update.message.reply_text(f"📌 Привычка *{habit_name}* уже есть в списке.", parse_mode="Markdown")
    else:
        await update.message.reply_text(
            f"✅ Привычка *{habit_name}* добавлена!\n\nОтмечай каждый день:\n`/done {habit_name}`",
            parse_mode="Markdown"
        )


async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    user_id = str(update.effective_user.id)

    if not context.args:
        # Показываем кнопки с привычками
        habits = sheets.get_habits(user_id)
        if not habits:
            await update.message.reply_text("У тебя пока нет привычек. Добавь: `/add Название`", parse_mode="Markdown")
            return
        keyboard = _build_habit_keyboard(habits, action="done")
        await update.message.reply_text("✅ Какую привычку отметить выполненной?", reply_markup=keyboard)
        return

    habit_name = " ".join(context.args).strip()
    _record_checkin(user_id, habit_name, "done", update)


async def skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    user_id = str(update.effective_user.id)

    if not context.args:
        habits = sheets.get_habits(user_id)
        if not habits:
            await update.message.reply_text("У тебя пока нет привычек. Добавь: `/add Название`", parse_mode="Markdown")
            return
        keyboard = _build_habit_keyboard(habits, action="skip")
        await update.message.reply_text("❌ Какую привычку пропустить?", reply_markup=keyboard)
        return

    habit_name = " ".join(context.args).strip()
    _record_checkin(user_id, habit_name, "skip", update)


async def list_habits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    user_id = str(update.effective_user.id)
    habits = sheets.get_habits(user_id)

    if not habits:
        await update.message.reply_text(
            "📋 У тебя пока нет привычек.\nДобавь первую: `/add Утренняя зарядка`",
            parse_mode="Markdown"
        )
        return

    lines = ["📋 *Твои привычки:*\n"]
    for i, h in enumerate(habits, 1):
        lines.append(f"{i}. {h}")
    lines.append("\n✅ `/done название` — отметить выполненной")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def remove_habit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    user_id = str(update.effective_user.id)

    if not context.args:
        habits = sheets.get_habits(user_id)
        if not habits:
            await update.message.reply_text("У тебя нет привычек для удаления.")
            return
        keyboard = _build_habit_keyboard(habits, action="remove")
        await update.message.reply_text("🗑 Какую привычку удалить?", reply_markup=keyboard)
        return

    habit_name = " ".join(context.args).strip()
    result = sheets.remove_habit(user_id, habit_name)
    if result:
        await update.message.reply_text(f"🗑 Привычка *{habit_name}* удалена.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❓ Привычка *{habit_name}* не найдена.", parse_mode="Markdown")


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    user_id = str(update.effective_user.id)
    tz = pytz.timezone(TIMEZONE)
    today_date = datetime.now(tz).strftime("%Y-%m-%d")

    habits = sheets.get_habits(user_id)
    if not habits:
        await update.message.reply_text("📋 Добавь привычки: `/add Название`", parse_mode="Markdown")
        return

    done_today = sheets.get_done_today(user_id, today_date)

    lines = [f"📅 *Сегодня — {datetime.now(tz).strftime('%d.%m.%Y')}*\n"]
    done_count = 0
    for h in habits:
        if h in done_today:
            lines.append(f"✅ ~{h}~")
            done_count += 1
        else:
            lines.append(f"⬜ {h}")

    pct = int(done_count / len(habits) * 100)
    bar = _progress_bar(pct)
    lines.append(f"\n{bar} {done_count}/{len(habits)} ({pct}%)")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    user_id = str(update.effective_user.id)
    data = sheets.get_stats(user_id, days=7)

    if not data:
        await update.message.reply_text("📊 Пока нет данных. Начни отмечать привычки!")
        return

    lines = ["📊 *Статистика за 7 дней:*\n"]
    for habit, info in data.items():
        done_days = info["done"]
        total = info["total"]
        pct = int(done_days / total * 100) if total > 0 else 0
        bar = _progress_bar(pct)
        streak = info.get("streak", 0)
        streak_str = f" 🔥{streak}" if streak >= 2 else ""
        lines.append(f"*{habit}*{streak_str}")
        lines.append(f"{bar} {done_days}/{total} дней ({pct}%)\n")

    lines.append("📈 Полный дашборд: /report")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    dashboard_url = os.getenv("LOOKER_STUDIO_URL", "")

    if not dashboard_url:
        await update.message.reply_text(
            "📈 *Как настроить дашборд:*\n\n"
            "1. Открой [Looker Studio](https://lookerstudio.google.com)\n"
            "2. Создай источник данных → Google Sheets\n"
            "3. Выбери таблицу *HabitTracker*\n"
            "4. Построй графики и скопируй ссылку\n"
            "5. Добавь в `.env`: `LOOKER_STUDIO_URL=ссылка`",
            parse_mode="Markdown", disable_web_page_preview=True
        )
        return

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("📊 Открыть дашборд", url=dashboard_url)
    ]])
    await update.message.reply_text("📈 Твой дашборд готов:", reply_markup=keyboard)


# ─── Callback кнопки ───────────────────────────────────────────────────────

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data  # format: "action:habit_name"
    parts = data.split(":", 1)
    if len(parts) != 2:
        return

    action, habit_name = parts
    user_id = str(query.from_user.id)

    if action in ("done", "skip"):
        tz = pytz.timezone(TIMEZONE)
        date_str = datetime.now(tz).strftime("%Y-%m-%d")
        time_str = datetime.now(tz).strftime("%H:%M")
        sheets.record_checkin(user_id, habit_name, action, date_str, time_str)

        emoji = "✅" if action == "done" else "❌"
        word = "выполнена" if action == "done" else "пропущена"
        await query.edit_message_text(f"{emoji} *{habit_name}* — {word}!", parse_mode="Markdown")

    elif action == "remove":
        sheets.remove_habit(user_id, habit_name)
        await query.edit_message_text(f"🗑 *{habit_name}* удалена.", parse_mode="Markdown")


# ─── Напоминания (job queue) ───────────────────────────────────────────────

async def send_daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Отправляет напоминание всем пользователям в 21:00"""
    users = sheets.get_all_users()
    tz = pytz.timezone(TIMEZONE)
    today_date = datetime.now(tz).strftime("%Y-%m-%d")

    for user_id, name in users:
        habits = sheets.get_habits(user_id)
        if not habits:
            continue

        done_today = sheets.get_done_today(user_id, today_date)
        pending = [h for h in habits if h not in done_today]

        if not pending:
            text = f"🎉 {name}, все привычки на сегодня выполнены! Отличная работа!"
        else:
            habit_list = "\n".join(f"⬜ {h}" for h in pending)
            text = (
                f"⏰ {name}, не забудь отметить привычки!\n\n"
                f"{habit_list}\n\n"
                "Используй /done для отметки"
            )
        try:
            await context.bot.send_message(chat_id=user_id, text=text)
        except Exception as e:
            logger.warning(f"Не удалось отправить напоминание {user_id}: {e}")


async def send_weekly_report(context: ContextTypes.DEFAULT_TYPE):
    """Отправляет недельную сводку каждое воскресенье в 20:00"""
    users = sheets.get_all_users()

    for user_id, name in users:
        data = sheets.get_stats(user_id, days=7)
        if not data:
            continue

        total_done = sum(v["done"] for v in data.values())
        total_possible = sum(v["total"] for v in data.values())
        overall_pct = int(total_done / total_possible * 100) if total_possible > 0 else 0

        best_habit = max(data, key=lambda h: data[h]["done"] / max(data[h]["total"], 1), default=None)
        streak_champion = max(data, key=lambda h: data[h].get("streak", 0), default=None)
        top_streak = data[streak_champion]["streak"] if streak_champion else 0

        text = (
            f"📊 *Итоги недели, {name}!*\n\n"
            f"Общий прогресс: {_progress_bar(overall_pct)} {overall_pct}%\n"
            f"Выполнено: {total_done} из {total_possible} возможных\n\n"
        )
        if best_habit:
            text += f"🏆 Лучшая привычка: *{best_habit}*\n"
        if top_streak >= 3:
            text += f"🔥 Серия дней: *{top_streak}* дней подряд — *{streak_champion}*\n"

        text += "\n📈 Детальный отчёт: /report"

        try:
            await context.bot.send_message(chat_id=user_id, text=text, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Не удалось отправить недельный отчёт {user_id}: {e}")


# ─── Утилиты ──────────────────────────────────────────────────────────────

def _record_checkin(user_id, habit_name, status, update):
    """Записывает чекин и отвечает пользователю"""
    tz = pytz.timezone(TIMEZONE)
    date_str = datetime.now(tz).strftime("%Y-%m-%d")
    time_str = datetime.now(tz).strftime("%H:%M")
    sheets.record_checkin(user_id, habit_name, status, date_str, time_str)
    emoji = "✅" if status == "done" else "❌"
    word = "выполнена" if status == "done" else "пропущена"

    import asyncio
    return update.message.reply_text(
        f"{emoji} *{habit_name}* — {word}!\n\n/stats чтобы посмотреть прогресс",
        parse_mode="Markdown"
    )


def _build_habit_keyboard(habits: list, action: str) -> InlineKeyboardMarkup:
    """Строит inline-клавиатуру из списка привычек"""
    buttons = [[InlineKeyboardButton(h, callback_data=f"{action}:{h}")] for h in habits]
    return InlineKeyboardMarkup(buttons)


def _progress_bar(pct: int, length: int = 10) -> str:
    filled = int(pct / 100 * length)
    return "█" * filled + "░" * (length - filled)


# ─── Запуск ───────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("add", add_habit))
    app.add_handler(CommandHandler("done", done))
    app.add_handler(CommandHandler("skip", skip))
    app.add_handler(CommandHandler("list", list_habits))
    app.add_handler(CommandHandler("remove", remove_habit))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CallbackQueryHandler(button_callback))

    # Напоминания
    tz = pytz.timezone(TIMEZONE)
    job_queue = app.job_queue
    job_queue.run_daily(send_daily_reminder, time=time(21, 0, tzinfo=tz))
    job_queue.run_daily(send_weekly_report, time=time(20, 0, tzinfo=tz), days=(6,))  # воскресенье

    logger.info("✅ Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
