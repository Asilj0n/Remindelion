# Lesson Reminder Telegram Bot

A Telegram bot that helps you manage and remember your weekly lessons/schedule.

## Features

- 📚 **Add Lessons**: Store your lessons with day, time, and subject
- 📅 **View Schedule**: See your complete weekly schedule
- 🗑️ **Remove Lessons**: Delete lessons you no longer need
- ⏰ **Reminders**: Choose when to be reminded (5 min, 15 min, 30 min, or 1 hour before)
- 💾 **Persistent Storage**: Your lessons are saved locally in JSON format

## Requirements

- Python 3.8+
- python-telegram-bot library

## Installation

1. Clone or download this project
2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Configuration

The bot token is stored in `config.py`. Update it with your Telegram bot token:

```python
BOT_TOKEN = "your_bot_token_here"
```

## Usage

Run the bot:
```bash
python bot.py
```

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Shows bot information and available commands |
| `/schedule` | View your weekly schedule with all lessons |
| `/add_lesson` | Add a new lesson to your schedule |
| `/remove_lesson` | Remove a lesson from your schedule |
| `/help` | Show all available commands |

## Adding a Lesson

When you use `/add_lesson`, the bot will ask you to enter your lesson in this format:
```
Day, Time, Subject
```

**Example:** `Monday, 14:00, Calculus 2`

- **Day**: Monday through Sunday
- **Time**: 24-hour format (00:00 - 23:59)
- **Subject**: Your lesson name

After submitting, the bot will ask when you want to be reminded:
- 5 minutes before
- 15 minutes before
- 30 minutes before
- 1 hour before

## Removing a Lesson

Use `/remove_lesson` and enter the lesson details in the same format:
```
Day, Time, Subject
```

## Data Storage

All lessons are stored in `lessons_data.json` in the following format:
```json
{
  "user_id": [
    {
      "day": "monday",
      "time": "14:00",
      "subject": "Calculus 2",
      "notification_time": "30 min"
    }
  ]
}
```

## Project Structure

- `bot.py` - Main bot application with all command handlers
- `database.py` - Database operations for storing and retrieving lessons
- `config.py` - Configuration file with bot token
- `requirements.txt` - Python dependencies
- `README.md` - This file

## Notes

- The bot stores data per user ID, so each user has their own schedule
- Lessons are sorted by day of week and time for easier viewing
- Use `/cancel` to stop any ongoing operation

## Future Enhancements

- Automatic reminder notifications at scheduled times
- Export schedule to calendar formats
- Recurring lessons
- Lesson notes and location information
- Integration with calendar systems
