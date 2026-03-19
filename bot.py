"""
Habit Tracker Bot — категории, кнопки, пошаговое добавление
"""
import os, logging
from datetime import datetime, time
import pytz
from dotenv import load_dotenv

from telegram import (Update, ReplyKeyboardMarkup, KeyboardButton,
                       InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo)
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler,
                           MessageHandler, ConversationHandler, filters, ContextTypes)
from sheets_helper import SheetsHelper

load_dotenv()
logging.basicConfig(format="%(asctime)s %(name)s %(levelname)s %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN        = os.getenv("TELEGRAM_TOKEN")
ALLOWED_UID  = os.getenv("ALLOWED_USER_ID")
TZ           = os.getenv("TIMEZONE", "Asia/Tashkent")
DASHBOARD    = os.getenv("DASHBOARD_URL", "")

sheets = SheetsHelper()

# ── Conversation states ───────────────────────────────────────────────────────
(ADD_NAME, ADD_CAT, ADD_CAT_NEW, ADD_PLAN_AMT, ADD_PLAN_UNIT) = range(5)
DONE_AMT = 10
CAT_MENU, CAT_NAME, CAT_TARGET = 20, 21, 22

# ── Keyboard ─────────────────────────────────────────────────────────────────
MAIN_KB = ReplyKeyboardMarkup([
    [KeyboardButton("✅ Сделано"),      KeyboardButton("📋 Планы на сегодня")],
    [KeyboardButton("➕ Добавить"),     KeyboardButton("📝 Список")],
    [KeyboardButton("🗑 Удалить"),      KeyboardButton("📊 Статистика")],
    [KeyboardButton("🗂 Категории")],
], resize_keyboard=True)

CANCEL_KB = ReplyKeyboardMarkup([[KeyboardButton("❌ Отмена")]], resize_keyboard=True)

def tz(): return pytz.timezone(TZ)
def today(): return datetime.now(tz()).strftime("%Y-%m-%d")
def now_time(): return datetime.now(tz()).strftime("%H:%M")
def fa(v): return str(int(v)) if float(v)==int(float(v)) else str(v)

def pbar(pct, n=8):
    f=int(pct/100*n); e=n-f
    b="🟩" if pct>=70 else "🟨" if pct>=40 else "🟥"
    return b*f+"⬜"*e

async def check(update):
    if not ALLOWED_UID: return True
    if str(update.effective_user.id)!=str(ALLOWED_UID):
        await update.message.reply_text("Приватный бот."); return False
    return True

# ── /start ────────────────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check(update): return
    u=update.effective_user
    sheets.register_user(str(u.id), u.first_name)
    await update.message.reply_text(f"Привет, {u.first_name}! 👋\n\nВыбери действие:", reply_markup=MAIN_KB)

# ── ДОБАВИТЬ ЗАДАЧУ ───────────────────────────────────────────────────────────
async def add_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check(update): return
    await update.message.reply_text("Введи название задачи:\n\nНапример: Отжимания", reply_markup=CANCEL_KB)
    return ADD_NAME

async def add_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ Отмена": return await cancel(update, ctx)
    ctx.user_data['new_habit'] = text

    uid  = str(update.effective_user.id)
    cats = sheets.get_categories(uid)

    if cats:
        buttons = [[InlineKeyboardButton(c["name"], callback_data=f"add_cat:{c['name']}")] for c in cats]
        buttons.append([InlineKeyboardButton("➕ Новая категория", callback_data="add_cat:__new__")])
        buttons.append([InlineKeyboardButton("Без категории", callback_data="add_cat:__none__")])
        await update.message.reply_text(
            f"Задача: {text}\n\nВыбери категорию:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return ADD_CAT
    else:
        # No categories yet → ask to create one or skip
        await update.message.reply_text(
            f"Задача: {text}\n\n"
            "У тебя нет категорий.\n"
            "Введи название новой категории или напиши «нет»:",
            reply_markup=CANCEL_KB
        )
        return ADD_CAT_NEW

async def add_cat_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid  = str(q.from_user.id)
    data = q.data.split(":", 1)[1]

    if data == "__new__":
        await q.edit_message_text("Введи название новой категории:")
        return ADD_CAT_NEW
    elif data == "__none__":
        ctx.user_data['new_cat'] = "Без категории"
    else:
        ctx.user_data['new_cat'] = data

    await q.edit_message_text(
        f"Задача: {ctx.user_data['new_habit']}\n"
        f"Категория: {ctx.user_data['new_cat']}\n\n"
        "Задай план — сколько нужно делать?\n"
        "Введи число или «нет»:"
    )
    return ADD_PLAN_AMT

async def add_cat_new(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ Отмена": return await cancel(update, ctx)
    uid = str(update.effective_user.id)

    if text.lower() in ("нет","no","-","skip","без категории"):
        ctx.user_data['new_cat'] = "Без категории"
    else:
        ctx.user_data['new_cat'] = text
        sheets.add_category(uid, text, target_pct=80)

    await update.message.reply_text(
        f"Задача: {ctx.user_data['new_habit']}\n"
        f"Категория: {ctx.user_data['new_cat']}\n\n"
        "Задай план — сколько нужно делать?\n"
        "Введи число или «нет»:",
        reply_markup=CANCEL_KB
    )
    return ADD_PLAN_AMT

async def add_plan_amt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ Отмена": return await cancel(update, ctx)
    uid   = str(update.effective_user.id)
    habit = ctx.user_data.get('new_habit','')
    cat   = ctx.user_data.get('new_cat','Без категории')

    sheets.add_habit(uid, habit, cat)

    if text.lower() in ("нет","no","-","skip"):
        await update.message.reply_text(
            f"✅ Задача «{habit}» добавлена!\nКатегория: {cat}\n\nОтмечай кнопкой «✅ Сделано»",
            reply_markup=MAIN_KB
        )
        return ConversationHandler.END

    try:
        ctx.user_data['plan_amt'] = float(text.replace(",","."))
        await update.message.reply_text(
            "Единица измерения:",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("раз"),    KeyboardButton("минут")],
                [KeyboardButton("км"),     KeyboardButton("страниц")],
                [KeyboardButton("стаканов"),KeyboardButton("часов")],
                [KeyboardButton("❌ Отмена")],
            ], resize_keyboard=True)
        )
        return ADD_PLAN_UNIT
    except ValueError:
        await update.message.reply_text("Введи число или «нет»:"); return ADD_PLAN_AMT

