from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.models import User
from .models import TelegramUser

class TelegramAuthenticationBackend(BaseBackend):
    """
    Кастомный бэкенд аутентификации для входа через Telegram.
    """
    def authenticate(self, request, telegram_data=None):
        if telegram_data is None:
            return None

        telegram_id = telegram_data['id']

        try:
            # Ищем существующего пользователя по Telegram ID
            telegram_user = TelegramUser.objects.get(telegram_id=telegram_id)
            # Обновляем данные на случай, если пользователь сменил имя или фото в Telegram
            telegram_user.first_name = telegram_data.get('first_name', '')
            telegram_user.last_name = telegram_data.get('last_name', '')
            telegram_user.username = telegram_data.get('username')
            telegram_user.photo_url = telegram_data.get('photo_url')
            telegram_user.save()
            return telegram_user.user
        except TelegramUser.DoesNotExist:
            # Создаем нового пользователя, если он не найден
            username = telegram_data.get('username', f"tg_{telegram_id}")

            # Гарантируем уникальность username
            if User.objects.filter(username=username).exists():
                username = f"{username}_{telegram_id}"

            user = User.objects.create_user(
                username=username,
                first_name=telegram_data.get('first_name', ''),
                last_name=telegram_data.get('last_name', '')
            )

            TelegramUser.objects.create(
                user=user,
                telegram_id=telegram_id,
                first_name=telegram_data.get('first_name', ''),
                last_name=telegram_data.get('last_name', ''),
                username=telegram_data.get('username'),
                photo_url=telegram_data.get('photo_url')
            )
            return user

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
