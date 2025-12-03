import os
from dotenv import load_dotenv


# Загружаем переменные из .env файла
load_dotenv()

# Токен бота (ОБЯЗАТЕЛЬНО замените на свой реальный токен!)
BOT_TOKEN = os.getenv('8571481642:AAE3sBqPjeVxu872KZBg1ojhAdsAk8RXHWY')

# Если токен не найден, используем дефолтный
if not BOT_TOKEN:
    BOT_TOKEN = "8571481642:AAE3sBqPjeVxu872KZBg1ojhAdsAk8RXHWY"  # Замените на ваш реальный токен!

# ID администраторов (замените на свой ID)
ADMIN_IDS = [5623324059]  # Ваш ID из вывода

# Настройки платежей
PAYMENT_METHODS = {
    'sber': '2202 2082 6210 7460'
}