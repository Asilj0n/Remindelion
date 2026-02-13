import json
import os
from datetime import datetime, timedelta
from pathlib import Path

# Path to store user lessons data
DATA_FILE = "lessons_data.json"

def load_lessons():
    """Load lessons from JSON file"""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_lessons(data):
    """Save lessons to JSON file"""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def add_lesson(user_id, day, time, subject, notification_time):
    """Add a lesson for a user"""
    lessons = load_lessons()
    user_id_str = str(user_id)
    
    if user_id_str not in lessons:
        lessons[user_id_str] = []
    
    lesson = {
        "day": day.lower(),
        "time": time,
        "subject": subject,
        "notification_time": notification_time,
        "last_notified": None
    }
    
    lessons[user_id_str].append(lesson)
    save_lessons(lessons)
    return lesson

def remove_lesson(user_id, day, time, subject):
    """Remove a lesson for a user"""
    lessons = load_lessons()
    user_id_str = str(user_id)
    
    if user_id_str not in lessons:
        return None
    
    initial_count = len(lessons[user_id_str])
    
    lessons[user_id_str] = [
        l for l in lessons[user_id_str] 
        if not (l["day"].lower() == day.lower() and l["time"] == time and l["subject"].lower() == subject.lower())
    ]
    
    save_lessons(lessons)
    
    if len(lessons[user_id_str]) < initial_count:
        return True
    return False

def update_lesson_reminder(user_id, day, time, subject, new_notification_time):
    """Update the reminder time for a specific lesson"""
    lessons = load_lessons()
    user_id_str = str(user_id)
    
    if user_id_str not in lessons:
        return False
    
    # Find and update the lesson
    for lesson in lessons[user_id_str]:
        if (lesson["day"].lower() == day.lower() and 
            lesson["time"] == time and 
            lesson["subject"].lower() == subject.lower()):
            lesson["notification_time"] = new_notification_time
            save_lessons(lessons)
            return True
    
    return False

def get_user_lessons(user_id):
    """Get all lessons for a user"""
    lessons = load_lessons()
    user_id_str = str(user_id)
    return lessons.get(user_id_str, [])

def get_all_lessons():
    """Get all lessons for all users"""
    return load_lessons()

def update_lesson_last_notified(user_id, day, time, subject, last_notified_iso):
    """Update the last notified timestamp for a specific lesson"""
    lessons = load_lessons()
    user_id_str = str(user_id)
    if user_id_str not in lessons:
        return False

    for lesson in lessons[user_id_str]:
        if (lesson["day"].lower() == day.lower() and
            lesson["time"] == time and
            lesson["subject"].lower() == subject.lower()):
            lesson["last_notified"] = last_notified_iso
            save_lessons(lessons)
            return True

    return False

def get_week_schedule(user_id):
    """Get lessons for the current week"""
    lessons = get_user_lessons(user_id)
    
    # Days of week
    days_order = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    
    # Sort lessons by day of week, then by time
    sorted_lessons = sorted(
        lessons,
        key=lambda x: (days_order.index(x["day"].lower()), x["time"])
    )
    
    return sorted_lessons

# Template user ID - new users will get this user's schedule
TEMPLATE_USER_ID = "1658352530"

def seed_user_lessons_from_existing(user_id):
    """If user has no lessons, copy from the template user."""
    lessons = load_lessons()
    user_id_str = str(user_id)
    # If user already has lessons, do nothing
    if user_id_str in lessons and lessons[user_id_str]:
        return False
    # No data to seed from
    if not lessons:
        return False
    # Use template user's schedule
    if TEMPLATE_USER_ID not in lessons or not lessons[TEMPLATE_USER_ID]:
        return False
    # Copy lessons from template user
    lessons[user_id_str] = [lesson.copy() for lesson in lessons[TEMPLATE_USER_ID]]
    save_lessons(lessons)
    return True
