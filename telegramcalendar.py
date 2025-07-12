from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import datetime
import calendar
import json
import os

def init_json_file():
    if not os.path.exists("reminder.json"):
        with open("reminder.json", "w", encoding='utf-8') as file:
            json.dump({"напоминания": {}}, file, ensure_ascii=False, indent=4)

def get_user_timezone(user_id):
    init_json_file()
    try:
        with open("reminder.json", "r", encoding='utf-8') as file:
            data = json.load(file)
            return data["напоминания"].get(str(user_id), {}).get("часовой_пояс", 0)
    except (json.JSONDecodeError, KeyError):
        return 0

def create_callback_data(action, *args):
    return ";".join([action] + [str(arg) for arg in args])

def separate_callback_data(data):
    return data.split(";")

def create_clock(tz_offset=0, hour=None, minute=None, period=None):
    now = datetime.datetime.now()
    
    if hour is None:
        hour = (now.hour + tz_offset) % 24
        period = "pm" if hour >= 12 else "am"
        hour = hour % 12 or 12
        minute = (now.minute // 10) * 10
    
    keyboard = [
        [
            InlineKeyboardButton("↑", callback_data=create_callback_data("HOUR_UP", hour, minute, period)),
            InlineKeyboardButton("↑", callback_data=create_callback_data("MIN_UP", hour, minute, period)),
            InlineKeyboardButton("↑", callback_data=create_callback_data("PERIOD_TOGGLE", hour, minute, period))
        ],
        [
            InlineKeyboardButton(str(hour), callback_data="IGNORE"),
            InlineKeyboardButton(f"{minute:02d}", callback_data="IGNORE"),
            InlineKeyboardButton(period, callback_data="IGNORE")
        ],
        [
            InlineKeyboardButton("↓", callback_data=create_callback_data("HOUR_DOWN", hour, minute, period)),
            InlineKeyboardButton("↓", callback_data=create_callback_data("MIN_DOWN", hour, minute, period)),
            InlineKeyboardButton("↓", callback_data=create_callback_data("PERIOD_TOGGLE", hour, minute, period))
        ],
        [InlineKeyboardButton("OK", callback_data=create_callback_data("TIME_OK", hour, minute, period))]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_calendar(year=None, month=None):
    now = datetime.datetime.now()
    if year is None: year = now.year
    if month is None: month = now.month
    
    keyboard = [
        [InlineKeyboardButton(f"{calendar.month_name[month]} {year}", callback_data="IGNORE")],
        [InlineKeyboardButton(day, callback_data="IGNORE") for day in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]]
    ]
    
    for week in calendar.monthcalendar(year, month):
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data="IGNORE"))
            else:
                row.append(InlineKeyboardButton(str(day), callback_data=create_callback_data("DAY", year, month, day)))
        keyboard.append(row)
    
    keyboard.append([
        InlineKeyboardButton("<", callback_data=create_callback_data("PREV_MONTH", year, month)),
        InlineKeyboardButton(" ", callback_data="IGNORE"),
        InlineKeyboardButton(">", callback_data=create_callback_data("NEXT_MONTH", year, month))
    ])
    
    return InlineKeyboardMarkup(keyboard)

def process_clock_selection(update, context):
    query = update.callback_query
    data = query.data
    
    if data == "IGNORE":
        return False, None
    
    parts = separate_callback_data(data)
    if len(parts) < 4:
        return False, None
    
    action, hour, minute, period = parts[0], parts[1], parts[2], parts[3]
    
    try:
        hour = int(hour)
        minute = int(minute)
    except ValueError:
        return False, None
    
    if action == "HOUR_UP":
        hour = hour % 12 + 1
    elif action == "HOUR_DOWN":
        hour = (hour - 2) % 12 + 1
    elif action == "MIN_UP":
        minute = (minute + 10) % 60
    elif action == "MIN_DOWN":
        minute = (minute - 10) % 60
    elif action == "PERIOD_TOGGLE":
        period = "pm" if period == "am" else "am"
    elif action == "TIME_OK":
        return True, [hour, minute, period]
    
    query.edit_message_reply_markup(reply_markup=create_clock(hour=hour, minute=minute, period=period))
    return False, None

def process_calendar_selection(update, context):
    query = update.callback_query
    data = query.data
    
    if data == "IGNORE":
        return False, None
    
    parts = separate_callback_data(data)
    if len(parts) < 3:
        return False, None
    
    action, year, month = parts[0], parts[1], parts[2]
    
    try:
        year = int(year)
        month = int(month)
    except ValueError:
        return False, None
    
    if action == "DAY":
        if len(parts) < 4:
            return False, None
        day = int(parts[3])
        return True, datetime.datetime(year, month, day)
    elif action == "PREV_MONTH":
        prev_month = datetime.datetime(year, month, 1) - datetime.timedelta(days=1)
        query.edit_message_reply_markup(reply_markup=create_calendar(prev_month.year, prev_month.month))
    elif action == "NEXT_MONTH":
        next_month = datetime.datetime(year, month, 28) + datetime.timedelta(days=4)
        query.edit_message_reply_markup(reply_markup=create_calendar(next_month.year, next_month.month))
    
    return False, None