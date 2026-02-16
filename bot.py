from datetime import datetime
from zoneinfo import ZoneInfo

# Timezone for Bishkek (UTC+6)
BISHKEK_TZ = ZoneInfo("Asia/Bishkek")

print("Server time (UTC):", datetime.now())
print("Bishkek time:", datetime.now(BISHKEK_TZ))



from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
    CallbackQueryHandler
)
import logging
from config import BOT_TOKEN
from database import (
    add_lesson,
    remove_lesson,
    get_user_lessons,
    get_week_schedule,
    update_lesson_reminder,
    seed_user_lessons_from_existing,
    get_all_lessons,
    update_lesson_last_notified
)
import re
from datetime import datetime, timedelta

# Conversation states
CHOOSING_ACTION, WAITING_LESSON_INPUT, ASKING_REMINDER, WAITING_NOTIFICATION, WAITING_REMOVE_INPUT, WAITING_REMINDER_LESSON_INPUT, WAITING_REMINDER_CHOICE, WAITING_COURSE_NAME, WAITING_DAY_SELECTION, WAITING_TIME_INPUT, WAITING_REMOVE_DAY_SELECTION, WAITING_REMOVE_LESSON_SELECTION = range(12)

# Bot commands help text
HELP_TEXT = """<b>📚 Available Commands:</b>

/start - Show bot information and available commands
/schedule - View your weekly schedule with all lessons
/lessons_today - View today's lessons
/lessons_tomorrow - View tomorrow's lessons
/add_lesson - Add a new lesson to your schedule
/remove_lesson - Remove a lesson from your schedule
/turn_on_off - Turn on/off reminder for a specific lesson
/help - Show this help message

<i>Note: Telegram commands can't contain spaces.</i>"""

START_TEXT = """<b>👋 Welcome to Lesson Reminder Bot!</b>

I'm here to help you manage and remember your lessons! 📖

<b>Here's what I can do:</b>
• 📅 Store and display your weekly schedule
• ⏰ Send you reminders before each lesson
• ✏️ Add new lessons easily
• 🗑️ Remove lessons you no longer need

Use /help to see all available commands, or try /add_lesson to get started!"""

def validate_time_format(time_str):
    """Validate time format (HH:MM in 24-hour format)"""
    pattern = r'^([0-1][0-9]|2[0-3]):[0-5][0-9]$'
    return re.match(pattern, time_str) is not None

def validate_day(day):
    """Validate day of week"""
    valid_days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    return day.lower() in valid_days

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_id = update.effective_user.id
    lessons = ensure_user_schedule(user_id)
    if lessons:
        await update.message.reply_text(
            START_TEXT
            + "\n\n"
            + HELP_TEXT
            + "\n\n"
            + "Use /schedule any time to view your saved lessons.",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            START_TEXT
            + "\n\n"
            + HELP_TEXT
            + "\n\n"
            + "📭 You don't have any lessons scheduled yet!\n\nUse /add_lesson to add your first lesson.",
            parse_mode="HTML"
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    await update.message.reply_text(HELP_TEXT, parse_mode="HTML")

def build_schedule_text(lessons):
    """Return formatted schedule text grouped by day"""
    from collections import defaultdict
    lessons_by_day = defaultdict(list)
    for lesson in lessons:
        lessons_by_day[lesson['day'].lower()].append(lesson)

    schedule_text = "📅 <b>Your Weekly Schedule:</b>\n\n"
    days_order = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for day in days_order:
        if day in lessons_by_day:
            schedule_text += f"<b>📌 {day.capitalize()}:</b>\n"
            for lesson in lessons_by_day[day]:
                schedule_text += f"   • {lesson['time']} - {lesson['subject']} <i>(⏰ {lesson['notification_time']})</i>\n"
            schedule_text += "\n"
    return schedule_text

def ensure_user_schedule(user_id):
    """Ensure user has a schedule; seed from existing users if empty."""
    lessons = get_week_schedule(user_id)
    if lessons:
        return lessons
    # Try to seed from another user
    seeded = seed_user_lessons_from_existing(user_id)
    if seeded:
        return get_week_schedule(user_id)
    return lessons

def parse_notification_minutes(notification_time):
    """Convert notification time string to minutes"""
    mapping = {
        "5 min": 5,
        "15 min": 15,
        "30 min": 30,
        "1 hour": 60
    }
    return mapping.get(notification_time)

def get_next_lesson_datetime(day, time_str, now):
    """Get the next occurrence datetime for a lesson day/time"""
    days_map = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6
    }
    target_weekday = days_map.get(day.lower())
    if target_weekday is None:
        return None

    hour, minute = map(int, time_str.split(':'))
    lesson_time_today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    days_ahead = (target_weekday - now.weekday()) % 7
    if days_ahead == 0 and lesson_time_today < now:
        days_ahead = 7

    lesson_date = (now + timedelta(days=days_ahead)).date()
    # Return timezone-aware datetime
    naive_dt = datetime.combine(lesson_date, lesson_time_today.time())
    return naive_dt.replace(tzinfo=now.tzinfo) if now.tzinfo else naive_dt

