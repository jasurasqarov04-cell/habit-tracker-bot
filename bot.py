"""
Habit Tracker Telegram Bot
Управление привычками + планы по количеству
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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Tashkent")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "")

sheets = SheetsHelper()


async def check_access(update: Update) -> bool:
    if not ALLOWED_USER_ID:
        return True
    if str(update.effective_user.id) != str(ALLOWED_USER_ID):
        await update.message.reply_text("Этот бот приватный.")
        return False
    return True


# ─── /start ───────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    user = update.effective_user
    sheets.register_user(str(user.id), user.first_name)

    text = (
        f"Привет, {user.first_name}!\n\n"
        "Команды:\n\n"
        "ПРИВЫЧКИ\n"
        "/add название — добавить привычку\n"
        "/list — список привычек\n"
        "/remove название — удалить\n\n"
        "ВЫПОЛНЕНИЕ\n"
        "/done название [количество] — отметить выполненным\n"
        "/skip название — пропустить\n\n"
        "ПЛАНЫ\n"
        "/plan название количество единица — задать цель\n"
        "/plans — все планы\n"
        "/removeplan название — удалить план\n\n"
        "СТАТИСТИКА\n"
        "/today — задачи на сегодня с прогрессом\n"
        "/stats — статистика за 7 дней\n"
        "/compare — эта неделя vs прошлая\n"
        "/report — дашборд\n\n"
        "Примеры:\n"
        "/add Отжимания\n"
        "/plan Отжимания 50 раз\n"
        "/done Отжимания 45"
    )
    await update.message.reply_text(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


# ─── Привычки ─────────────────────────────────────────────────────────────────

async def add_habit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    user_id = str(update.effective_user.id)

    if not context.args:
        await update.message.reply_text(
            "Укажи название:\n/add Отжимания"
        )
        return

    habit_name = " ".join(context.args).strip()
    result = sheets.add_habit(user_id, habit_name)

    if result == "exists":
        await update.message.reply_text(f"Привычка «{habit_name}» уже есть.")
    else:
        await update.message.reply_text(
            f"Привычка «{habit_name}» добавлена!\n\n"
            f"Задай план (необязательно):\n/plan {habit_name} 50 раз"
        )


async def list_habits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    user_id = str(update.effective_user.id)
    habits = sheets.get_habits(user_id)
    plans  = sheets.get_all_plans(user_id)

    if not habits:
        await update.message.reply_text("Нет привычек. Добавь: /add Название")
        return

    lines = ["Твои привычки:\n"]
    for i, h in enumerate(habits, 1):
        plan = plans.get(h)
        if plan:
            lines.append(f"{i}. {h}  —  план: {_fmt_amount(plan['target_amount'])} {plan['unit']}")
        else:
            lines.append(f"{i}. {h}")

    lines.append("\n/done название — отметить выполненным")
    await update.message.reply_text("\n".join(lines))


async def remove_habit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    user_id = str(update.effective_user.id)

    if not context.args:
        habits = sheets.get_habits(user_id)
        if not habits:
            await update.message.reply_text("Нет привычек для удаления.")
            return
        keyboard = _build_habit_keyboard(habits, action="remove")
        await update.message.reply_text("Какую привычку удалить?", reply_markup=keyboard)
        return

    habit_name = " ".join(context.args).strip()
    result = sheets.remove_habit(user_id, habit_name)
    if result:
        await update.message.reply_text(f"Привычка «{habit_name}» удалена.")
    else:
        await update.message.reply_text(f"Привычка «{habit_name}» не найдена.")


# ─── Планы ────────────────────────────────────────────────────────────────────

async def set_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /plan Отжимания 50 раз
    /plan Прочитать 30 страниц
    /plan Бег 5 км
    /plan Вода 8 стаканов
    """
    if not await check_access(update): return
    user_id = str(update.effective_user.id)

    if len(context.args) < 3:
        await update.message.reply_text(
            "Формат: /plan название количество единица\n\n"
            "Примеры:\n"
            "/plan Отжимания 50 раз\n"
            "/plan Бег 5 км\n"
            "/plan Чтение 30 страниц\n"
            "/plan Вода 8 стаканов"
        )
        return

    # Парсим: последнее слово = единица, предпоследнее = число, остальное = название
    args = context.args
    unit = args[-1]
    try:
        target = float(args[-2])
    except ValueError:
        await update.message.reply_text(
            "Количество должно быть числом.\n"
            "Пример: /plan Отжимания 50 раз"
        )
        return

    habit_name = " ".join(args[:-2]).strip()
    if not habit_name:
        await update.message.reply_text("Укажи название привычки.")
        return

    # Проверяем что привычка существует
    habits = sheets.get_habits(user_id)
    if habit_name not in habits:
        await update.message.reply_text(
            f"Привычка «{habit_name}» не найдена.\n"
            f"Сначала добавь: /add {habit_name}"
        )
        return

    result = sheets.set_plan(user_id, habit_name, target, unit)
    verb = "обновлён" if result == "updated" else "задан"

    await update.message.reply_text(
        f"План {verb}!\n\n"
        f"Привычка: {habit_name}\n"
        f"Цель: {_fmt_amount(target)} {unit} в день\n\n"
        f"Отмечай выполнение:\n"
        f"/done {habit_name} {int(target)}"
    )


