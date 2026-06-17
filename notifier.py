import json
import requests
import yaml
import schedule
import time
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

# ─── Bảng tiết → giờ (USTH) ───────────────────────────────────────────────────
TIET_TO_TIME = {
    1:  "07:30", 2:  "08:25", 3:  "09:25",
    4:  "10:20", 5:  "11:15", 6:  "12:10",
    7:  "13:00", 8:  "13:55", 9:  "14:50",
    10: "15:45", 11: "16:40", 12: "17:35",
    13: "18:30", 14: "19:25", 15: "20:20",
}

TIMETABLE_URL = "https://erp.usth.edu.vn/student-services/api/v2/timetables/query-student-timetable-in-range"

# ─── Load config ──────────────────────────────────────────────────────────────
def load_config():
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def get_headers(config):
    u = config["usth"]
    cookie = (
        f"JSESSIONID={u['jsessionid']}; "
        f"x-student-portal-token={u['student_token']}; "
        f"x-access-token={u['access_token']}"
    )
    return {
        "x-student-portal-token": u["student_token"],
        "x-access-token":         u["access_token"],
        "x-check-sum":            "a90709f7c1abdebaf88c5a670b314845951d3885d9d8dce77d107032bbe620d9",
        "Content-Type":           "application/json",
        "Cookie":                 cookie,
        "Referer":                "https://erp.usth.edu.vn/students/learn/timetable",
        "Origin":                 "https://erp.usth.edu.vn",
        "User-Agent":             "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

# ─── Helpers ──────────────────────────────────────────────────────────────────
def parse_time(val):
    if val <= 0:
        return "?"
    if val > 100:
        return f"{val // 100:02d}:{val % 100:02d}"
    return TIET_TO_TIME.get(val, f"Tiết {val}")

def ts_to_dt(ts_ms):
    return datetime.utcfromtimestamp(ts_ms / 1000) + timedelta(hours=7)

def day_name(dt):
    return ["Thứ 2","Thứ 3","Thứ 4","Thứ 5","Thứ 6","Thứ 7","Chủ nhật"][dt.weekday()]

# ─── Discord ──────────────────────────────────────────────────────────────────
def send_discord(webhook_url, content=None, embeds=None):
    payload = {"username": "USTH Lịch Học 📅"}
    if content:
        payload["content"] = content
    if embeds:
        payload["embeds"] = embeds
    try:
        r = requests.post(webhook_url, json=payload, timeout=10)
        return r.status_code in (200, 204)
    except Exception as e:
        print(f"  ✗ Lỗi Discord: {e}")
        return False

# ─── Fetch API ────────────────────────────────────────────────────────────────
def fetch_timetable(config, months_ahead=3):
    now   = datetime.now()
    start = datetime(now.year, now.month, 1)
    end_month = now.month + months_ahead
    end_year  = now.year + (end_month - 1) // 12
    end_month = (end_month - 1) % 12 + 1
    end = datetime(end_year, end_month, 1) - timedelta(milliseconds=1)

    payload = {
        "fromTime": int(start.timestamp() * 1000),
        "toTime":   int(end.timestamp() * 1000),
    }

    # Load config mới nhất mỗi lần fetch (để nhận token mới nếu user đã cập nhật)
    config = load_config()
    headers = get_headers(config)

    r = requests.post(TIMETABLE_URL, json=payload, headers=headers, timeout=15)

    if r.status_code == 401:
        raise Exception("TOKEN_EXPIRED")
    r.raise_for_status()
    return r.json()

# ─── Parse ────────────────────────────────────────────────────────────────────
def parse_sessions(data):
    sessions = []
    for item in data:
        course   = item.get("courseName", "")
        class_id = item.get("classId", "")
        ctype    = item.get("classType", "")

        for cal in item.get("_calendars", []):
            if isinstance(cal, str):
                cal = json.loads(cal)

            date_ts = cal.get("date", -1)
            if date_ts <= 0:
                continue

            from_v   = cal.get("from", 0)
            to_v     = cal.get("to", 0)
            place    = cal.get("place", "?")
            teachers = ", ".join(cal.get("teacherNames", [])) or "?"

            dt    = ts_to_dt(date_ts)
            start = parse_time(from_v)
            end   = parse_time(to_v)

            try:
                start_dt = datetime.strptime(
                    f"{dt.strftime('%d/%m/%Y')} {start}", "%d/%m/%Y %H:%M"
                )
            except Exception:
                continue

            tiet_str = (f"Tiết {from_v}–{to_v}" if from_v <= 15
                        else f"{start}–{end}")

            sessions.append({
                "course":   course,
                "class_id": class_id,
                "ctype":    ctype,
                "date":     dt.strftime("%d/%m/%Y"),
                "dow":      day_name(dt),
                "start":    start,
                "end":      end,
                "tiet":     tiet_str,
                "place":    place,
                "teacher":  teachers,
                "start_dt": start_dt,
                "key":      f"{class_id}_{date_ts}_{from_v}",
            })

    sessions.sort(key=lambda x: x["start_dt"])
    return sessions

def sessions_hash(sessions):
    keys = "|".join(s["key"] for s in sessions)
    return hashlib.md5(keys.encode()).hexdigest()

# ─── Notification helpers ─────────────────────────────────────────────────────
def fmt_session_block(s):
    return (
        f"📚 **{s['course']}** `{s['class_id']}`\n"
        f"📅 {s['dow']}, {s['date']}\n"
        f"⏰ {s['tiet']} ({s['start']} – {s['end']})\n"
        f"🏫 {s['place']}\n"
        f"👨‍🏫 {s['teacher']}"
    )

def notify_daily_schedule(sessions, webhook_url):
    today = datetime.now().strftime("%d/%m/%Y")
    today_s = [s for s in sessions if s["date"] == today]

    if today_s:
        parts = [f"📅 **Lịch học hôm nay — {today}**\n"]
        for s in today_s:
            parts.append(
                f"▸ **{s['course']}** | {s['tiet']} | 📍 {s['place']}"
            )
        content = "\n".join(parts)
    else:
        content = f"📅 **Lịch học hôm nay — {today}**\n\n🎉 Không có lịch học!"

    send_discord(webhook_url, content=content)
    print(f"  📅 Đã gửi lịch ngày {today} ({len(today_s)} buổi)")

def notify_reminder(s, webhook_url, label):
    content = (
        f"🔔 **Nhắc lịch học — còn {label}!**\n\n"
        + fmt_session_block(s)
    )
    send_discord(webhook_url, content=content)
    print(f"  ⏰ Nhắc [{label}]: {s['course']} lúc {s['start']} ngày {s['date']}")

def notify_changes(added, removed, webhook_url):
    lines = []
    for s in added:
        lines.append(f"✅ **Thêm:** {s['course']} — {s['dow']}, {s['date']} | {s['tiet']} | {s['place']}")
    for s in removed:
        lines.append(f"❌ **Xóa:** {s['course']} — {s['dow']}, {s['date']} | {s['tiet']} | {s['place']}")
    if lines:
        content = "🔄 **Lịch học vừa thay đổi!**\n\n" + "\n".join(lines)
        send_discord(webhook_url, content=content)
        print(f"  🔄 Thay đổi: +{len(added)} -{len(removed)} buổi")

def notify_token_expired(webhook_url):
    send_discord(webhook_url,
        content=(
            "⚠️ **Token USTH đã hết hạn!**\n\n"
            "Vào `erp.usth.edu.vn` → F12 → Network → `query-student-timetable-in-range`\n"
            "Copy `x-student-portal-token`, `x-access-token`, `JSESSIONID`\n"
            "Paste vào `config.yaml` rồi restart bot."
        )
    )

# ─── State ────────────────────────────────────────────────────────────────────
class BotState:
    def __init__(self):
        self.sessions      = []
        self.last_hash     = ""
        self.reminded_keys = set()
        self.last_daily    = ""
        self._remind_date  = ""

state = BotState()

# ─── Jobs ─────────────────────────────────────────────────────────────────────
def job_fetch_and_detect(config):
    webhook = config["discord"]["webhook_url"]
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🔄 Đang fetch lịch học...")
    try:
        raw      = fetch_timetable(config)
        new_sess = parse_sessions(raw)
        new_hash = sessions_hash(new_sess)

        if state.last_hash and new_hash != state.last_hash:
            old_keys = {s["key"] for s in state.sessions}
            new_keys = {s["key"] for s in new_sess}
            added    = [s for s in new_sess        if s["key"] not in old_keys]
            removed  = [s for s in state.sessions  if s["key"] not in new_keys]
            notify_changes(added, removed, webhook)

        state.sessions  = new_sess
        state.last_hash = new_hash
        print(f"  ✅ Cập nhật xong: {len(new_sess)} buổi học")
        print(f"  📁 Đã lưu timetable.json")
        for s in new_sess[:3]:
            print(f"      → {s['course']} | {s['date']}")

        with open("timetable.json", "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)

    except Exception as e:
        if "TOKEN_EXPIRED" in str(e):
            print("  ✗ Token hết hạn!")
            notify_token_expired(config["discord"]["webhook_url"])
        else:
            print(f"  ✗ Lỗi fetch: {e}")

def job_daily_schedule(config):
    today = datetime.now().strftime("%d/%m/%Y")
    if state.last_daily == today:
        return
    if not state.sessions:
        job_fetch_and_detect(config)
    notify_daily_schedule(state.sessions, config["discord"]["webhook_url"])
    state.last_daily = today

def job_reminders(config):
    if not state.sessions:
        return
    now     = datetime.now()
    webhook = config["discord"]["webhook_url"]
    today   = now.strftime("%d/%m/%Y")

    if state._remind_date != today:
        state.reminded_keys = set()
        state._remind_date  = today

    # ── Nhắc 1 ngày trước: gộp tất cả buổi học ngày mai vào 1 tin ──
    tomorrow = (now + timedelta(days=1)).strftime("%d/%m/%Y")
    rid_tomorrow = f"tomorrow_{tomorrow}"
    tomorrow_sessions = [s for s in state.sessions if s["date"] == tomorrow]

    if tomorrow_sessions and rid_tomorrow not in state.reminded_keys:
        for s in tomorrow_sessions:
            notify_at = s["start_dt"] - timedelta(hours=24)
            diff = (notify_at - now).total_seconds()
            if 0 <= diff <= 65:
                # Gộp tất cả buổi ngày mai thành 1 tin
                lines = [f"🔔 **Nhắc lịch học ngày mai — {tomorrow}!**\n"]
                for ts in tomorrow_sessions:
                    lines.append(
                        f"▸ **{ts['course']}**\n"
                        f"  ⏰ {ts['tiet']} ({ts['start']} – {ts['end']})\n"
                        f"  🏫 {ts['place']}  |  👨‍🏫 {ts['teacher']}"
                    )
                send_discord(webhook, content="\n\n".join(lines))
                print(f"  ⏰ Nhắc 1 ngày: {len(tomorrow_sessions)} buổi ngày {tomorrow}")
                state.reminded_keys.add(rid_tomorrow)
                break  # gửi 1 lần là đủ

    # ── Nhắc 1 giờ và 30 phút: gộp theo từng mốc thời gian ──
    short_reminders = [r for r in config.get("reminders", []) if r["hours_before"] < 24]

    for r in short_reminders:
        hb    = r["hours_before"]
        label = f"{int(hb * 60)} phút" if hb < 1 else f"{int(hb)} giờ"

        # Tìm tất cả buổi học cùng mốc nhắc
        to_notify = []
        for s in state.sessions:
            rid = f"{s['key']}_{label}"
            if rid in state.reminded_keys:
                continue
            notify_at = s["start_dt"] - timedelta(hours=hb)
            diff = (notify_at - now).total_seconds()
            if 0 <= diff <= 65:
                to_notify.append((s, rid))

        if not to_notify:
            continue

        if len(to_notify) == 1:
            # Chỉ 1 buổi → gửi bình thường
            s, rid = to_notify[0]
            content = (
                f"🔔 **Nhắc lịch học — còn {label}!**\n\n"
                + fmt_session_block(s)
            )
            send_discord(webhook, content=content)
            print(f"  ⏰ Nhắc [{label}]: {s['course']}")
        else:
            # Nhiều buổi cùng giờ → gộp lại
            lines = [f"🔔 **Nhắc lịch học — còn {label}!**\n"]
            for s, rid in to_notify:
                lines.append(
                    f"▸ **{s['course']}**\n"
                    f"  ⏰ {s['tiet']} ({s['start']} – {s['end']})\n"
                    f"  🏫 {s['place']}  |  👨‍🏫 {s['teacher']}"
                )
            send_discord(webhook, content="\n\n".join(lines))
            print(f"  ⏰ Nhắc [{label}]: {len(to_notify)} buổi")

        for s, rid in to_notify:
            state.reminded_keys.add(rid)


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    config  = load_config()
    webhook = config["discord"]["webhook_url"]

    print("=" * 50)
    print("  USTH Schedule Bot")
    print("=" * 50)

    # Fetch lần đầu
    job_fetch_and_detect(config)

    if not state.sessions:
        print("⚠ Không tìm thấy buổi học nào có lịch cụ thể.")
        print("  Có thể token đã hết hạn — cập nhật config.yaml rồi thử lại.")
    else:
        send_discord(webhook,
            content=(
                f"✅ **Bot khởi động thành công!**\n"
                f"📊 Tìm thấy **{len(state.sessions)}** buổi học có lịch cụ thể.\n"
                f"⏰ Sẽ gửi lịch ngày lúc **6:00 sáng** mỗi ngày."
            )
        )
        print(f"\n📋 Các buổi học tìm thấy:")
        for s in state.sessions:
            print(f"  → {s['course']:45s} | {s['date']} | {s['tiet']:15s} | {s['place']}")

    fetch_interval = config.get("fetch_interval_minutes", 30)
    schedule.every(fetch_interval).minutes.do(job_fetch_and_detect, config=config)
    schedule.every().day.at("06:00").do(job_daily_schedule, config=config)
    schedule.every(1).minutes.do(job_reminders, config=config)

    print(f"\n📅 Bot đang chạy (fetch mỗi {fetch_interval} phút). Ctrl+C để dừng.\n")

    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()