async def add_plan_unit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ Отмена": return await cancel(update, ctx)
    uid   = str(update.effective_user.id)
    habit = ctx.user_data.get('new_habit','')
    cat   = ctx.user_data.get('new_cat','Без категории')
    amt   = ctx.user_data.get('plan_amt',0)
    sheets.set_plan(uid, habit, amt, text)
    await update.message.reply_text(
        f"✅ Задача «{habit}» добавлена!\n"
        f"Категория: {cat}\n"
        f"План: {fa(amt)} {text} в день\n\n"
        "Отмечай кнопкой «✅ Сделано»",
        reply_markup=MAIN_KB
    )
    return ConversationHandler.END

# ── СДЕЛАНО ───────────────────────────────────────────────────────────────────
async def done_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check(update): return
    uid    = str(update.effective_user.id)
    habits = sheets.get_habits(uid)
    plans  = sheets.get_all_plans(uid)
    amts   = sheets.get_today_amounts(uid, today())

    if not habits:
        await update.message.reply_text("Нет задач. Нажми «➕ Добавить»", reply_markup=MAIN_KB)
        return ConversationHandler.END

    buttons = []
    for h in habits:
        plan=plans.get(h); done=amts.get(h,0.0)
        if plan and plan["target_amount"]>0:
            t=plan["target_amount"]; u=plan["unit"]
            pct=min(int(done/t*100),100)
            label=f"{h}  {fa(done)}/{fa(t)} {u} ({pct}%)"
        else: label=h
        buttons.append([InlineKeyboardButton(label, callback_data=f"dp:{h}")])

    await update.message.reply_text("Выбери задачу:", reply_markup=InlineKeyboardMarkup(buttons))
    return DONE_AMT

