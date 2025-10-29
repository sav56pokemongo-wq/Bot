import telebot
import requests
from bs4 import BeautifulSoup
import sqlite3
import time
import threading
import logging

# Ваш токен бота
TOKEN = '8470624102:AAHTd2obrD6CQYXYBeyUXXX2YnBS7WRERSM'
bot = telebot.TeleBot(TOKEN)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

# Подключение к базе данных для хранения истории
conn = sqlite3.connect('price_history.db', check_same_thread=False)
cursor = conn.cursor()

# Создание таблиц, если их нет
cursor.execute("""
CREATE TABLE IF NOT EXISTS prices (
    product_id TEXT PRIMARY KEY, 
    price REAL, 
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    user_id INTEGER
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY, 
    username TEXT
)
""")
conn.commit()

# Функции для получения цен с маркетплейсов

def get_ozon_price(product_url):
    """Парсинг цены с Озон"""
    try:
        response = requests.get(product_url)
        soup = BeautifulSoup(response.content, 'html.parser')
        # Пример, замените на реальный тег, который содержит цену на Озоне
        price_tag = soup.find('span', {'class': 'price-class'})
        if price_tag:
            return float(price_tag.text.strip().replace('₽', '').replace(' ', ''))
        return None
    except Exception as e:
        logger.error(f"Error fetching price from Ozon: {e}")
        return None

def get_wildberries_price(product_url):
    """Парсинг цены с Валдберес"""
    try:
        response = requests.get(product_url)
        soup = BeautifulSoup(response.content, 'html.parser')
        # Пример, замените на реальный тег, который содержит цену на Валдберес
        price_tag = soup.find('span', {'class': 'price-class'})
        if price_tag:
            return float(price_tag.text.strip().replace('₽', '').replace(' ', ''))
        return None
    except Exception as e:
        logger.error(f"Error fetching price from Wildberries: {e}")
        return None

# Функция для проверки изменений цены
def check_price_changes(product_url, product_id, platform, user_id):
    if platform == 'ozon':
        current_price = get_ozon_price(product_url)
    elif platform == 'wildberries':
        current_price = get_wildberries_price(product_url)
    
    if current_price is not None:
        cursor.execute("SELECT * FROM prices WHERE product_id=? ORDER BY timestamp DESC LIMIT 1", (product_id,))
        last_price = cursor.fetchone()
        
        if last_price is None or last_price[1] != current_price:
            cursor.execute("INSERT INTO prices (product_id, price, user_id) VALUES (?, ?, ?)", (product_id, current_price, user_id))
            conn.commit()
            return current_price
    return None

# Отправка уведомлений пользователю
def send_price_alert(chat_id, product_url, product_id, platform):
    price_change = check_price_changes(product_url, product_id, platform, chat_id)
    if price_change:
        bot.send_message(chat_id, f"Цена на товар {product_url} изменилась! Новая цена: {price_change}₽")

# Команда /start для инициализации пользователя
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    username = message.chat.username
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    bot.send_message(user_id, "Добро пожаловать! Используйте команду /add <платформа> <URL товара> для добавления товара в отслеживание.")

# Команда /add для добавления отслеживаемого товара
@bot.message_handler(commands=['add'])
def add_product(message):
    msg = message.text.split()
    if len(msg) != 3:
        bot.send_message(message.chat.id, "Неверный формат! Используйте /add <платформа> <URL товара>")
        return
    
    platform, product_url = msg[1], msg[2]
    product_id = f'{platform}_{product_url}'  # Уникальный ID для товара
    user_id = message.chat.id
    
    # Отправляем уведомление сразу при добавлении товара
    send_price_alert(user_id, product_url, product_id, platform)
    bot.send_message(user_id, f"Товар добавлен для отслеживания: {product_url}")

# Команда /list для получения списка отслеживаемых товаров
@bot.message_handler(commands=['list'])
def list_products(message):
    user_id = message.chat.id
    cursor.execute("SELECT product_id, price FROM prices WHERE user_id=?", (user_id,))
    rows = cursor.fetchall()
    
    if rows:
        response = "Ваши отслеживаемые товары:"
        for row in rows:
            product_id, price = row
            response += f"{product_id}: {price}₽"
        bot.send_message(user_id, response)
    else:
        bot.send_message(user_id, "Вы не отслеживаете ни одного товара.")

# Функция для мониторинга изменения цен (проверка каждую минуту)
def track_prices():
    while True:
        cursor.execute("SELECT * FROM prices")
        rows = cursor.fetchall()
        
        for row in rows:
            product_id, price, timestamp, user_id = row
            platform = 'ozon' if 'ozon' in product_id else 'wildberries'
            product_url = product_id.split('_')[1]
            
            # Отправляем уведомления пользователю
            send_price_alert(user_id, product_url, product_id, platform)

        time.sleep(60)  # Проверка цен каждую минуту

# Запуск мониторинга в отдельном потоке
def start_tracking():
    tracking_thread = threading.Thread(target=track_prices)
    tracking_thread.daemon = True
    tracking_thread.start()

if __name__ == '__main__':
    # Запуск мониторинга цен
    start_tracking()

    # Запуск бота
    bot.polling(none_stop=True)
