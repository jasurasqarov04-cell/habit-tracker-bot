"""
Google Sheets Helper
Вся работа с таблицей: пользователи, привычки, чекины, статистика
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

# Названия листов в Google Sheets
SHEET_USERS    = "Users"
SHEET_HABITS   = "Habits"
SHEET_CHECKINS = "Checkins"


class SheetsHelper:
    def __init__(self):
        import json

        creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")

        if creds_json:
            # Railway / любой сервер — берём JSON прямо из переменной окружения
            creds_info = json.loads(creds_json)
            creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        else:
            # Локальный запуск — берём из файла credentials.json
            creds_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
            creds = Credentials.from_service_account_file(creds_file, scopes=SCOPES)

        client = gspread.authorize(creds)
        self.spreadsheet = client.open_by_key(os.getenv("SPREADSHEET_ID"))

        self._ensure_sheets()

    # ── Инициализация листов ──────────────────────────────────────────────

    def _ensure_sheets(self):
        """Создаёт листы и заголовки если их нет"""
        existing = [ws.title for ws in self.spreadsheet.worksheets()]

        if SHEET_USERS not in existing:
            ws = self.spreadsheet.add_worksheet(SHEET_USERS, rows=1000, cols=4)
            ws.append_row(["user_id", "name", "registered_at", "timezone"])

        if SHEET_HABITS not in existing:
            ws = self.spreadsheet.add_worksheet(SHEET_HABITS, rows=2000, cols=4)
            ws.append_row(["user_id", "habit_name", "created_at", "active"])

        if SHEET_CHECKINS not in existing:
            ws = self.spreadsheet.add_worksheet(SHEET_CHECKINS, rows=50000, cols=6)
            ws.append_row(["user_id", "habit_name", "date", "time", "status", "weekday"])

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
        """Возвращает [(user_id, name), ...]"""
        ws = self._sheet(SHEET_USERS)
        records = ws.get_all_records()
        return [(str(r["user_id"]), r["name"]) for r in records if r.get("user_id")]

    # ── Привычки ─────────────────────────────────────────────────────────

    def add_habit(self, user_id: str, habit_name: str) -> str:
        ws = self._sheet(SHEET_HABITS)
        records = ws.get_all_records()

        # Проверяем дубликат
        for r in records:
            if str(r["user_id"]) == user_id and r["habit_name"] == habit_name and r["active"] == "1":
                return "exists"

        ws.append_row([
            user_id, habit_name,
            datetime.now().strftime("%Y-%m-%d"),
            "1"
        ])
        return "added"

    def get_habits(self, user_id: str) -> list:
        """Возвращает список активных привычек пользователя"""
        ws = self._sheet(SHEET_HABITS)
        records = ws.get_all_records()
        return [
            r["habit_name"] for r in records
            if str(r["user_id"]) == user_id and str(r["active"]) == "1"
        ]

    def remove_habit(self, user_id: str, habit_name: str) -> bool:
        ws = self._sheet(SHEET_HABITS)
        records = ws.get_all_records()

        for i, r in enumerate(records, start=2):  # строки начинаются с 2 (1 = заголовок)
            if str(r["user_id"]) == user_id and r["habit_name"] == habit_name:
                ws.update_cell(i, 4, "0")  # колонка active = 0
                return True
        return False

    # ── Чекины ───────────────────────────────────────────────────────────

    def record_checkin(self, user_id: str, habit_name: str, status: str, date_str: str, time_str: str):
        ws = self._sheet(SHEET_CHECKINS)
        records = ws.get_all_records()

        # Удаляем старый чекин за тот же день (если был)
        for i, r in enumerate(records, start=2):
            if (str(r["user_id"]) == user_id
                    and r["habit_name"] == habit_name
                    and r["date"] == date_str):
                ws.update_cell(i, 5, status)  # просто обновляем статус
                return

        weekday = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A")
        ws.append_row([user_id, habit_name, date_str, time_str, status, weekday])

    def get_done_today(self, user_id: str, date_str: str) -> set:
        """Возвращает множество привычек, выполненных сегодня"""
        ws = self._sheet(SHEET_CHECKINS)
        records = ws.get_all_records()
        return {
            r["habit_name"] for r in records
            if str(r["user_id"]) == user_id
            and r["date"] == date_str
            and r["status"] == "done"
        }

    # ── Статистика ────────────────────────────────────────────────────────

    def get_stats(self, user_id: str, days: int = 7) -> dict:
        """
        Возвращает:
        {
          "Привычка": {
            "done": 5,
            "total": 7,
            "streak": 3
          }
        }
        """
        habits = self.get_habits(user_id)
        if not habits:
            return {}

        ws = self._sheet(SHEET_CHECKINS)
        records = ws.get_all_records()

        # Даты за последние N дней
        today = datetime.now().date()
        date_range = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]

        # Чекины пользователя за период
        user_checkins = {
            (r["habit_name"], r["date"]): r["status"]
            for r in records
            if str(r["user_id"]) == user_id and r["date"] in date_range
        }

        result = {}
        for habit in habits:
            done_count = sum(
                1 for d in date_range
                if user_checkins.get((habit, d)) == "done"
            )

            # Считаем текущую серию (streak)
            streak = 0
            for d in date_range:  # идём от сегодня назад
                if user_checkins.get((habit, d)) == "done":
                    streak += 1
                else:
                    break

            result[habit] = {
                "done": done_count,
                "total": days,
                "streak": streak
            }

        return result