async def done_pick(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    h=q.data.split(":",1)[1]; uid=str(q.from_user.id)
    ctx.user_data['done_habit']=h
    plan=sheets.get_plan(uid,h)

    if plan and plan["target_amount"]>0:
        t=plan["target_amount"]; u=plan["unit"]
        amts=sheets.get_today_amounts(uid,today())
        done=amts.get(h,0.0); rem=max(t-done,0)
        await q.edit_message_text(
            f"✅ {h}\n\nПлан: {fa(t)} {u}\nСделано: {fa(done)} {u}\nОсталось: {fa(rem)} {u}\n\nСколько сделал сейчас?"
        )
        return DONE_AMT
    else:
        sheets.record_checkin(uid,h,"done",today(),now_time(),0)
        await q.edit_message_text(f"✅ {h} — выполнено!")
        return ConversationHandler.END

async def done_amt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text=update.message.text.strip()
    if text=="❌ Отмена": return await cancel(update,ctx)
    uid=str(update.effective_user.id); h=ctx.user_data.get('done_habit','')
    try: amt=float(text.replace(",","."))
    except ValueError:
        await update.message.reply_text("Введи число:"); return DONE_AMT

    sheets.record_checkin(uid,h,"done",today(),now_time(),amt)
    plan=sheets.get_plan(uid,h)
    if plan and plan["target_amount"]>0:
        t=plan["target_amount"]; u=plan["unit"]
        amts=sheets.get_today_amounts(uid,today())
        total=amts.get(h,amt); pct=min(int(total/t*100),100)
        msg=f"✅ {h}\n\n{pbar(pct)} {fa(total)}/{fa(t)} {u} ({pct}%)"
        if pct>=100: msg+="\n\n🎉 Цель достигнута!"
    else: msg=f"✅ {h} — выполнено!"
    await update.message.reply_text(msg, reply_markup=MAIN_KB)
    return ConversationHandler.END

# ── ПЛАНЫ НА СЕГОДНЯ ──────────────────────────────────────────────────────────
async def plans_today(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check(update): return
    uid=str(update.effective_user.id)
    habits=sheets.get_habits(uid); plans=sheets.get_all_plans(uid)
    amts=sheets.get_today_amounts(uid,today()); done_set=sheets.get_done_today(uid,today())
    if not habits:
        await update.message.reply_text("Нет задач.", reply_markup=MAIN_KB); return

    lines=[f"📋 {datetime.now(tz()).strftime('%d.%m.%Y')}\n"]
    done_count=0
    for h in habits:
        plan=plans.get(h); done_v=amts.get(h,0.0); is_done=h in done_set
        if plan and plan["target_amount"]>0:
            t=plan["target_amount"]; u=plan["unit"]
            pct=min(int(done_v/t*100),100); bar=pbar(pct,6)
            if done_v>=t: icon="✅"; done_count+=1
            elif done_v>0: icon="🔄"
            else: icon="⬜"
            lines.append(f"{icon} {h}\n   {bar} {fa(done_v)}/{fa(t)} {u} ({pct}%)")
        else:
            if is_done: icon="✅"; done_count+=1
            else: icon="⬜"
            lines.append(f"{icon} {h}")

    total=len(habits); op=int(done_count/total*100) if total else 0
    lines.append(f"\n{pbar(op)} {done_count}/{total} ({op}%)")
    await update.message.reply_text("\n".join(lines), reply_markup=MAIN_KB)

# ── СПИСОК ────────────────────────────────────────────────────────────────────
async def list_habits(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check(update): return
    uid=str(update.effective_user.id)
    habits_info=sheets.get_habits_with_category(uid)
    plans=sheets.get_all_plans(uid)
    if not habits_info:
        await update.message.reply_text("Нет задач.", reply_markup=MAIN_KB); return

    # Group by category
    by_cat={}
    for h in habits_info:
        by_cat.setdefault(h["category"],[]).append(h["name"])

    lines=["📝 Задачи:\n"]
    for cat,hs in by_cat.items():
        lines.append(f"📁 {cat}")
        for h in hs:
            p=plans.get(h)
            if p: lines.append(f"  • {h} — {fa(p['target_amount'])} {p['unit']}")
            else: lines.append(f"  • {h}")
        lines.append("")
    await update.message.reply_text("\n".join(lines), reply_markup=MAIN_KB)

# ── УДАЛИТЬ ───────────────────────────────────────────────────────────────────
async def delete_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check(update): return
    uid=str(update.effective_user.id); habits=sheets.get_habits(uid)
    if not habits:
        await update.message.reply_text("Нет задач.", reply_markup=MAIN_KB)
        return ConversationHandler.END
    btns=[[InlineKeyboardButton(h,callback_data=f"del:{h}")] for h in habits]
    await update.message.reply_text("Какую задачу удалить?", reply_markup=InlineKeyboardMarkup(btns))
    return ConversationHandler.END

async def delete_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    h=q.data.split(":",1)[1]
    btns=InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Да",callback_data=f"delok:{h}"),
        InlineKeyboardButton("❌ Нет",callback_data="delno"),
    ]])
    await q.edit_message_text(f"Удалить «{h}»?\nПлан тоже удалится.", reply_markup=btns)