async def check_and_send_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Check upcoming lessons and send reminders"""
    now = datetime.now(BISHKEK_TZ)  # Use Bishkek timezone
    all_lessons = get_all_lessons()
    if not all_lessons:
        return

    for user_id_str, lessons in all_lessons.items():
        try:
            user_id = int(user_id_str)
        except ValueError:
            continue

        for lesson in lessons:
            notification_time = lesson.get("notification_time")
            if not notification_time or notification_time == "No reminder":
                continue

            minutes_before = parse_notification_minutes(notification_time)
            if minutes_before is None:
                continue

            lesson_dt = get_next_lesson_datetime(lesson.get("day", ""), lesson.get("time", ""), now)
            if lesson_dt is None:
                continue

            reminder_dt = lesson_dt - timedelta(minutes=minutes_before)
            window_end = reminder_dt + timedelta(seconds=60)

            last_notified = lesson.get("last_notified")
            if last_notified:
                try:
                    last_notified_dt = datetime.fromisoformat(last_notified)
                    # Make timezone-aware if naive
                    if last_notified_dt.tzinfo is None:
                        last_notified_dt = last_notified_dt.replace(tzinfo=BISHKEK_TZ)
                    if last_notified_dt == reminder_dt:
                        continue
                except ValueError:
                    pass

            if reminder_dt <= now < window_end:
                message = (
                    f"⏰ Reminder: {lesson['subject']}\n"
                    f"📅 {lesson['day'].capitalize()} at {lesson['time']}\n"
                    f"(in {notification_time})"
                )
                await context.bot.send_message(chat_id=user_id, text=message)
                update_lesson_last_notified(
                    user_id,
                    lesson["day"],
                    lesson["time"],
                    lesson["subject"],
                    reminder_dt.isoformat()
                )

async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /schedule command"""
    user_id = update.effective_user.id
    lessons = ensure_user_schedule(user_id)
    
    if not lessons:
        await update.message.reply_text("📭 You don't have any lessons scheduled yet!\n\nUse /add_lesson to add your first lesson.")
        return

    schedule_text = build_schedule_text(lessons)
    await update.message.reply_text(schedule_text, parse_mode="HTML")