async def list_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    user_id = str(update.effective_user.id)
    plans = sheets.get_all_plans(user_id)

    if not plans:
        await update.message.reply_text(
            "Планов нет.\n\n"
            "Задай план:\n/plan Отжимания 50 раз"
        )
        return

    tz = pytz.timezone(TIMEZONE)
    today_str = datetime.now(tz).strftime("%Y-%m-%d")
    today_amounts = sheets.get_today_amounts(user_id, today_str)

    lines = ["Твои планы на сегодня:\n"]
    for habit_name, plan in plans.items():
        target = plan["target_amount"]
        unit   = plan["unit"]
        done   = today_amounts.get(habit_name, 0.0)
        pct    = min(int(done / target * 100), 100) if target > 0 else 0
        bar    = _progress_bar(pct)

        lines.append(
            f"{habit_name}\n"
            f"{bar} {_fmt_amount(done)}/{_fmt_amount(target)} {unit} ({pct}%)\n"
        )

    await update.message.reply_text("\n".join(lines))


async def remove_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    user_id = str(update.effective_user.id)

    if not context.args:
        await update.message.reply_text("Укажи название:\n/removeplan Отжимания")
        return

    habit_name = " ".join(context.args).strip()
    result = sheets.remove_plan(user_id, habit_name)
    if result:
        await update.message.reply_text(f"План для «{habit_name}» удалён.")
    else:
        await update.message.reply_text(f"План для «{habit_name}» не найден.")


# ─── Выполнение ───────────────────────────────────────────────────────────────

