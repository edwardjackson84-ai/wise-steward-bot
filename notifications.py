# notifications.py
"""Failure-path Telegram notifications. Fail-silently — never crashes caller."""
import os
import requests

def notify_telegram(message: str) -> None:
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        return  # No-op when not configured
    try:
        requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": message[:4000]},  # TG hard limit ~4096
            timeout=5,
        )
    except Exception as e:
        print(f"[Telegram] Notification failed: {e}")  # Don't propagate
