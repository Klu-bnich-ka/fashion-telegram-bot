import requests
import os
import re
import random
from bs4 import BeautifulSoup
import feedparser
from datetime import datetime, timedelta
import time
import json
import logging
import hashlib
from urllib.parse import urljoin, quote
import sqlite3
from contextlib import contextmanager
import urllib3
from textblob import TextBlob
import sys

# Отключаем предупреждения SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot_debug.log')
    ]
)
logger = logging.getLogger(__name__)

# Настройки
BOT_TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
CHANNEL = os.environ.get('CHANNEL', '@YOUR_CHANNEL_HERE')

# Проверяем переменные окружения
if BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE' or CHANNEL == '@YOUR_CHANNEL_HERE':
    logger.error("❌ Please set BOT_TOKEN and CHANNEL environment variables")
    sys.exit(1)

logger.info(f"✅ Bot token: {BOT_TOKEN[:10]}...")
logger.info(f"✅ Channel: {CHANNEL}")

# Только 3 самых популярных источника
SOURCES = [
    {
        'name': 'Hypebeast', 
        'url': 'https://hypebeast.com/fashion/feed',
        'lang': 'en',
        'weight': 10
    },
    {
        'name': 'Highsnobiety', 
        'url': 'https://www.highsnobiety.com/feed/',
        'lang': 'en', 
        'weight': 9
    },
    {
        'name': 'Sneaker News',
        'url': 'https://sneakernews.com/feed/',
        'lang': 'en',
        'weight': 8
    }
]

BRANDS = [
    'Nike', 'Jordan', 'Adidas', 'New Balance', 'Supreme', 'Palace', 
    'Bape', 'Stussy', 'Off-White', 'Balenciaga', 'Gucci', 'Dior',
    'Louis Vuitton', 'Prada', 'Chanel', 'Versace', 'Yeezy'
]

class ToporStyleFormatter:
    """Форматирование в стиле Топора"""
    
    @staticmethod
    def create_post(brand, title, content):
        """Создает пост в стиле Топора"""
        emoji = "👟"  # Простой эмодзи
        
        # Генерируем реалистичные числа
        subscribers = f"{random.randint(500, 1200)}K"
        comments = random.randint(200, 2500)
        time_posted = f"{random.randint(10, 23)}:{random.randint(10, 59)}"
        
        # Создаем пост в точном формате Топора
        post = f"""{title}

{content}

Топор +18. Подписаться
{subscribers} {time_posted}

{comments} комментариев

Топор+
"""
        return post

