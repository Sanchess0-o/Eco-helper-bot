import logging
import sqlite3
import json
import os
import random
import calendar
from datetime import time, datetime, timedelta
import pytz
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove
)
from telegram.ext import (
    Application, 
    CommandHandler, 
    CallbackQueryHandler, 
    ContextTypes,
    ConversationHandler, 
    MessageHandler, 
    filters
)
from warnings import filterwarnings
from telegram.warnings import PTBUserWarning

filterwarnings(action="ignore", message=r".*CallbackQueryHandler", category=PTBUserWarning)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константы
SELECTING_TIME, SELECTING_TIMEZONE = range(2)
NAME, DATE_Q, TIME_Q, INFO, OPT = range(5)
TIPS = [
    "Выключайте свет и электроприборы, когда они не используются",
    "Рационально используйте энергоресурсы",
    "Предпочитайте упаковки многоразового использования",
    "Используйте многоразовые пакеты",
    "Потребляйте меньше продуктов животного происхождения",
    "Сортируйте отходы",
    "Выбирайте экологически чистые виды транспорта",
    "Поддерживайте местных проихводителей - покупайте продукты у месиных фермеров",
    "Рассказывайте друзьями и близким о проблеме глобального потепления!",
    "Поддерживайте организации , работающие над решением проблемы изменения климата, учавствуйте в акциях и инициативах"
]

# Инициализация баз данных
conn = sqlite3.connect('users.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        hour INTEGER,
        minute INTEGER,
        timezone TEXT
    )
