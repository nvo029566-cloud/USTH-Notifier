import json
from datetime import datetime, timedelta

with open("timetable.json", encoding="utf-8") as f:
    data = json.load(f)

now = datetime.now()
future = []

for item in data:
    for cal in item.get("_calendars", []):
        if isinstance(cal, str):
            cal = json.loads(cal)
        dt = datetime.utcfromtimestamp(cal["date"] / 1000) + timedelta(hours=7)
        if dt >= now:
            future.append((dt, item["courseName"], cal.get("place", "?")))

future.sort()

if future:
    print(f"Tìm thấy {len(future)} buổi học sắp tới:\n")
    for dt, course, place in future:
        print(f"  {dt.strftime('%d/%m/%Y %H:%M')}  |  {course:40s}  |  {place}")
else:
    print("Không có buổi học nào trong tương lai trong file timetable.json hiện tại.")
    print("Cần fetch lại từ API để lấy lịch học kỳ mới.")