async def delete_confirm_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if q.data=="delno": await q.edit_message_text("Отменено."); return
    h=q.data.split(":",1)[1]; uid=str(q.from_user.id)
    sheets.remove_habit(uid,h); sheets.remove_plan(uid,h)
    await q.edit_message_text(f"🗑 «{h}» удалена.")

# ── КАТЕГОРИИ ─────────────────────────────────────────────────────────────────
async def cats_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check(update): return
    uid=str(update.effective_user.id); cats=sheets.get_categories(uid)
    lines=["🗂 Категории:\n"]
    if cats:
        for c in cats: lines.append(f"• {c['name']} — план: {c['target_pct']}%")
    else: lines.append("Нет категорий.")
    lines.append("\n/addcat Название 80 — добавить категорию\n/delcat Название — удалить\n/settarget Название 85 — изменить цель")
    await update.message.reply_text("\n".join(lines), reply_markup=MAIN_KB)

async def add_cat_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check(update): return
    uid=str(update.effective_user.id)
    if len(ctx.args)<1:
        await update.message.reply_text("Формат: /addcat Здоровье 80"); return
    target=80
    if len(ctx.args)>=2:
        try: target=int(ctx.args[-1]); name=" ".join(ctx.args[:-1])
        except: name=" ".join(ctx.args)
    else: name=ctx.args[0]
    result=sheets.add_category(uid,name,target)
    if result=="exists":
        await update.message.reply_text(f"Категория «{name}» уже есть.")
    else:
        await update.message.reply_text(f"✅ Категория «{name}» добавлена!\nЦель: {target}%")

async def del_cat_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check(update): return
    uid=str(update.effective_user.id)
    if not ctx.args: await update.message.reply_text("Формат: /delcat Здоровье"); return
    name=" ".join(ctx.args)
    sheets.remove_category(uid,name)
    await update.message.reply_text(f"Категория «{name}» удалена.")