''')
conn.commit()

# ===== ФУНКЦИИ ДЛЯ НАПОМИНАНИЙ =====
def init_json_file():
    default_data = {"напоминания": {}}
    if not os.path.exists("reminder.json"):
        with open("reminder.json", "w", encoding='utf-8') as file:
            json.dump(default_data, file, ensure_ascii=False, indent=4)

def json_editor(user_id, key, value):
    init_json_file()
    user_id = str(user_id)
    
    with open("reminder.json", "r", encoding='utf-8') as file:
        try:
            data = json.load(file)
        except json.JSONDecodeError:
            data = {"напоминания": {}}
    
    if "напоминания" not in data:
        data["напоминания"] = {}
    
    if user_id not in data["напоминания"]:
        data["напоминания"][user_id] = {"часовой_пояс": 0, "напоминания": []}
    
    if key == "название":
        data["напоминания"][user_id]["напоминания"].insert(0, {})
    
    data["напоминания"][user_id]["напоминания"][0][key] = value
    
    with open("reminder.json", "w", encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

def json_getter(user_id):
    init_json_file()
    user_id = str(user_id)
    
    with open("reminder.json", "r", encoding='utf-8') as file:
        data = json.load(file)
        
        if "напоминания" not in data or user_id not in data["напоминания"]:
            raise ValueError("Данные пользователя не найдены")
        
        if not data["напоминания"][user_id]["напоминания"]:
            raise ValueError("Нет активных напоминаний")
        
        reminder = data["напоминания"][user_id]["напоминания"][0]
        return (
            reminder["название"],
            reminder["дата"],
            reminder["время"],
            reminder["id"]
        )

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
    now = datetime.now()
    
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
    now = datetime.now()
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
        return True, datetime(year, month, day)
    elif action == "PREV_MONTH":
        prev_month = datetime(year, month, 1) - timedelta(days=1)
        query.edit_message_reply_markup(reply_markup=create_calendar(prev_month.year, prev_month.month))
    elif action == "NEXT_MONTH":
        next_month = datetime(year, month, 28) + timedelta(days=4)
        query.edit_message_reply_markup(reply_markup=create_calendar(next_month.year, next_month.month))
    
    return False, None

# ===== ОСНОВНЫЕ ФУНКЦИИ ЭКО-БОТА =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🍵 Привет. Я EcoHelper🕊️, твой персональный эко-помощник. "
        "Тут ты можешь узнать о глобальном потеплении и решении этой проблемы. "
        "Каждый день я буду присылать тебе простые советы. "
        "Хочешь узнать больше о глобальном потеплении? нажми команду /global_warming\n\n"
        "Также я могу помочь с напоминаниями - используй /reminder"
    )

async def vibrat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Выбрать часовой пояс", callback_data="set_timezone")]
    ]
    await update.message.reply_text(
        "Сначала выбери свой часовой пояс:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECTING_TIMEZONE

async def set_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    timezones = [
        ["Москва (UTC+3)", "Europe/Moscow"],
        ["Лондон (UTC+1)", "Europe/London"],
        ["Нью-Йорк (UTC-4)", "America/New_York"],
        ["Токио (UTC+9)", "Asia/Tokyo"]
    ]
    
    keyboard = []
    for tz in timezones:
        keyboard.append([InlineKeyboardButton(tz[0], callback_data=f"tz_{tz[1]}")])
    
    await query.edit_message_text(
        "Выбери свой часовой пояс:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECTING_TIME

async def handle_timezone_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    timezone = query.data.split("_")[1]
    context.user_data['timezone'] = timezone
    
    keyboard = [
        [
            InlineKeyboardButton("08:00", callback_data="8_0"),
            InlineKeyboardButton("12:00", callback_data="12_0"),
            InlineKeyboardButton("18:00", callback_data="18_0"),
        ],
        [InlineKeyboardButton("Другое время", callback_data="custom")]
    ]
    await query.edit_message_text(
        "Теперь выбери время для напоминания:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECTING_TIME

async def handle_time_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "custom":
        await query.edit_message_text("Введи время в формате ЧЧ:ММ (например, 09:30)")
        return SELECTING_TIME
    else:
        hour, minute = map(int, query.data.split("_"))
        timezone = context.user_data.get('timezone', 'Europe/Moscow')
        save_user_time(query.from_user.id, hour, minute, timezone)
        await query.edit_message_text(
            f"✅ Отлично! Буду присылать советы в {hour:02d}:{minute:02d} по часовому поясу {timezone}."
        )
        await schedule_daily_tip(context, query.from_user.id, hour, minute, timezone)
        return ConversationHandler.END

async def handle_custom_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        time_str = update.message.text
        hour, minute = map(int, time_str.split(":"))
        if 0 <= hour < 24 and 0 <= minute < 60:
            timezone = context.user_data.get('timezone', 'Europe/Moscow')
            save_user_time(update.message.from_user.id, hour, minute, timezone)
            await update.message.reply_text(
                f"✅ Отлично! Буду присылать советы в {hour:02d}:{minute:02d} по часовому поясу {timezone}."
            )
            await schedule_daily_tip(context, update.message.from_user.id, hour, minute, timezone)
            return ConversationHandler.END
        else:
            await update.message.reply_text("⛔ Некорректное время. Попробуй снова.")
            return SELECTING_TIME
    except ValueError:
        await update.message.reply_text("⛔ Неверный формат. Введи время как ЧЧ:ММ (например, 09:30).")
        return SELECTING_TIME

def save_user_time(user_id: int, hour: int, minute: int, timezone: str):
    cursor.execute(
        "INSERT OR REPLACE INTO users (user_id, hour, minute, timezone) VALUES (?, ?, ?, ?)",
        (user_id, hour, minute, timezone)
    )
    conn.commit()

async def schedule_daily_tip(context: ContextTypes.DEFAULT_TYPE, user_id: int, hour: int, minute: int, timezone: str):
    try:
        # Удаляем старые задачи
        current_jobs = context.job_queue.get_jobs_by_name(str(user_id))
        for job in current_jobs:
            job.schedule_removal()

        # Проверяем часовой пояс
        try:
            tz = pytz.timezone(timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            tz = pytz.timezone('Europe/Moscow')
            logger.warning(f"Unknown timezone {timezone} for user {user_id}, using default")

        # Добавляем новую задачу
        context.job_queue.run_daily(
            send_daily_tip,
            time(hour, minute, tzinfo=tz),
            chat_id=user_id,
            name=str(user_id),
            data={"user_id": user_id}
        )
        logger.info(f"Scheduled daily tip for user {user_id} at {hour:02d}:{minute:02d} {timezone}")
    except Exception as e:
        logger.error(f"Error scheduling tip for user {user_id}: {e}")

async def send_daily_tip(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    user_id = job.data["user_id"]
    
    cursor.execute("SELECT hour, minute, timezone FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if row:
        hour, minute, timezone = row
        day_index = datetime.now(pytz.timezone(timezone)).timetuple().tm_yday
        tip = TIPS[day_index % len(TIPS)]
        
        try:
            await context.bot.send_message(chat_id=user_id, text=tip)
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения пользователю {user_id}: {e}")

# ===== ФУНКЦИИ ДЛЯ НАПОМИНАНИЙ =====
async def reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📝 Введите название события для напоминания:",
        parse_mode="Markdown"
    )
    return NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text
    user_id = update.message.chat_id
    json_editor(user_id, "название", name)
    
    await update.message.reply_text(
        f"📅 Выберите дату для {name}:",
        reply_markup=create_calendar(), 
        parse_mode="Markdown"
    )
    return DATE_Q

async def select_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    selected, date = process_calendar_selection(update, context)
    if selected:
        json_editor(query.from_user.id, "дата", date.strftime("%d/%m/%Y"))
        await query.edit_message_text(
            text=f"Вы выбрали: {date.strftime('%d/%m/%Y')}",
            reply_markup=None
        )
        
        tz = get_user_timezone(query.from_user.id)
        await context.bot.send_message(
            chat_id=query.from_user.id, 
            text="⏰ Выберите время:",
            parse_mode="Markdown", 
            reply_markup=create_clock(tz_offset=tz)
        )
        return TIME_Q
    return DATE_Q

async def select_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    selected, time = process_clock_selection(update, context)
    if selected:
        user_id = str(query.from_user.id)
        r_id = random.randint(0, 100000)
        formatted_time = f"{time[0]}:{time[1]:02d} {time[2]}"
        
        json_editor(user_id, "время", formatted_time)
        json_editor(user_id, "id", r_id)

        await query.edit_message_text(
            text=f"Вы выбрали: {formatted_time}",
            reply_markup=None
        )
        
        reply_keyboard = [["Да", "Нет"]]
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text="Добавить дополнительную информацию?",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
        )
        return INFO
    return TIME_Q

async def get_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "Да":
        await update.message.reply_text("Введите дополнительную информацию:")
        return OPT
    else:
        return await save_reminder(update, context)

async def get_additional_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info = update.message.text
    return await save_reminder(update, context, info)

async def save_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE, info=None):
    user_id = str(update.message.chat_id)
    try:
        name, date, time, r_id = json_getter(user_id)
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text("Произошла ошибка. Попробуйте снова.")
        return ConversationHandler.END
    
    if info:
        json_editor(user_id, "доп_инфо", info)
    
    reply_keyboard = [["/start", "/list"]]
    await update.message.reply_text(
        f"✅ Напоминание сохранено!\n\nСобытие: {name}\nДата: {date}\nВремя: {time}",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.chat_id)
    with open("reminder.json", "r+", encoding='utf-8') as file:
        data = json.load(file)
        if "напоминания" in data and user_id in data["напоминания"]:
            if data["напоминания"][user_id]["напоминания"]:
                data["напоминания"][user_id]["напоминания"].pop(0)
                file.seek(0)
                json.dump(data, file, ensure_ascii=False, indent=4)
                file.truncate()
    
    await update.message.reply_text(
        '❌ Создание напоминания отменено.',
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

# ===== ИНФОРМАЦИОННЫЕ КОМАНДЫ =====
async def global_warming(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌍 Глобальное потепление — повышение средней температуры климатической системы Земли. "
        "Узнать больше: /what"
    )

async def what(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔥 Последствия изменения климата:\n"
        "- Сильные засухи и нехватка воды\n"
        "- Повышение уровня моря\n"
        "- Катастрофические погодные явления\n"
        "- Сокращение биоразнообразия\n"
        "Причины: /why"
    )

async def why(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📈 Основные причины глобального потепления:\n"
        "1. Выбросы парниковых газов (CO2, метан)\n"
        "2. Сжигание ископаемого топлива\n"
        "3. Вырубка лесов\n"
        "4. Промышленные процессы\n"
        "5. Свалки мусора (выделяют метан)\n\n"
        "💡 Каждый может помочь: начните с малого - используйте /vibrat"
    )

# ===== ОСНОВНАЯ ФУНКЦИЯ =====
def main():
    try:
        # Создаем Application
        application = Application.builder().token("8158309846:AAEmFzC3vLLkb027O-SiGH0xQkOoJc59qpc").build()

        # Обработчик выбора времени и часового пояса для эко-советов
        eco_conv_handler = ConversationHandler(
            entry_points=[CommandHandler('vibrat', vibrat)],
            states={
                SELECTING_TIMEZONE: [CallbackQueryHandler(set_timezone)],
                SELECTING_TIME: [
                    CallbackQueryHandler(handle_timezone_selection, pattern="^tz_"),
                    CallbackQueryHandler(handle_time_selection),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_time)
                ]
            },
            fallbacks=[]
        )

        # Обработчик для напоминаний
        reminder_conv_handler = ConversationHandler(
            entry_points=[CommandHandler('reminder', reminder)],
            states={
                NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
                DATE_Q: [CallbackQueryHandler(select_date)],
                TIME_Q: [CallbackQueryHandler(select_time)],
                INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_info)],
                OPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_additional_info)],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
        )

        # Регистрация обработчиков команд
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("globalwarming", global_warming))
        application.add_handler(CommandHandler("what", what))
        application.add_handler(CommandHandler("why", why))
        application.add_handler(eco_conv_handler)
        application.add_handler(reminder_conv_handler)

        # Восстановление расписания из БД
        cursor.execute("SELECT user_id, hour, minute, timezone FROM users")
        for row in cursor.fetchall():
            user_id, hour, minute, timezone = row
            try:
                tz = pytz.timezone(timezone)
                application.job_queue.run_daily(
                    send_daily_tip,
                    time(hour, minute, tzinfo=tz),
                    chat_id=user_id,
                    name=str(user_id),
                    data={"user_id": user_id}
                )
                logger.info(f"Restored schedule for user {user_id} at {hour:02d}:{minute:02d} {timezone}")
            except Exception as e:
                logger.error(f"Error restoring schedule for user {user_id}: {e}")

        # Запуск бота
        logger.info("Starting bot...")
        application.run_polling()
        logger.info("Bot stopped")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    main()