async def add_lesson_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the add lesson conversation"""
    await update.message.reply_text(
        "📝 <b>Add New Lesson</b>\n\n"
        "Please enter the <b>course name</b>:\n\n"
        "Example: <code>Calculus 2</code>",
        parse_mode="HTML"
    )
    return WAITING_COURSE_NAME

async def course_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle course name input and show day selection buttons"""
    course_name = update.message.text.strip()
    
    if not course_name:
        await update.message.reply_text(
            "❌ Course name cannot be empty! Please enter a valid course name:",
            parse_mode="HTML"
        )
        return WAITING_COURSE_NAME
    
    # Store course name in context
    context.user_data['new_course_name'] = course_name
    
    # Show day selection buttons
    keyboard = [
        [InlineKeyboardButton("Monday", callback_data="day_monday"),
         InlineKeyboardButton("Tuesday", callback_data="day_tuesday")],
        [InlineKeyboardButton("Wednesday", callback_data="day_wednesday"),
         InlineKeyboardButton("Thursday", callback_data="day_thursday")],
        [InlineKeyboardButton("Friday", callback_data="day_friday"),
         InlineKeyboardButton("Saturday", callback_data="day_saturday")],
        [InlineKeyboardButton("Sunday", callback_data="day_sunday")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📚 Course: <b>{course_name}</b>\n\n"
        "📅 Select the day:",
        parse_mode="HTML",
        reply_markup=reply_markup
    )
    
    return WAITING_DAY_SELECTION

async def day_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle day selection and ask for time input"""
    query = update.callback_query
    await query.answer()
    
    # Extract day from callback data
    day = query.data.replace("day_", "").capitalize()
    context.user_data['new_course_day'] = day
    
    course_name = context.user_data.get('new_course_name', 'Unknown')
    
    await query.edit_message_text(
        f"📚 Course: <b>{course_name}</b>\n"
        f"📅 Day: <b>{day}</b>\n\n"
        "🕐 Enter the time:\n\n"
        "Format: <code>##:##</code>\n"
        "Example: <code>09:30</code> or <code>14:00</code>",
        parse_mode="HTML"
    )
    
    return WAITING_TIME_INPUT

async def time_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle time input and ask about reminder"""
    time_str = update.message.text.strip()
    
    # Validate time format
    if not validate_time_format(time_str):
        await update.message.reply_text(
            "❌ Invalid time format!\n\n"
            "Please use format: <code>##:##</code>\n"
            "Example: <code>09:30</code> or <code>14:00</code>",
            parse_mode="HTML"
        )
        return WAITING_TIME_INPUT
    
    course_name = context.user_data.get('new_course_name', 'Unknown')
    day = context.user_data.get('new_course_day', 'Unknown')
    
    # Store lesson data
    context.user_data['new_lessons'] = [{
        'day': day,
        'time': time_str,
        'subject': course_name
    }]
    
    # Ask about reminder
    keyboard = [
        [InlineKeyboardButton("✅ Yes, set reminder", callback_data="reminder_yes")],
        [InlineKeyboardButton("❌ No reminder", callback_data="reminder_no")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"✅ <b>Lesson Summary:</b>\n\n"
        f"📚 Course: <b>{course_name}</b>\n"
        f"📅 Day: <b>{day}</b>\n"
        f"🕐 Time: <b>{time_str}</b>\n\n"
        "⏰ Do you want to set a reminder?",
        parse_mode="HTML",
        reply_markup=reply_markup
    )
    
    return ASKING_REMINDER

# Old button-based time selection removed - now using text input

async def reminder_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle reminder choice (yes/no)"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "reminder_yes":
        # Show notification time options
        keyboard = [
            [InlineKeyboardButton("5 min", callback_data="notif_5")],
            [InlineKeyboardButton("15 min", callback_data="notif_15")],
            [InlineKeyboardButton("30 min", callback_data="notif_30")],
            [InlineKeyboardButton("1 hour", callback_data="notif_60")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "⏰ When would you like to be reminded before each lesson?",
            parse_mode="HTML",
            reply_markup=reply_markup
        )
        return WAITING_NOTIFICATION
    
    elif query.data == "reminder_no":
        # Add lessons without reminder
        user_id = update.effective_user.id
        lessons_data = context.user_data.get('new_lessons', [])
        
        if not lessons_data:
            await query.edit_message_text("❌ Error: No lesson data found!")
            context.user_data.clear()
            return ConversationHandler.END
        
        # Add all lessons without notification time
        for lesson in lessons_data:
            add_lesson(
                user_id,
                lesson['day'],
                lesson['time'],
                lesson['subject'],
                "No reminder"
            )
        
        # Create success message
        if len(lessons_data) == 1:
            lesson = lessons_data[0]
            success_msg = (
                f"✅ <b>Lesson Added Successfully!</b>\n\n"
                f"📚 Subject: {lesson['subject']}\n"
                f"📅 Day: {lesson['day']}\n"
                f"🕐 Time: {lesson['time']}\n"
                f"⏰ Reminder: None\n\n"
                "Use /schedule to view all your lessons or /add_lesson to add another!"
            )
        else:
            success_msg = f"✅ <b>{len(lessons_data)} Lessons Added Successfully!</b>\n\n"
            for lesson in lessons_data:
                success_msg += f"• <b>{lesson['subject']}</b> on <b>{lesson['day']}</b> at <b>{lesson['time']}</b>\n"
            success_msg += f"\n⏰ Reminders: None\n\n"
            success_msg += "Use /schedule to view all your lessons or /add_lesson to add more!"
        
        await query.edit_message_text(success_msg, parse_mode="HTML")
        
        # Clear user data
        context.user_data.clear()
        return ConversationHandler.END

async def notification_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle notification time selection"""
    query = update.callback_query
    await query.answer()
    
    notif_mapping = {
        "notif_5": "5 min",
        "notif_15": "15 min",
        "notif_30": "30 min",
        "notif_60": "1 hour"
    }
    
    notification_time = notif_mapping.get(query.data, "5 min")
    
    # Add lesson(s) to database
    user_id = update.effective_user.id
    lessons_data = context.user_data.get('new_lessons', [])
    
    if not lessons_data:
        await query.edit_message_text("❌ Error: No lesson data found!")
        context.user_data.clear()
        return ConversationHandler.END
    
    # Add all lessons with the same notification time
    for lesson in lessons_data:
        add_lesson(
            user_id,
            lesson['day'],
            lesson['time'],
            lesson['subject'],
            notification_time
        )
    
    # Create success message
    if len(lessons_data) == 1:
        lesson = lessons_data[0]
        success_msg = (
            f"✅ <b>Lesson Added Successfully!</b>\n\n"
            f"📚 Subject: {lesson['subject']}\n"
            f"📅 Day: {lesson['day']}\n"
            f"🕐 Time: {lesson['time']}\n"
            f"⏰ Reminder: {notification_time} before\n\n"
            "Use /schedule to view all your lessons or /add_lesson to add another!"
        )
    else:
        success_msg = f"✅ <b>{len(lessons_data)} Lessons Added Successfully!</b>\n\n"
        for lesson in lessons_data:
            success_msg += f"• <b>{lesson['subject']}</b> on <b>{lesson['day']}</b> at <b>{lesson['time']}</b>\n"
        success_msg += f"\n⏰ All reminders set to: {notification_time} before\n\n"
        success_msg += "Use /schedule to view all your lessons or /add_lesson to add more!"
    
    await query.edit_message_text(success_msg, parse_mode="HTML")
    
    # Clear user data
    context.user_data.clear()
    return ConversationHandler.END

async def remove_lesson_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the remove lesson conversation"""
    user_id = update.effective_user.id
    lessons = get_user_lessons(user_id)
    
    if not lessons:
        await update.message.reply_text("📭 You don't have any lessons to remove!")
        return ConversationHandler.END
    
    # Store lessons in context for later reference
    context.user_data['remove_lessons'] = lessons
    
    # Show day selection buttons
    keyboard = [
        [InlineKeyboardButton("Monday", callback_data="rmday_monday"),
         InlineKeyboardButton("Tuesday", callback_data="rmday_tuesday")],
        [InlineKeyboardButton("Wednesday", callback_data="rmday_wednesday"),
         InlineKeyboardButton("Thursday", callback_data="rmday_thursday")],
        [InlineKeyboardButton("Friday", callback_data="rmday_friday"),
         InlineKeyboardButton("Saturday", callback_data="rmday_saturday")],
        [InlineKeyboardButton("Sunday", callback_data="rmday_sunday")],
        [InlineKeyboardButton("❌ Cancel", callback_data="rmday_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🗑️ <b>Remove Lesson</b>\n\n"
        "📅 Select the day:",
        parse_mode="HTML",
        reply_markup=reply_markup
    )
    return WAITING_REMOVE_DAY_SELECTION

async def remove_day_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle day selection for remove lesson"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "rmday_cancel":
        await query.edit_message_text("❌ Operation cancelled.")
        context.user_data.clear()
        return ConversationHandler.END
    
    # Extract day from callback data
    day = query.data.replace("rmday_", "").capitalize()
    context.user_data['remove_day'] = day
    
    # Get lessons for this day
    lessons = context.user_data.get('remove_lessons', [])
    day_lessons = [l for l in lessons if l['day'].lower() == day.lower()]
    
    if not day_lessons:
        # No lessons on this day - show message and let user pick another day
        keyboard = [
            [InlineKeyboardButton("Monday", callback_data="rmday_monday"),
             InlineKeyboardButton("Tuesday", callback_data="rmday_tuesday")],
            [InlineKeyboardButton("Wednesday", callback_data="rmday_wednesday"),
             InlineKeyboardButton("Thursday", callback_data="rmday_thursday")],
            [InlineKeyboardButton("Friday", callback_data="rmday_friday"),
             InlineKeyboardButton("Saturday", callback_data="rmday_saturday")],
            [InlineKeyboardButton("Sunday", callback_data="rmday_sunday")],
            [InlineKeyboardButton("❌ Cancel", callback_data="rmday_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"📭 <b>No lessons on {day}!</b>\n\n"
            "📅 Select another day:",
            parse_mode="HTML",
            reply_markup=reply_markup
        )
        return WAITING_REMOVE_DAY_SELECTION
    
    # Sort lessons by time
    day_lessons_sorted = sorted(day_lessons, key=lambda x: x['time'])
    context.user_data['remove_day_lessons'] = day_lessons_sorted
    
    # Create buttons for each lesson on this day
    keyboard = []
    for i, lesson in enumerate(day_lessons_sorted):
        button_text = f"{lesson['time']} - {lesson['subject']}"
        callback_data = f"rmlesson_{i}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    # Add back and cancel buttons
    keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="rmlesson_back"),
                     InlineKeyboardButton("❌ Cancel", callback_data="rmlesson_cancel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"🗑️ <b>Remove Lesson</b>\n\n"
        f"📅 Day: <b>{day}</b>\n\n"
        "Select the lesson to remove:",
        parse_mode="HTML",
        reply_markup=reply_markup
    )
    return WAITING_REMOVE_LESSON_SELECTION

async def remove_lesson_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle lesson selection for removal"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "rmlesson_cancel":
        await query.edit_message_text("❌ Operation cancelled.")
        context.user_data.clear()
        return ConversationHandler.END
    
    if query.data == "rmlesson_back":
        # Go back to day selection
        keyboard = [
            [InlineKeyboardButton("Monday", callback_data="rmday_monday"),
             InlineKeyboardButton("Tuesday", callback_data="rmday_tuesday")],
            [InlineKeyboardButton("Wednesday", callback_data="rmday_wednesday"),
             InlineKeyboardButton("Thursday", callback_data="rmday_thursday")],
            [InlineKeyboardButton("Friday", callback_data="rmday_friday"),
             InlineKeyboardButton("Saturday", callback_data="rmday_saturday")],
            [InlineKeyboardButton("Sunday", callback_data="rmday_sunday")],
            [InlineKeyboardButton("❌ Cancel", callback_data="rmday_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🗑️ <b>Remove Lesson</b>\n\n"
            "📅 Select the day:",
            parse_mode="HTML",
            reply_markup=reply_markup
        )
        return WAITING_REMOVE_DAY_SELECTION
    
    # Extract lesson index from callback data
    try:
        lesson_index = int(query.data.replace("rmlesson_", ""))
    except ValueError:
        await query.edit_message_text("❌ Error: Invalid selection.")
        context.user_data.clear()
        return ConversationHandler.END
    
    day_lessons = context.user_data.get('remove_day_lessons', [])
    
    if lesson_index < 0 or lesson_index >= len(day_lessons):
        await query.edit_message_text("❌ Error: Lesson not found.")
        context.user_data.clear()
        return ConversationHandler.END
    
    lesson = day_lessons[lesson_index]
    user_id = update.effective_user.id
    
    # Remove the lesson
    success = remove_lesson(user_id, lesson['day'], lesson['time'], lesson['subject'])
    
    if success:
        await query.edit_message_text(
            f"✅ <b>Lesson Removed Successfully!</b>\n\n"
            f"🗑️ Removed: <b>{lesson['subject']}</b>\n"
            f"📅 Day: <b>{lesson['day']}</b>\n"
            f"🕐 Time: <b>{lesson['time']}</b>\n\n"
            "Use /schedule to view your updated schedule!",
            parse_mode="HTML"
        )
    else:
        await query.edit_message_text(
            "❌ Failed to remove lesson. Please try again.",
            parse_mode="HTML"
        )
    
    context.user_data.clear()
    return ConversationHandler.END

# Old remove_input_handler removed - now using button-based flow

async def turn_on_off_reminder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the turn on/off reminder conversation"""
    user_id = update.effective_user.id
    lessons = get_user_lessons(user_id)
    
    if not lessons:
        await update.message.reply_text("📭 You don't have any lessons to modify!")
        return ConversationHandler.END
    
    await update.message.reply_text(
        "⏰ <b>Turn On/Off Reminder</b>\n\n"
        "Please enter the lesson details to modify:\n"
        "<code>Day, Time, Subject</code>\n\n"
        "Example: <code>Monday, 14:00, Calculus 2</code>",
        parse_mode="HTML"
    )
    return WAITING_REMINDER_LESSON_INPUT

async def reminder_lesson_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle lesson input for reminder modification"""
    text = update.message.text.strip()
    
    # Parse input
    parts = [p.strip() for p in text.split(',')]
    
    if len(parts) != 3:
        await update.message.reply_text(
            "❌ Invalid format! Please use:\n"
            "<code>Day, Time, Subject</code>\n\n"
            "Example: <code>Monday, 14:00, Calculus 2</code>",
            parse_mode="HTML"
        )
        return WAITING_REMINDER_LESSON_INPUT
    
    day, time_str, subject = parts
    
    # Validate day
    if not validate_day(day):
        await update.message.reply_text(
            "❌ Invalid day! Please use one of:\n"
            "Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday",
            parse_mode="HTML"
        )
        return WAITING_REMINDER_LESSON_INPUT
    
    # Validate time
    if not validate_time_format(time_str):
        await update.message.reply_text(
            "❌ Invalid time format! Please use 24-hour format (HH:MM).\n"
            "Example: <code>14:00</code> for 2 PM",
            parse_mode="HTML"
        )
        return WAITING_REMINDER_LESSON_INPUT
    
    # Check if lesson exists
    user_id = update.effective_user.id
    lessons = get_user_lessons(user_id)
    lesson_found = False
    
    for lesson in lessons:
        if (lesson["day"].lower() == day.lower() and 
            lesson["time"] == time_str and 
            lesson["subject"].lower() == subject.lower()):
            lesson_found = True
            break
    
    if not lesson_found:
        await update.message.reply_text(
            f"❌ Lesson not found!\n\n"
            f"Couldn't find: <b>{subject}</b> on <b>{day}</b> at <b>{time_str}</b>\n\n"
            "Use /schedule to see your current lessons.",
            parse_mode="HTML"
        )
        return WAITING_REMINDER_LESSON_INPUT
    
    # Store lesson info in context
    context.user_data['reminder_lesson'] = {
        'day': day,
        'time': time_str,
        'subject': subject
    }
    
    # Show reminder options
    keyboard = [
        [InlineKeyboardButton("5 min", callback_data="reminder_update_5")],
        [InlineKeyboardButton("15 min", callback_data="reminder_update_15")],
        [InlineKeyboardButton("30 min", callback_data="reminder_update_30")],
        [InlineKeyboardButton("1 hour", callback_data="reminder_update_60")],
        [InlineKeyboardButton("❌ Don't set a reminder", callback_data="reminder_update_none")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"✅ Found lesson: <b>{subject}</b> on <b>{day}</b> at <b>{time_str}</b>\n\n"
        "⏰ Choose reminder time:",
        parse_mode="HTML",
        reply_markup=reply_markup
    )
    
    return WAITING_REMINDER_CHOICE

async def reminder_update_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle reminder update selection"""
    query = update.callback_query
    await query.answer()
    
    notif_mapping = {
        "reminder_update_5": "5 min",
        "reminder_update_15": "15 min",
        "reminder_update_30": "30 min",
        "reminder_update_60": "1 hour",
        "reminder_update_none": "No reminder"
    }
    
    notification_time = notif_mapping.get(query.data, "No reminder")
    
    # Get lesson info from context
    lesson_info = context.user_data.get('reminder_lesson', {})
    
    if not lesson_info:
        await query.edit_message_text("❌ Error: No lesson data found!")
        context.user_data.clear()
        return ConversationHandler.END
    
    # Update the lesson reminder
    user_id = update.effective_user.id
    success = update_lesson_reminder(
        user_id,
        lesson_info['day'],
        lesson_info['time'],
        lesson_info['subject'],
        notification_time
    )
    
    if success:
        await query.edit_message_text(
            f"✅ <b>Reminder Updated Successfully!</b>\n\n"
            f"📚 Subject: {lesson_info['subject']}\n"
            f"📅 Day: {lesson_info['day']}\n"
            f"🕐 Time: {lesson_info['time']}\n"
            f"⏰ New Reminder: {notification_time}\n\n"
            "Use /schedule to view all your lessons!",
            parse_mode="HTML"
        )
    else:
        await query.edit_message_text(
            "❌ Failed to update reminder. Please try again.",
            parse_mode="HTML"
        )
    
    # Clear user data
    context.user_data.clear()
    return ConversationHandler.END

async def lessons_today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /lessons_today command - show today's lessons"""
    user_id = update.effective_user.id
    lessons = ensure_user_schedule(user_id)
    
    if not lessons:
        await update.message.reply_text("📭 You don't have any lessons scheduled yet!\n\nUse /add_lesson to add your first lesson.")
        return
    
    # Get today's day name using Bishkek timezone
    now = datetime.now(BISHKEK_TZ)
    today = now.strftime("%A").lower()
    today_display = now.strftime("%A, %B %d, %Y")
    
    # Filter lessons for today
    today_lessons = [l for l in lessons if l['day'].lower() == today]
    
    if not today_lessons:
        await update.message.reply_text(
            f"📅 <b>{today_display}</b>\n\n"
            "😴 No lessons scheduled for today!\n\n"
            "Use /schedule to view your full weekly schedule.",
            parse_mode="HTML"
        )
        return
    
    # Sort by time
    today_lessons.sort(key=lambda x: x['time'])
    
    # Build response
    response = f"📅 <b>Today's Lessons ({today_display})</b>\n\n"
    
    for i, lesson in enumerate(today_lessons, 1):
        reminder_info = lesson.get('notification_time', 'No reminder')
        if reminder_info == "No reminder":
            reminder_text = "🔕 No reminder"
        else:
            reminder_text = f"🔔 Reminder: {reminder_info} before"
        
        response += (
            f"<b>{i}. {lesson['subject']}</b>\n"
            f"   🕐 Time: {lesson['time']}\n"
            f"   {reminder_text}\n\n"
        )
    
    response += f"📚 Total: {len(today_lessons)} lesson(s) today"
    
    await update.message.reply_text(response, parse_mode="HTML")

async def lessons_tomorrow_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /lessons_tomorrow command - show tomorrow's lessons"""
    user_id = update.effective_user.id
    lessons = ensure_user_schedule(user_id)
    
    if not lessons:
        await update.message.reply_text("📭 You don't have any lessons scheduled yet!\n\nUse /add_lesson to add your first lesson.")
        return
    
    # Get tomorrow's day name using Bishkek timezone
    now = datetime.now(BISHKEK_TZ)
    tomorrow = now + timedelta(days=1)
    tomorrow_day = tomorrow.strftime("%A").lower()
    tomorrow_display = tomorrow.strftime("%A, %B %d, %Y")
    
    # Filter lessons for tomorrow
    tomorrow_lessons = [l for l in lessons if l['day'].lower() == tomorrow_day]
    
    if not tomorrow_lessons:
        await update.message.reply_text(
            f"📅 <b>{tomorrow_display}</b>\n\n"
            "😴 No lessons scheduled for tomorrow!\n\n"
            "Use /schedule to view your full weekly schedule.",
            parse_mode="HTML"
        )
        return
    
    # Sort by time
    tomorrow_lessons.sort(key=lambda x: x['time'])
    
    # Build response
    response = f"📅 <b>Tomorrow's Lessons ({tomorrow_display})</b>\n\n"
    
    for i, lesson in enumerate(tomorrow_lessons, 1):
        reminder_info = lesson.get('notification_time', 'No reminder')
        if reminder_info == "No reminder":
            reminder_text = "🔕 No reminder"
        else:
            reminder_text = f"🔔 Reminder: {reminder_info} before"
        
        response += (
            f"<b>{i}. {lesson['subject']}</b>\n"
            f"   🕐 Time: {lesson['time']}\n"
            f"   {reminder_text}\n\n"
        )
    
    response += f"📚 Total: {len(tomorrow_lessons)} lesson(s) tomorrow"
    
    await update.message.reply_text(response, parse_mode="HTML")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel conversation"""
    await update.message.reply_text("❌ Operation cancelled.")
    context.user_data.clear()
    return ConversationHandler.END

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle unknown commands and suggest valid ones"""
    await update.message.reply_text(
        "❓ I don't recognize that command.\n\n"
        "Try one of: /start, /help, /schedule, /lessons_today, /lessons_tomorrow, /add_lesson, /remove_lesson, /turn_on_off.\n\n"
        "Note: Commands must match exactly and contain no spaces.",
        parse_mode="HTML"
    )

async def unknown_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle random text messages"""
    await update.message.reply_text(
        "❌ Invalid input!\n\n"
        "Please use one of the available commands:\n"
        "/start - Show bot info\n"
        "/help - Show all commands\n"
        "/schedule - View weekly schedule\n"
        "/add_lesson - Add a lesson\n"
        "/remove_lesson - Remove a lesson",
        parse_mode="HTML"
    )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Log the error and send a friendly message"""
    logging.exception("Unhandled exception during update processing", exc_info=context.error)
    try:
        if isinstance(update, Update):
            target = update.effective_message or update.callback_query
            if target:
                await target.reply_text("⚠️ Sorry, something went wrong. Please try again.")
    except Exception:
        pass

def main():
    """Start the bot"""
    # Setup logging
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    # Create application
    async def post_init(application: Application):
        await application.bot.set_my_commands([
            BotCommand("start", "Show bot information"),
            BotCommand("help", "Show help message"),
            BotCommand("schedule", "View your weekly schedule"),
            BotCommand("lessons_today", "View today's lessons"),
            BotCommand("lessons_tomorrow", "View tomorrow's lessons"),
            BotCommand("add_lesson", "Add a new lesson"),
            BotCommand("remove_lesson", "Remove a lesson"),
            BotCommand("turn_on_off", "Turn on/off a reminder")
        ])

    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("schedule", schedule_command))
    application.add_handler(CommandHandler("lessons_today", lessons_today_command))
    application.add_handler(CommandHandler("lessons_tomorrow", lessons_tomorrow_command))
    
    # Add conversation handler for adding lessons
    add_lesson_conv = ConversationHandler(
        entry_points=[CommandHandler("add_lesson", add_lesson_command)],
        states={
            WAITING_COURSE_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, course_name_handler),
                CommandHandler("cancel", cancel)
            ],
            WAITING_DAY_SELECTION: [
                CallbackQueryHandler(day_selection_callback, pattern="^day_")
            ],
            WAITING_TIME_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, time_input_handler),
                CommandHandler("cancel", cancel)
            ],
            ASKING_REMINDER: [
                CallbackQueryHandler(reminder_choice_callback)
            ],
            WAITING_NOTIFICATION: [
                CallbackQueryHandler(notification_callback)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start_command),
            CommandHandler("help", help_command),
            CommandHandler("schedule", schedule_command)
        ],
        allow_reentry=True
    )
    
    # Add conversation handler for removing lessons
    remove_lesson_conv = ConversationHandler(
        entry_points=[CommandHandler("remove_lesson", remove_lesson_command)],
        states={
            WAITING_REMOVE_DAY_SELECTION: [
                CallbackQueryHandler(remove_day_selection_callback, pattern="^rmday_")
            ],
            WAITING_REMOVE_LESSON_SELECTION: [
                CallbackQueryHandler(remove_lesson_selection_callback, pattern="^rmlesson_")
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start_command),
            CommandHandler("help", help_command),
            CommandHandler("schedule", schedule_command)
        ],
        allow_reentry=True
    )
    
    # Add conversation handler for turning on/off reminder
    reminder_conv = ConversationHandler(
        entry_points=[
            CommandHandler("turn_on_off", turn_on_off_reminder_command)
        ],
        states={
            WAITING_REMINDER_LESSON_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_lesson_input_handler),
                CommandHandler("cancel", cancel)
            ],
            WAITING_REMINDER_CHOICE: [
                CallbackQueryHandler(reminder_update_callback)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start_command),
            CommandHandler("help", help_command),
            CommandHandler("schedule", schedule_command)
        ],
        allow_reentry=True
    )
    
    application.add_handler(add_lesson_conv)
    application.add_handler(remove_lesson_conv)
    application.add_handler(reminder_conv)
    
    # Handle unknown commands and random text
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_text))
    application.add_error_handler(error_handler)

    # Schedule reminder checks (every 60 seconds)
    application.job_queue.run_repeating(check_and_send_reminders, interval=60, first=10)
    
    # Start the bot
    print("✅ Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()