async def set_target_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check(update): return
    uid=str(update.effective_user.id)
    if len(ctx.args)<2: await update.message.reply_text("Формат: /settarget Здоровье 85"); return
    try:
        target=int(ctx.args[-1]); name=" ".join(ctx.args[:-1])
        sheets.set_category_target(uid,name,target)
        await update.message.reply_text(f"Цель для «{name}» изменена на {target}%")
    except ValueError:
        await update.message.reply_text("Цель должна быть числом, например: 85")

# ── СТАТИСТИКА ────────────────────────────────────────────────────────────────
async def stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check(update): return
    uid=str(update.effective_user.id)
    data=sheets.get_stats(uid,days=7)
    cat_stats=sheets.get_category_stats(uid,days=30)

    if not data:
        await update.message.reply_text("Нет данных.", reply_markup=MAIN_KB); return

    lines=["📊 Статистика за 7 дней:\n"]

    # Category summary
    if cat_stats:
        lines.append("── Категории (30 дней) ──")
        for c in cat_stats:
            actual=c["actual_pct"]; target=c["target_pct"]
            bar=pbar(actual,6)
            diff=actual-target
            trend="↑" if diff>=0 else "↓"
            lines.append(f"📁 {c['name']}")
            lines.append(f"{bar} {actual}% (план {target}%) {trend}{abs(diff)}%")
        lines.append("")

    # Per habit
    lines.append("── Задачи ──")
    for h,info in data.items():
        done=info["done"]; total=info["total"]
        pct=int(done/total*100) if total>0 else 0
        bar=pbar(pct); streak=info.get("streak",0)
        ss=f"  🔥{streak}" if streak>=2 else ""
        lines.append(f"{h}{ss}")
        lines.append(f"{bar} {done}/{total} дней ({pct}%)")
        plan=info.get("plan")
        if plan and plan["target_amount"]>0:
            t=plan["target_amount"]; u=plan["unit"]
            ta=info.get("today_amount",0.0)
            ap=min(int(ta/t*100),100)
            lines.append(f"Сегодня: {pbar(ap,6)} {fa(ta)}/{fa(t)} {u} ({ap}%)")
        lines.append("")

    await update.message.reply_text("\n".join(lines), reply_markup=MAIN_KB)

# ── ДАШБОРД ───────────────────────────────────────────────────────────────────
async def report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check(update): return
    uid=str(update.effective_user.id)
    if not DASHBOARD:
        await update.message.reply_text("Добавь DASHBOARD_URL в переменные.", reply_markup=MAIN_KB); return
    url=f"{DASHBOARD}?uid={uid}"
    kb=InlineKeyboardMarkup([[InlineKeyboardButton("📊 Открыть дашборд",web_app=WebAppInfo(url=url))]])
    await update.message.reply_text("Твой прогресс:", reply_markup=kb)

# ── ОТМЕНА ────────────────────────────────────────────────────────────────────
async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("Отменено.", reply_markup=MAIN_KB)
    return ConversationHandler.END

# ── TEXT HANDLER ──────────────────────────────────────────────────────────────
async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    t=update.message.text
    if t=="✅ Сделано":          await done_start(update,ctx)
    elif t=="📋 Планы на сегодня": await plans_today(update,ctx)
    elif t=="➕ Добавить":        await add_start(update,ctx)
    elif t=="📝 Список":          await list_habits(update,ctx)
    elif t=="🗑 Удалить":         await delete_start(update,ctx)
    elif t=="📊 Статистика":      await stats(update,ctx)
    elif t=="🗂 Категории":       await cats_menu(update,ctx)

# ── AUTO SKIP ─────────────────────────────────────────────────────────────────
async def auto_skip(ctx: ContextTypes.DEFAULT_TYPE):
    users=sheets.get_all_users()
    tz_=pytz.timezone(TZ); d=datetime.now(tz_).strftime("%Y-%m-%d"); t=datetime.now(tz_).strftime("%H:%M")
    for uid,name in users:
        for h in sheets.get_habits(uid):
            if h in sheets.get_done_today(uid,d): continue
            sheets.record_checkin(uid,h,"skip",d,t,0)