class SimpleNewsAggregator:
    """Упрощенный агрегатор новостей"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/rss+xml, application/xml, text/xml, */*'
        })
        
    def get_all_news(self):
        """Получает все новости из источников"""
        all_news = []
        
        for source in SOURCES:
            try:
                logger.info(f"🔍 Checking {source['name']}...")
                news_items = self.parse_feed(source)
                all_news.extend(news_items)
                logger.info(f"✅ Found {len(news_items)} news from {source['name']}")
                time.sleep(1)
            except Exception as e:
                logger.error(f"❌ Error with {source['name']}: {str(e)}")
                continue
                
        return all_news
    
    def parse_feed(self, source):
        """Парсит RSS фид"""
        news_items = []
        
        try:
            feed = feedparser.parse(source['url'])
            logger.info(f"📋 Feed {source['name']} has {len(feed.entries)} entries")
            
            for entry in feed.entries[:5]:  # Берем только 5 последних
                if self.is_recent(entry):
                    news_item = self.process_entry(entry, source)
                    if news_item:
                        news_items.append(news_item)
                        
        except Exception as e:
            logger.error(f"❌ Feed parsing error {source['name']}: {str(e)}")
            
        return news_items
    
    def is_recent(self, entry, max_hours=24):
        """Проверяет свежесть новости"""
        try:
            # Пробуем разные поля даты
            date_str = getattr(entry, 'published', None) or getattr(entry, 'updated', None)
            if not date_str:
                return True  # Если даты нет, считаем свежей
                
            # Парсим дату
            parsed_date = self.parse_date(date_str)
            if not parsed_date:
                return True
                
            # Проверяем свежесть
            time_diff = datetime.now() - parsed_date
            return time_diff.total_seconds() / 3600 <= max_hours
            
        except Exception as e:
            logger.warning(f"⚠️ Date parsing error: {e}")
            return True
    
    def parse_date(self, date_string):
        """Парсит дату"""
        formats = [
            '%a, %d %b %Y %H:%M:%S %Z',
            '%a, %d %b %Y %H:%M:%S %z', 
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%d %H:%M:%S'
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_string, fmt)
            except:
                continue
        return None
    
    def process_entry(self, entry, source):
        """Обрабатывает запись"""
        try:
            title = getattr(entry, 'title', 'No title')
            description = getattr(entry, 'description', '')
            link = getattr(entry, 'link', '')
            
            # Ищем бренд
            brand = self.find_brand(title + " " + description)
            if not brand:
                return None
            
            # Очищаем контент
            content = self.clean_content(description or title)
            
            return {
                'title': title,
                'content': content,
                'brand': brand,
                'source': source['name'],
                'link': link,
                'original_title': title
            }
            
        except Exception as e:
            logger.error(f"❌ Entry processing error: {e}")
            return None
    
    def find_brand(self, text):
        """Находит бренд в тексте"""
        text_lower = text.lower()
        for brand in BRANDS:
            if brand.lower() in text_lower:
                return brand
        return None
    
    def clean_content(self, content):
        """Очищает контент"""
        # Удаляем HTML теги
        clean = re.sub('<[^<]+?>', '', content)
        # Удаляем лишние пробелы
        clean = re.sub('\s+', ' ', clean).strip()
        # Обрезаем до 200 символов
        if len(clean) > 200:
            clean = clean[:197] + '...'
        return clean

class SimpleContentEnhancer:
    """Упрощенный усилитель контента"""
    
    def enhance_content(self, original_content, brand):
        """Улучшает контент"""
        # Простой перевод ключевых слов
        translations = {
            'release': 'релиз',
            'collection': 'коллекция', 
            'collaboration': 'коллаборация',
            'sneakers': 'кроссовки',
            'limited': 'лимитированный',
            'edition': 'издание',
            'new': 'новый',
            'available': 'доступен'
        }
        
        content = original_content
        for eng, rus in translations.items():
            content = re.sub(rf'\b{eng}\b', rus, content, flags=re.IGNORECASE)
        
        # Делаем более разговорным
        content = content.replace('The', '').replace('A ', '')
        
        return content
    
    def create_catchy_title(self, original_title, brand):
        """Создает цепляющий заголовок"""
        templates = [
            f"{brand} запускает новый дроп",
            f"Новинка от {brand} уже здесь", 
            f"{brand} удивляет новым релизом",
            f"Хит сезона от {brand}",
            f"{brand} анонсирует коллаборацию"
        ]
        return random.choice(templates)

class DatabaseManager:
    """Менеджер базы данных"""
    
    def __init__(self):
        self.init_db()
    
    def init_db(self):
        """Инициализирует БД"""
        conn = sqlite3.connect('news.db')
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sent_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_hash TEXT UNIQUE,
                brand TEXT,
                sent_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
    
    def is_duplicate(self, content):
        """Проверяет дубликат"""
        content_hash = hashlib.md5(content.encode()).hexdigest()
        conn = sqlite3.connect('news.db')
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM sent_posts WHERE content_hash = ?', (content_hash,))
        result = cursor.fetchone() is not None
        conn.close()
        return result
    
    def mark_sent(self, content, brand):
        """Помечает как отправленное"""
        content_hash = hashlib.md5(content.encode()).hexdigest()
        conn = sqlite3.connect('news.db')
        cursor = conn.cursor()
        try:
            cursor.execute(
                'INSERT INTO sent_posts (content_hash, brand) VALUES (?, ?)',
                (content_hash, brand)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            pass
        conn.close()

class TelegramBot:
    """Упрощенный Telegram бот"""
    
    def __init__(self, token, channel):
        self.token = token
        self.channel = channel
        self.session = requests.Session()
        self.timeout = 30
    
    def send_message(self, text):
        """Отправляет сообщение"""
        url = f'https://api.telegram.org/bot{self.token}/sendMessage'
        
        payload = {
            'chat_id': self.channel,
            'text': text,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True
        }
        
        try:
            logger.info(f"📤 Sending message to Telegram...")
            logger.info(f"Message preview: {text[:100]}...")
            
            response = self.session.post(url, json=payload, timeout=self.timeout)
            response_data = response.json()
            
            logger.info(f"📡 Telegram API response: {response.status_code}")
            
            if response.status_code == 200:
                logger.info("✅ Message sent successfully!")
                return True
            else:
                logger.error(f"❌ Telegram API error: {response_data}")
                return False
                
        except requests.exceptions.Timeout:
            logger.error("❌ Request timeout")
            return False
        except requests.exceptions.ConnectionError:
            logger.error("❌ Connection error")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error: {str(e)}")
            return False
    
    def test_connection(self):
        """Тестирует соединение с ботом"""
        url = f'https://api.telegram.org/bot{self.token}/getMe'
        
        try:
            response = self.session.get(url, timeout=10)
            if response.status_code == 200:
                bot_info = response.json()
                logger.info(f"✅ Bot connection test passed: {bot_info['result']['username']}")
                return True
            else:
                logger.error(f"❌ Bot connection test failed: {response.text}")
                return False
        except Exception as e:
            logger.error(f"❌ Bot connection test error: {e}")
            return False

class FashionNewsBot:
    """Главный класс бота"""
    
    def __init__(self):
        self.db = DatabaseManager()
        self.aggregator = SimpleNewsAggregator()
        self.enhancer = SimpleContentEnhancer()
        self.formatter = ToporStyleFormatter()
        self.bot = TelegramBot(BOT_TOKEN, CHANNEL)
    
    def run(self):
        """Запускает бота"""
        logger.info("🚀 Starting Fashion News Bot")
        
        # Тестируем соединение с ботом
        if not self.bot.test_connection():
            logger.error("❌ Bot connection test failed. Exiting.")
            return False
        
        # Ищем новости
        all_news = self.aggregator.get_all_news()
        logger.info(f"📰 Total news found: {len(all_news)}")
        
        if not all_news:
            logger.warning("⚠️ No news found, generating fallback content...")
            return self.send_fallback_content()
        
        # Пробуем отправить первую подходящую новость
        for news in all_news:
            if self.try_send_news(news):
                return True
        
        # Если ничего не нашли, отправляем фолбэк
        logger.warning("⚠️ No suitable news found, sending fallback...")
        return self.send_fallback_content()
    
    def try_send_news(self, news):
        """Пробует отправить новость"""
        try:
            brand = news['brand']
            original_content = news['content']
            original_title = news['title']
            
            # Улучшаем контент
            enhanced_content = self.enhancer.enhance_content(original_content, brand)
            catchy_title = self.enhancer.create_catchy_title(original_title, brand)
            
            # Создаем финальный пост
            final_content = f"{catchy_title}\n\n{enhanced_content}"
            
            # Проверяем дубликат
            if self.db.is_duplicate(final_content):
                logger.info(f"⏭️ Duplicate content skipped: {brand}")
                return False
            
            # Создаем пост в стиле Топора
            post = self.formatter.create_post(brand, catchy_title, enhanced_content)
            
            # Отправляем
            if self.bot.send_message(post):
                self.db.mark_sent(final_content, brand)
                logger.info(f"✅ Successfully posted about {brand}")
                return True
            else:
                logger.error(f"❌ Failed to post about {brand}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error processing news: {e}")
            return False
    
    def send_fallback_content(self):
        """Отправляет фолбэк контент"""
        fallback_brands = [
            {
                'brand': 'Nike',
                'title': 'Nike готовит сюрприз',
                'content': 'По слухам, Nike работает над новой коллаборацией с известным дизайнером. Ожидается ограниченный релиз.'
            },
            {
                'brand': 'Adidas', 
                'content': 'Adidas анонсирует обновление культовой модели. Фанаты ждут с нетерпением.'
            },
            {
                'brand': 'Supreme',
                'content': 'Supreme готовит новый дроп с неожиданным партнером. Инсайдеры говорят о сюрпризе.'
            }
        ]
        
        fallback = random.choice(fallback_brands)
        catchy_title = self.enhancer.create_catchy_title(fallback['title'], fallback['brand'])
        post = self.formatter.create_post(fallback['brand'], catchy_title, fallback['content'])
        
        logger.info("🔄 Sending fallback content...")
        return self.bot.send_message(post)

def main():
    """Главная функция"""
    max_retries = 3
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            logger.info(f"🔄 Attempt {attempt + 1}/{max_retries}")
            
            bot = FashionNewsBot()
            success = bot.run()
            
            if success:
                logger.info("🎉 Bot finished successfully!")
                return
            else:
                logger.warning(f"⚠️ Attempt {attempt + 1} failed")
                
        except Exception as e:
            logger.error(f"💥 Critical error in attempt {attempt + 1}: {e}")
        
        if attempt < max_retries - 1:
            logger.info(f"⏳ Waiting {retry_delay} seconds before retry...")
            time.sleep(retry_delay)
    
    logger.error("💥 All attempts failed!")

if __name__ == "__main__":
    main()
