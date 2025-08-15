import requests
from django.conf import settings

def send_telegram_message(message):
    """
    Sends a message to the Telegram chats specified in the settings.
    """
    token = settings.TELEGRAM_BOT_TOKEN
    chat_ids = settings.TELEGRAM_CHAT_IDS

    if not token or not chat_ids:
        print("Telegram settings (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_IDS) are not configured.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    for chat_id in chat_ids:
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'Markdown'
        }
        try:
            response = requests.post(url, data=payload)
            if response.status_code != 200:
                print(f"Failed to send message to {chat_id}: {response.text}")
        except requests.exceptions.RequestException as e:
            print(f"Error sending Telegram message: {e}")
