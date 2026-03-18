"""
Google Sheets Helper
Пользователи, привычки, чекины, планы, статистика
"""

import os
import logging
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
import gspread

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SHEET_USERS    = "Users"
SHEET_HABITS   = "Habits"
SHEET_CHECKINS = "Checkins"
SHEET_PLANS    = "Plans"


class SheetsHelper:
    def __init__(self):
        import json

        creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if creds_json:
            creds_info = json.loads(creds_json)
            creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        else:
            creds_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
            creds = Credentials.from_service_account_file(creds_file, scopes=SCOPES)

        client = gspread.authorize(creds)
        self.spreadsheet = client.open_by_key(os.getenv("SPREADSHEET_ID"))
        self._ensure_sheets()

    # ── Инициализация листов ──────────────────────────────────────────────

    def _ensure_sheets(self):
        existing = [ws.title for ws in self.spreadsheet.worksheets()]

        if SHEET_USERS not in existing:
            ws = self.spreadsheet.add_worksheet(SHEET_USERS, rows=1000, cols=4)
            ws.append_row(["user_id", "name", "registered_at", "timezone"])

        if SHEET_HABITS not in existing:
            ws = self.spreadsheet.add_worksheet(SHEET_HABITS, rows=2000, cols=4)
            ws.append_row(["user_id", "habit_name", "created_at", "active"])

        if SHEET_CHECKINS not in existing:
            ws = self.spreadsheet.add_worksheet(SHEET_CHECKINS, rows=50000, cols=7)
            # Добавили колонку amount
            ws.append_row(["user_id", "habit_name", "date", "time", "status", "weekday", "amount"])

        if SHEET_PLANS not in existing:
            ws = self.spreadsheet.add_worksheet(SHEET_PLANS, rows=2000, cols=5)
            ws.append_row(["user_id", "habit_name", "target_amount", "unit", "active"])

    def _sheet(self, name: str):
        return self.spreadsheet.worksheet(name)

    # ── Пользователи ─────────────────────────────────────────────────────

    def register_user(self, user_id: str, name: str):
        ws = self._sheet(SHEET_USERS)
        records = ws.get_all_records()
        if not any(str(r["user_id"]) == user_id for r in records):
            ws.append_row([
                user_id, name,
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                os.getenv("TIMEZONE", "Asia/Tashkent")
            ])

    def get_all_users(self) -> list:
        ws = self._sheet(SHEET_USERS)
        records = ws.get_all_records()
        return [(str(r["user_id"]), r["name"]) for r in records if r.get("user_id")]

    # ── Привычки ─────────────────────────────────────────────────────────

    def add_habit(self, user_id: str, habit_name: str) -> str:
        ws = self._sheet(SHEET_HABITS)
        records = ws.get_all_records()
        for r in records:
            if str(r["user_id"]) == user_id and r["habit_name"] == habit_name and str(r["active"]) == "1":
                return "exists"
        ws.append_row([user_id, habit_name, datetime.now().strftime("%Y-%m-%d"), "1"])
        return "added"

    def get_habits(self, user_id: str) -> list:
        ws = self._sheet(SHEET_HABITS)
        records = ws.get_all_records()
        return [
            r["habit_name"] for r in records
            if str(r["user_id"]) == user_id and str(r["active"]) == "1"
        ]

    def remove_habit(self, user_id: str, habit_name: str) -> bool:
        ws = self._sheet(SHEET_HABITS)
        records = ws.get_all_records()
        for i, r in enumerate(records, start=2):
            if str(r["user_id"]) == user_id and r["habit_name"] == habit_name:
                ws.update_cell(i, 4, "0")
                return True
        return False

    # ── Планы (цели по количеству) ────────────────────────────────────────

    def set_plan(self, user_id: str, habit_name: str, target_amount: float, unit: str) -> str:
        """
        Устанавливает план для привычки.
        Если план уже есть — обновляет. Иначе создаёт новый.
        Возвращает: 'updated' или 'created'
        """
        ws = self._sheet(SHEET_PLANS)
        records = ws.get_all_records()

        for i, r in enumerate(records, start=2):
            if str(r["user_id"]) == user_id and r["habit_name"] == habit_name and str(r["active"]) == "1":
                ws.update_cell(i, 3, target_amount)
                ws.update_cell(i, 4, unit)
                return "updated"

        ws.append_row([user_id, habit_name, target_amount, unit, "1"])
        return "created"

    def get_plan(self, user_id: str, habit_name: str) -> dict | None:
        """
        Возвращает план для привычки или None.
        Формат: {"target_amount": 50, "unit": "раз"}
        """
        ws = self._sheet(SHEET_PLANS)
        records = ws.get_all_records()
        for r in records:
            if (str(r["user_id"]) == user_id
                    and r["habit_name"] == habit_name
                    and str(r["active"]) == "1"):
                try:
                    return {
                        "target_amount": float(r["target_amount"]),
                        "unit": str(r["unit"]),
                    }
                except (ValueError, KeyError):
                    return None
        return None

    def get_all_plans(self, user_id: str) -> dict:
        """
        Возвращает все планы пользователя.
        Формат: {"Привычка": {"target_amount": 50, "unit": "раз"}}
        """
        ws = self._sheet(SHEET_PLANS)
        records = ws.get_all_records()
        result = {}
        for r in records:
            if str(r["user_id"]) == user_id and str(r["active"]) == "1":
                try:
                    result[r["habit_name"]] = {
                        "target_amount": float(r["target_amount"]),
                        "unit": str(r["unit"]),
                    }
                except (ValueError, KeyError):
                    pass
        return result

    def remove_plan(self, user_id: str, habit_name: str) -> bool:
        ws = self._sheet(SHEET_PLANS)
        records = ws.get_all_records()
        for i, r in enumerate(records, start=2):
            if str(r["user_id"]) == user_id and r["habit_name"] == habit_name:
                ws.update_cell(i, 5, "0")
                return True
        return False

    # ── Чекины ───────────────────────────────────────────────────────────

    def record_checkin(self, user_id: str, habit_name: str, status: str,
                       date_str: str, time_str: str, amount: float = 0):
        """
        Записывает чекин с количеством (amount).
        Если за этот день уже есть запись — обновляет статус и добавляет к amount.
        """
        ws = self._sheet(SHEET_CHECKINS)
        records = ws.get_all_records()

        for i, r in enumerate(records, start=2):
            if (str(r["user_id"]) == user_id
                    and r["habit_name"] == habit_name
                    and r["date"] == date_str):
                ws.update_cell(i, 5, status)
                # Суммируем количество (если вводят несколько раз за день)
                old_amount = float(r.get("amount", 0) or 0)
                new_amount = old_amount + amount if amount > 0 else old_amount
                ws.update_cell(i, 7, new_amount)
                return

        weekday = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A")
        ws.append_row([user_id, habit_name, date_str, time_str, status, weekday, amount])

    def get_done_today(self, user_id: str, date_str: str) -> set:
        ws = self._sheet(SHEET_CHECKINS)
        records = ws.get_all_records()
        return {
            r["habit_name"] for r in records
            if str(r["user_id"]) == user_id
            and r["date"] == date_str
            and r["status"] == "done"
        }

    def get_today_amounts(self, user_id: str, date_str: str) -> dict:
        """
        Возвращает сколько выполнено сегодня по каждой привычке.
        Формат: {"Привычка": 45.0}
        """
        ws = self._sheet(SHEET_CHECKINS)
        records = ws.get_all_records()
        result = {}
        for r in records:
            if str(r["user_id"]) == user_id and r["date"] == date_str:
                try:
                    result[r["habit_name"]] = float(r.get("amount", 0) or 0)
                except (ValueError, TypeError):
                    result[r["habit_name"]] = 0.0
        return result

    # ── Статистика ────────────────────────────────────────────────────────

    def get_weekly_comparison(self, user_id: str) -> dict:
        habits = self.get_habits(user_id)
        if not habits:
            return {}

        ws = self._sheet(SHEET_CHECKINS)
        records = ws.get_all_records()

        today = datetime.now().date()
        this_week = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
        last_week = [(today - timedelta(days=i + 7)).strftime("%Y-%m-%d") for i in range(7)]
        all_dates = set(this_week + last_week)

        user_checkins = {
            (r["habit_name"], r["date"]): r["status"]
            for r in records
            if str(r["user_id"]) == user_id and r["date"] in all_dates
        }

        result = {}
        for habit in habits:
            this = sum(1 for d in this_week if user_checkins.get((habit, d)) == "done")
            last = sum(1 for d in last_week if user_checkins.get((habit, d)) == "done")
            result[habit] = {"this_week": this, "last_week": last, "total": 7}

        return result

    def get_stats(self, user_id: str, days: int = 7) -> dict:
        """
        Возвращает статистику за N дней.
        Если есть план — добавляет данные о количестве.
        Формат:
        {
          "Привычка": {
            "done": 5, "total": 7, "streak": 3,
            "plan": {"target_amount": 50, "unit": "раз"},   # если задан план
            "today_amount": 45.0                             # сегодня выполнено
          }
        }
        """
        habits = self.get_habits(user_id)
        if not habits:
            return {}

        ws = self._sheet(SHEET_CHECKINS)
        records = ws.get_all_records()
        plans = self.get_all_plans(user_id)

        today = datetime.now().date()
        today_str = today.strftime("%Y-%m-%d")
        date_range = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]

        user_checkins = {
            (r["habit_name"], r["date"]): r["status"]
            for r in records
            if str(r["user_id"]) == user_id and r["date"] in date_range
        }

        # Количество за сегодня
        today_amounts = {}
        for r in records:
            if str(r["user_id"]) == user_id and r["date"] == today_str:
                try:
                    today_amounts[r["habit_name"]] = float(r.get("amount", 0) or 0)
                except (ValueError, TypeError):
                    today_amounts[r["habit_name"]] = 0.0

        result = {}
        for habit in habits:
            done_count = sum(
                1 for d in date_range
                if user_checkins.get((habit, d)) == "done"
            )
            streak = 0
            for d in date_range:
                if user_checkins.get((habit, d)) == "done":
                    streak += 1
                else:
                    break

            entry = {
                "done": done_count,
                "total": days,
                "streak": streak,
                "today_amount": today_amounts.get(habit, 0.0),
            }

            if habit in plans:
                entry["plan"] = plans[habit]

            result[habit] = entry

        return result