async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /done — кнопки
    /done Отжимания — выполнено (без количества)
    /done Отжимания 45 — выполнено 45 (с количеством)
    """
    if not await check_access(update): return
    user_id = str(update.effective_user.id)

    if not context.args:
        habits = sheets.get_habits(user_id)
        if not habits:
            await update.message.reply_text("Нет привычек. Добавь: /add Название")
            return
        keyboard = _build_habit_keyboard(habits, action="done")
        await update.message.reply_text("Какую привычку отметить выполненной?", reply_markup=keyboard)
        return

    # Парсим аргументы: последний может быть числом (количество)
    args = context.args
    amount = 0.0
    if len(args) >= 2:
        try:
            amount = float(args[-1])
            habit_name = " ".join(args[:-1]).strip()
        except ValueError:
            habit_name = " ".join(args).strip()
    else:
        habit_name = " ".join(args).strip()

    await _do_checkin(update, user_id, habit_name, "done", amount)


async def skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    user_id = str(update.effective_user.id)

    if not context.args:
        habits = sheets.get_habits(user_id)
        if not habits:
            await update.message.reply_text("Нет привычек. Добавь: /add Название")
            return
        keyboard = _build_habit_keyboard(habits, action="skip")
        await update.message.reply_text("Какую привычку пропустить?", reply_markup=keyboard)
        return

    habit_name = " ".join(context.args).strip()
    await _do_checkin(update, user_id, habit_name, "skip", 0)


async def _do_checkin(update, user_id, habit_name, status, amount):
    """Записывает чекин и отвечает с прогрессом"""
    tz = pytz.timezone(TIMEZONE)
    date_str = datetime.now(tz).strftime("%Y-%m-%d")
    time_str = datetime.now(tz).strftime("%H:%M")

    sheets.record_checkin(user_id, habit_name, status, date_str, time_str, amount)

    plan = sheets.get_plan(user_id, habit_name)

    if status == "done":
        if plan and amount > 0:
            target = plan["target_amount"]
            unit   = plan["unit"]
            # Берём актуальное суммарное количество за день
            today_amounts = sheets.get_today_amounts(user_id, date_str)
            total_done = today_amounts.get(habit_name, amount)
            pct  = min(int(total_done / target * 100), 100) if target > 0 else 100
            bar  = _progress_bar(pct)

            text = (
                f"Выполнено: {habit_name}\n\n"
                f"{bar} {_fmt_amount(total_done)}/{_fmt_amount(target)} {unit} ({pct}%)"
            )
            if pct >= 100:
                text += "\n\nЦель достигнута!"
        elif plan:
            # Привычка с планом, но без количества — спрашиваем
            text = (
                f"Выполнено: {habit_name}\n\n"
                f"У этой привычки есть план: {_fmt_amount(plan['target_amount'])} {plan['unit']}\n"
                f"Укажи количество:\n/done {habit_name} {int(plan['target_amount'])}"
            )
        else:
            text = f"Выполнено: {habit_name}"
    else:
        text = f"Пропущено: {habit_name}"

    await update.message.reply_text(text)


# ─── /today ───────────────────────────────────────────────────────────────────

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    user_id = str(update.effective_user.id)
    tz = pytz.timezone(TIMEZONE)
    today_str = datetime.now(tz).strftime("%Y-%m-%d")
    today_display = datetime.now(tz).strftime("%d.%m.%Y")

    habits = sheets.get_habits(user_id)
    if not habits:
        await update.message.reply_text("Добавь привычки: /add Название")
        return

    done_today    = sheets.get_done_today(user_id, today_str)
    today_amounts = sheets.get_today_amounts(user_id, today_str)
    plans         = sheets.get_all_plans(user_id)

    lines = [f"Сегодня — {today_display}\n"]
    done_count = 0

    for h in habits:
        is_done = h in done_today
        plan    = plans.get(h)

        if plan:
            target = plan["target_amount"]
            unit   = plan["unit"]
            done_v = today_amounts.get(h, 0.0)
            pct    = min(int(done_v / target * 100), 100) if target > 0 else (100 if is_done else 0)
            bar    = _progress_bar(pct, length=6)

            if is_done and done_v >= target:
                status_icon = "✅"
                done_count += 1
            elif is_done or done_v > 0:
                status_icon = "🔄"
            else:
                status_icon = "⬜"

            lines.append(
                f"{status_icon} {h}\n"
                f"   {bar} {_fmt_amount(done_v)}/{_fmt_amount(target)} {unit} ({pct}%)"
            )
        else:
            if is_done:
                lines.append(f"✅ {h}")
                done_count += 1
            else:
                lines.append(f"⬜ {h}")

    # Итого
    total = len(habits)
    overall_pct = int(done_count / total * 100)
    bar = _progress_bar(overall_pct)
    lines.append(f"\n{bar} {done_count}/{total} ({overall_pct}%)")

    await update.message.reply_text("\n".join(lines))


# ─── /stats ───────────────────────────────────────────────────────────────────

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    user_id = str(update.effective_user.id)
    data = sheets.get_stats(user_id, days=7)

    if not data:
        await update.message.reply_text("Нет данных. Начни отмечать привычки!")
        return

    lines = ["Статистика за 7 дней:\n"]
    for habit, info in data.items():
        done_days = info["done"]
        total     = info["total"]
        pct       = int(done_days / total * 100) if total > 0 else 0
        bar       = _progress_bar(pct)
        streak    = info.get("streak", 0)
        streak_str = f"  🔥{streak}" if streak >= 2 else ""

        plan       = info.get("plan")
        today_amt  = info.get("today_amount", 0.0)

        lines.append(f"{habit}{streak_str}")
        lines.append(f"{bar} {done_days}/{total} дней ({pct}%)")

        # Если есть план — показываем количество за сегодня
        if plan and plan["target_amount"] > 0:
            target = plan["target_amount"]
            unit   = plan["unit"]
            amt_pct = min(int(today_amt / target * 100), 100)
            amt_bar = _progress_bar(amt_pct, length=6)
            lines.append(
                f"Сегодня: {amt_bar} {_fmt_amount(today_amt)}/{_fmt_amount(target)} {unit} ({amt_pct}%)"
            )

        lines.append("")

    await update.message.reply_text("\n".join(lines))


# ─── /compare ─────────────────────────────────────────────────────────────────

async def compare(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    user_id = str(update.effective_user.id)
    data = sheets.get_weekly_comparison(user_id)

    if not data:
        await update.message.reply_text("Нет данных для сравнения.")
        return

    lines = ["Эта неделя vs прошлая:\n"]
    total_this = total_last = total_possible = 0

    for habit, info in data.items():
        this  = info["this_week"]
        last  = info["last_week"]
        total = info["total"]
        total_this     += this
        total_last     += last
        total_possible += total

        this_pct = int(this / total * 100)
        last_pct = int(last / total * 100)
        diff     = this_pct - last_pct
        trend    = f"↑ +{diff}%" if diff > 0 else (f"↓ {diff}%" if diff < 0 else "→ без изменений")

        lines.append(f"{habit}")
        lines.append(f"Эта:     {_progress_bar(this_pct)} {this}/{total} ({this_pct}%)")
        lines.append(f"Прошлая: {_progress_bar(last_pct)} {last}/{total} ({last_pct}%)")
        lines.append(f"{trend}\n")

    total_this_pct = int(total_this / total_possible * 100) if total_possible else 0
    total_last_pct = int(total_last / total_possible * 100) if total_possible else 0
    total_diff     = total_this_pct - total_last_pct
    total_trend    = f"↑ Лучше на {total_diff}%" if total_diff > 0 else (
                     f"↓ Хуже на {abs(total_diff)}%" if total_diff < 0 else "→ Без изменений")

    lines.append("─────────────")
    lines.append(f"Итого:")
    lines.append(f"Эта:     {_progress_bar(total_this_pct)} {total_this_pct}%")
    lines.append(f"Прошлая: {_progress_bar(total_last_pct)} {total_last_pct}%")
    lines.append(total_trend)

    await update.message.reply_text("\n".join(lines))


# ─── /report ──────────────────────────────────────────────────────────────────

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    uid = str(update.effective_user.id)

    if not DASHBOARD_URL:
        await update.message.reply_text(
            "Добавь в .env:\n"
            "DASHBOARD_URL=https://твой-сайт.github.io/..."
        )
        return

    url = f"{DASHBOARD_URL}?uid={uid}"
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Открыть дашборд", url=url)
    ]])
    await update.message.reply_text("Твой дашборд:", reply_markup=keyboard)


# ─── Callback кнопки ──────────────────────────────────────────────────────────

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data  = query.data
    parts = data.split(":", 1)
    if len(parts) != 2:
        return

    action, habit_name = parts
    user_id = str(query.from_user.id)

    if action in ("done", "skip"):
        tz       = pytz.timezone(TIMEZONE)
        date_str = datetime.now(tz).strftime("%Y-%m-%d")
        time_str = datetime.now(tz).strftime("%H:%M")
        sheets.record_checkin(user_id, habit_name, action, date_str, time_str, 0)

        plan = sheets.get_plan(user_id, habit_name)

        if action == "done":
            if plan:
                target = plan["target_amount"]
                unit   = plan["unit"]
                text   = (
                    f"Выполнено: {habit_name}\n\n"
                    f"У этой привычки план: {_fmt_amount(target)} {unit}\n"
                    f"Введи количество:\n/done {habit_name} {int(target)}"
                )
            else:
                text = f"Выполнено: {habit_name}"
        else:
            text = f"Пропущено: {habit_name}"

        await query.edit_message_text(text)

    elif action == "remove":
        sheets.remove_habit(user_id, habit_name)
        await query.edit_message_text(f"Привычка «{habit_name}» удалена.")


# ─── Напоминания ──────────────────────────────────────────────────────────────

async def send_daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    users = sheets.get_all_users()
    tz    = pytz.timezone(TIMEZONE)
    today_str = datetime.now(tz).strftime("%Y-%m-%d")

    for user_id, name in users:
        habits = sheets.get_habits(user_id)
        if not habits:
            continue

        done_today    = sheets.get_done_today(user_id, today_str)
        today_amounts = sheets.get_today_amounts(user_id, today_str)
        plans         = sheets.get_all_plans(user_id)
        pending       = [h for h in habits if h not in done_today]

        if not pending:
            text = f"{name}, все привычки выполнены! Отлично!"
        else:
            lines = [f"{name}, не забудь привычки!\n"]
            for h in pending:
                plan = plans.get(h)
                if plan:
                    target  = plan["target_amount"]
                    unit    = plan["unit"]
                    done_v  = today_amounts.get(h, 0.0)
                    pct     = min(int(done_v / target * 100), 100) if target > 0 else 0
                    lines.append(f"⬜ {h}: {_fmt_amount(done_v)}/{_fmt_amount(target)} {unit} ({pct}%)")
                else:
                    lines.append(f"⬜ {h}")
            lines.append("\n/done для отметки")
            text = "\n".join(lines)

        try:
            await context.bot.send_message(chat_id=user_id, text=text)
        except Exception as e:
            logger.warning(f"Не удалось отправить напоминание {user_id}: {e}")


async def send_weekly_report(context: ContextTypes.DEFAULT_TYPE):
    users = sheets.get_all_users()
    for user_id, name in users:
        data = sheets.get_stats(user_id, days=7)
        if not data:
            continue

        total_done     = sum(v["done"] for v in data.values())
        total_possible = sum(v["total"] for v in data.values())
        overall_pct    = int(total_done / total_possible * 100) if total_possible > 0 else 0
        best_habit     = max(data, key=lambda h: data[h]["done"] / max(data[h]["total"], 1), default=None)
        streak_champ   = max(data, key=lambda h: data[h].get("streak", 0), default=None)
        top_streak     = data[streak_champ]["streak"] if streak_champ else 0

        text = (
            f"Итоги недели, {name}!\n\n"
            f"Общий прогресс: {_progress_bar(overall_pct)} {overall_pct}%\n"
            f"Выполнено: {total_done} из {total_possible}\n\n"
        )
        if best_habit:
            text += f"Лучшая привычка: {best_habit}\n"
        if top_streak >= 3:
            text += f"Серия: {top_streak} дней — {streak_champ}\n"
        text += "\n/report — открыть дашборд"

        try:
            await context.bot.send_message(chat_id=user_id, text=text)
        except Exception as e:
            logger.warning(f"Не удалось отправить отчёт {user_id}: {e}")


# ─── Утилиты ──────────────────────────────────────────────────────────────────

def _fmt_amount(v: float) -> str:
    """50.0 → '50', 5.5 → '5.5'"""
    return str(int(v)) if v == int(v) else str(v)


def _build_habit_keyboard(habits: list, action: str) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(h, callback_data=f"{action}:{h}")] for h in habits]
    return InlineKeyboardMarkup(buttons)


def _progress_bar(pct: int, length: int = 10) -> str:
    filled = int(pct / 100 * length)
    empty  = length - filled
    if pct >= 70:
        block = "🟩"
    elif pct >= 40:
        block = "🟨"
    else:
        block = "🟥"
    return block * filled + "⬜" * empty


# ─── Запуск ───────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",      start))
    app.add_handler(CommandHandler("help",       help_command))
    app.add_handler(CommandHandler("add",        add_habit))
    app.add_handler(CommandHandler("done",       done))
    app.add_handler(CommandHandler("skip",       skip))
    app.add_handler(CommandHandler("list",       list_habits))
    app.add_handler(CommandHandler("remove",     remove_habit))
    app.add_handler(CommandHandler("today",      today))
    app.add_handler(CommandHandler("stats",      stats))
    app.add_handler(CommandHandler("compare",    compare))
    app.add_handler(CommandHandler("report",     report))
    app.add_handler(CommandHandler("plan",       set_plan))
    app.add_handler(CommandHandler("plans",      list_plans))
    app.add_handler(CommandHandler("removeplan", remove_plan))
    app.add_handler(CallbackQueryHandler(button_callback))

    tz        = pytz.timezone(TIMEZONE)
    job_queue = app.job_queue
    job_queue.run_daily(send_daily_reminder, time=time(21, 0, tzinfo=tz))
    job_queue.run_daily(send_weekly_report,  time=time(20, 0, tzinfo=tz), days=(6,))

    logger.info("Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