async def send_reminder(ctx: ContextTypes.DEFAULT_TYPE):
    users=sheets.get_all_users()
    tz_=pytz.timezone(TZ); d=datetime.now(tz_).strftime("%Y-%m-%d")
    for uid,name in users:
        habits=sheets.get_habits(uid)
        if not habits: continue
        done_set=sheets.get_done_today(uid,d)
        amts=sheets.get_today_amounts(uid,d)
        plans=sheets.get_all_plans(uid)
        pending=[h for h in habits if h not in done_set]
        if not pending: continue
        lines=[f"⏰ {name}, не забудь!\n"]
        for h in pending:
            p=plans.get(h)
            if p and p["target_amount"]>0:
                t=p["target_amount"]; u=p["unit"]; dv=amts.get(h,0.0)
                lines.append(f"⬜ {h}: {fa(dv)}/{fa(t)} {u}")
            else: lines.append(f"⬜ {h}")
        try:
            await ctx.bot.send_message(chat_id=uid,text="\n".join(lines),reply_markup=MAIN_KB)
        except Exception as e:
            logger.warning(f"Reminder {uid}: {e}")

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    app=Application.builder().token(TOKEN).build()

    add_conv=ConversationHandler(
        entry_points=[CommandHandler("add",add_start),MessageHandler(filters.Regex("^➕ Добавить$"),add_start)],
        states={
            ADD_NAME:     [MessageHandler(filters.TEXT&~filters.COMMAND,add_name)],
            ADD_CAT:      [CallbackQueryHandler(add_cat_callback,pattern="^add_cat:")],
            ADD_CAT_NEW:  [MessageHandler(filters.TEXT&~filters.COMMAND,add_cat_new)],
            ADD_PLAN_AMT: [MessageHandler(filters.TEXT&~filters.COMMAND,add_plan_amt)],
            ADD_PLAN_UNIT:[MessageHandler(filters.TEXT&~filters.COMMAND,add_plan_unit)],
        },
        fallbacks=[CommandHandler("cancel",cancel),MessageHandler(filters.Regex("^❌ Отмена$"),cancel)],
        allow_reentry=True,
    )

    done_conv=ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^✅ Сделано$"),done_start),CommandHandler("done",done_start)],
        states={
            DONE_AMT:[
                CallbackQueryHandler(done_pick,pattern="^dp:"),
                MessageHandler(filters.TEXT&~filters.COMMAND,done_amt),
            ],
        },
        fallbacks=[CommandHandler("cancel",cancel),MessageHandler(filters.Regex("^❌ Отмена$"),cancel)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start",start))
    app.add_handler(CommandHandler("help",start))
    app.add_handler(add_conv)
    app.add_handler(done_conv)
    app.add_handler(CallbackQueryHandler(delete_cb,          pattern="^del:"))
    app.add_handler(CallbackQueryHandler(delete_confirm_cb,  pattern="^(delok:|delno)"))
    app.add_handler(CommandHandler("list",   list_habits))
    app.add_handler(CommandHandler("stats",  stats))
    app.add_handler(CommandHandler("today",  plans_today))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("addcat", add_cat_cmd))
    app.add_handler(CommandHandler("delcat", del_cat_cmd))
    app.add_handler(CommandHandler("settarget", set_target_cmd))
    app.add_handler(MessageHandler(
        filters.TEXT&~filters.COMMAND&~filters.Regex("^(➕ Добавить|✅ Сделано)$"),
        handle_text
    ))

    tz_=pytz.timezone(TZ); jq=app.job_queue
    jq.run_daily(send_reminder, time=time(21,0,tzinfo=tz_))
    jq.run_daily(auto_skip,     time=time(23,55,tzinfo=tz_))

    logger.info("Бот запущен!"); app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__=="__main__":
    main()
