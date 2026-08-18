import re

SYSTEM_REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)


def strip_system_reminders(text: str) -> str:
    return SYSTEM_REMINDER.sub("", text)
