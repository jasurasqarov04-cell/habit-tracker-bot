"""
Google Sheets Helper — Categories, Habits, Plans, Checkins
"""
import os, logging
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
import gspread

logger = logging.getLogger(__name__)
SCOPES = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
S_USERS="Users"; S_HABITS="Habits"; S_CHECKINS="Checkins"; S_PLANS="Plans"; S_CATS="Categories"

class SheetsHelper:
    def __init__(self):
        import json
        j = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if j:
            creds = Credentials.from_service_account_info(json.loads(j), scopes=SCOPES)
        else:
            creds = Credentials.from_service_account_file(os.getenv("GOOGLE_CREDENTIALS_FILE","credentials.json"), scopes=SCOPES)
        client = gspread.authorize(creds)
        self.ss = client.open_by_key(os.getenv("SPREADSHEET_ID"))
        self._ensure()

    def _ensure(self):
        ex = [w.title for w in self.ss.worksheets()]
        if S_USERS not in ex:
            w=self.ss.add_worksheet(S_USERS,1000,4); w.append_row(["user_id","name","registered_at","timezone"])
        if S_HABITS not in ex:
            w=self.ss.add_worksheet(S_HABITS,2000,5); w.append_row(["user_id","habit_name","created_at","active","category"])
        if S_CHECKINS not in ex:
            w=self.ss.add_worksheet(S_CHECKINS,50000,7); w.append_row(["user_id","habit_name","date","time","status","weekday","amount"])
        if S_PLANS not in ex:
            w=self.ss.add_worksheet(S_PLANS,2000,5); w.append_row(["user_id","habit_name","target_amount","unit","active"])
        if S_CATS not in ex:
            w=self.ss.add_worksheet(S_CATS,500,4); w.append_row(["user_id","category_name","target_pct","active"])

    def _ws(self,name): return self.ss.worksheet(name)

    # ── Users ────────────────────────────────────────────────────────────────
    def register_user(self,uid,name):
        ws=self._ws(S_USERS); recs=ws.get_all_records()
        if not any(str(r["user_id"])==uid for r in recs):
            ws.append_row([uid,name,datetime.now().strftime("%Y-%m-%d %H:%M"),os.getenv("TIMEZONE","Asia/Tashkent")])

    def get_all_users(self):
        return [(str(r["user_id"]),r["name"]) for r in self._ws(S_USERS).get_all_records() if r.get("user_id")]

    # ── Categories ───────────────────────────────────────────────────────────
    def add_category(self,uid,name,target_pct=80):
        ws=self._ws(S_CATS); recs=ws.get_all_records()
        for r in recs:
            if str(r["user_id"])==uid and r["category_name"]==name and str(r["active"])=="1":
                return "exists"
        ws.append_row([uid,name,target_pct,"1"]); return "added"

    def get_categories(self,uid):
        result=[]
        for r in self._ws(S_CATS).get_all_records():
            if str(r["user_id"])==uid and str(r["active"])=="1":
                result.append({"name":r["category_name"],"target_pct":int(r.get("target_pct",80) or 80)})
        return result

    def remove_category(self,uid,name):
        ws=self._ws(S_CATS); recs=ws.get_all_records()
        for i,r in enumerate(recs,start=2):
            if str(r["user_id"])==uid and r["category_name"]==name:
                ws.update_cell(i,4,"0"); return True
        return False

    def set_category_target(self,uid,name,target_pct):
        ws=self._ws(S_CATS); recs=ws.get_all_records()
        for i,r in enumerate(recs,start=2):
            if str(r["user_id"])==uid and r["category_name"]==name and str(r["active"])=="1":
                ws.update_cell(i,3,target_pct); return True
        return False

    # ── Habits ───────────────────────────────────────────────────────────────
    def add_habit(self,uid,name,category="Без категории"):
        ws=self._ws(S_HABITS); recs=ws.get_all_records()
        for r in recs:
            if str(r["user_id"])==uid and r["habit_name"]==name and str(r["active"])=="1":
                return "exists"
        ws.append_row([uid,name,datetime.now().strftime("%Y-%m-%d"),"1",category]); return "added"

    def get_habits(self,uid):
        return [r["habit_name"] for r in self._ws(S_HABITS).get_all_records()
                if str(r["user_id"])==uid and str(r["active"])=="1"]

    def get_habits_with_category(self,uid):
        return [{"name":r["habit_name"],"category":r.get("category","Без категории") or "Без категории"}
                for r in self._ws(S_HABITS).get_all_records()
                if str(r["user_id"])==uid and str(r["active"])=="1"]

    def remove_habit(self,uid,name):
        ws=self._ws(S_HABITS); recs=ws.get_all_records()
        for i,r in enumerate(recs,start=2):
            if str(r["user_id"])==uid and r["habit_name"]==name:
                ws.update_cell(i,4,"0"); return True
        return False

    # ── Plans ─────────────────────────────────────────────────────────────────
    def set_plan(self,uid,name,target,unit):
        ws=self._ws(S_PLANS); recs=ws.get_all_records()
        for i,r in enumerate(recs,start=2):
            if str(r["user_id"])==uid and r["habit_name"]==name and str(r["active"])=="1":
                ws.update_cell(i,3,target); ws.update_cell(i,4,unit); return "updated"
        ws.append_row([uid,name,target,unit,"1"]); return "created"

    def get_plan(self,uid,name):
        for r in self._ws(S_PLANS).get_all_records():
            if str(r["user_id"])==uid and r["habit_name"]==name and str(r["active"])=="1":
                try: return {"target_amount":float(r["target_amount"]),"unit":str(r["unit"])}
                except: return None
        return None

    def get_all_plans(self,uid):
        result={}
        for r in self._ws(S_PLANS).get_all_records():
            if str(r["user_id"])==uid and str(r["active"])=="1":
                try: result[r["habit_name"]]={"target_amount":float(r["target_amount"]),"unit":str(r["unit"])}
                except: pass
        return result

    def remove_plan(self,uid,name):
        ws=self._ws(S_PLANS); recs=ws.get_all_records()
        for i,r in enumerate(recs,start=2):
            if str(r["user_id"])==uid and r["habit_name"]==name:
                ws.update_cell(i,5,"0"); return True
        return False

    # ── Checkins ──────────────────────────────────────────────────────────────
    def record_checkin(self,uid,name,status,date_str,time_str,amount=0):
        ws=self._ws(S_CHECKINS); recs=ws.get_all_records()
        for i,r in enumerate(recs,start=2):
            if str(r["user_id"])==uid and r["habit_name"]==name and r["date"]==date_str:
                ws.update_cell(i,5,status)
                old=float(r.get("amount",0) or 0)
                ws.update_cell(i,7,old+amount if amount>0 else old)
                return
        wd=datetime.strptime(date_str,"%Y-%m-%d").strftime("%A")
        ws.append_row([uid,name,date_str,time_str,status,wd,amount])

    def get_done_today(self,uid,date_str):
        return {r["habit_name"] for r in self._ws(S_CHECKINS).get_all_records()
                if str(r["user_id"])==uid and r["date"]==date_str and r["status"]=="done"}

    def get_today_amounts(self,uid,date_str):
        result={}
        for r in self._ws(S_CHECKINS).get_all_records():
            if str(r["user_id"])==uid and r["date"]==date_str:
                try: result[r["habit_name"]]=float(r.get("amount",0) or 0)
                except: result[r["habit_name"]]=0.0
        return result

    # ── Stats ─────────────────────────────────────────────────────────────────
    def get_stats(self,uid,days=7):
        habits=self.get_habits(uid)
        if not habits: return {}
        recs=self._ws(S_CHECKINS).get_all_records()
        plans=self.get_all_plans(uid)
        today=datetime.now().date(); today_s=today.strftime("%Y-%m-%d")
        date_range=[(today-timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
        ck={(r["habit_name"],r["date"]):r["status"] for r in recs
            if str(r["user_id"])==uid and r["date"] in set(date_range)}
        today_amt={}
        for r in recs:
            if str(r["user_id"])==uid and r["date"]==today_s:
                try: today_amt[r["habit_name"]]=float(r.get("amount",0) or 0)
                except: today_amt[r["habit_name"]]=0.0
        result={}
        for h in habits:
            done=sum(1 for d in date_range if ck.get((h,d))=="done")
            streak=0
            for d in date_range:
                if ck.get((h,d))=="done": streak+=1
                else: break
            e={"done":done,"total":days,"streak":streak,"today_amount":today_amt.get(h,0.0)}
            if h in plans: e["plan"]=plans[h]
            result[h]=e
        return result

    def get_category_stats(self,uid,days=30):
        """
        Статистика по категориям.
        actual_pct = среднее completion по всем задачам категории за N дней.
        """
        cats=self.get_categories(uid)
        habits_info=self.get_habits_with_category(uid)
        recs=self._ws(S_CHECKINS).get_all_records()
        plans=self.get_all_plans(uid)
        today=datetime.now().date(); today_s=today.strftime("%Y-%m-%d")
        date_range=[(today-timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
        date_set=set(date_range)

        ck={}; today_amt={}
        for r in recs:
            if str(r["user_id"])!=uid: continue
            if r["date"] in date_set: ck[(r["habit_name"],r["date"])]=r["status"]
            if r["date"]==today_s:
                try: today_amt[r["habit_name"]]=float(r.get("amount",0) or 0)
                except: today_amt[r["habit_name"]]=0.0

        cat_habits={}
        for h in habits_info:
            cat=h["category"] or "Без категории"
            cat_habits.setdefault(cat,[]).append(h["name"])

        result=[]
        for cat in cats:
            cname=cat["name"]; target=cat["target_pct"]
            hlist=cat_habits.get(cname,[])
            details=[]
            for h in hlist:
                done=sum(1 for d in date_range if ck.get((h,d))=="done")
                comp_pct=round(done/len(date_range)*100) if date_range else 0
                plan=plans.get(h)
                plan_pct=0
                if plan and plan["target_amount"]>0:
                    plan_pct=min(round(today_amt.get(h,0)/plan["target_amount"]*100),100)
                details.append({"name":h,"completion_pct":comp_pct,"plan_pct":plan_pct,
                                 "plan":plan,"today_amount":today_amt.get(h,0.0)})
            # среднее по задачам
            actual=round(sum(d["completion_pct"] for d in details)/len(details)) if details else 0
            result.append({"name":cname,"target_pct":target,"actual_pct":actual,"habits":details})
        return result

    def get_weekly_comparison(self,uid):
        habits=self.get_habits(uid)
        if not habits: return {}
        recs=self._ws(S_CHECKINS).get_all_records()
        today=datetime.now().date()
        tw=[(today-timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
        lw=[(today-timedelta(days=i+7)).strftime("%Y-%m-%d") for i in range(7)]
        ck={(r["habit_name"],r["date"]):r["status"] for r in recs
            if str(r["user_id"])==uid and r["date"] in set(tw+lw)}
        return {h:{"this_week":sum(1 for d in tw if ck.get((h,d))=="done"),
                   "last_week":sum(1 for d in lw if ck.get((h,d))=="done"),"total":7}
                for h in habits}
