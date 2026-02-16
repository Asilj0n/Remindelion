# Lesson Reminder Telegram Bot

A Telegram bot that helps you manage and remember your weekly lessons/schedule.

## Features

- 📚 **Add Lessons**: Easy button-based day selection + text input for time
- 📅 **View Schedule**: See your complete weekly schedule
- 📆 **Today/Tomorrow**: Quick view of today's or tomorrow's lessons
- 🗑️ **Remove Lessons**: Button-based removal - select day, then pick the lesson
- ⏰ **Reminders**: Get notified 5 min, 15 min, 30 min, or 1 hour before lessons
- 🕐 **Bishkek Timezone**: All times use Asia/Bishkek (UTC+6)
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
| `/lessons_today` | View today's lessons |
| `/lessons_tomorrow` | View tomorrow's lessons |
| `/add_lesson` | Add a new lesson to your schedule |
| `/remove_lesson` | Remove a lesson from your schedule |
| `/turn_on_off` | Turn on/off reminder for a specific lesson |
| `/help` | Show all available commands |

## Adding a Lesson

When you use `/add_lesson`:

1. **Enter course name** - Type the name of your course (e.g., "Calculus 2")
2. **Select day** - Tap a button to choose the day (Monday - Sunday)
3. **Enter time** - Type the time in format `##:##` (e.g., `09:30` or `14:00`)
4. **Set reminder** - Choose whether to set a reminder:
   - 5 minutes before
   - 15 minutes before
   - 30 minutes before
   - 1 hour before
   - No reminder

## Removing a Lesson

When you use `/remove_lesson`:

1. **Select day** - Tap a button to choose the day
2. **Select lesson** - See all lessons on that day and tap to remove
   - If no lessons exist on that day, you'll be prompted to select another day
   - Use "Back" to go back to day selection
   - Use "Cancel" to cancel the operation

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
- Random text input will prompt users to use valid commands
- Automatic reminders are sent based on your notification preferences

## Future Enhancements

- Export schedule to calendar formats
- Recurring lessons
- Lesson notes and location information
- Integration with calendar systems
