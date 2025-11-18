import requests
import os
import re
import random
from bs4 import BeautifulSoup
import feedparser
from datetime import datetime, timedelta
import time
import logging
import hashlib
from urllib.parse import urljoin
import sqlite3
from googletrans import Translator

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Настройки
BOT_TOKEN = os.environ['BOT_TOKEN']
CHANNEL = os.environ['CHANNEL']

# 3 основных источника
SOURCES = [
    {
        'name': 'Hypebeast', 
        'url': 'https://hypebeast.com/fashion/feed',
        'base_url': 'https://hypebeast.com'
    },
    {
        'name': 'Highsnobiety', 
        'url': 'https://www.highsnobiety.com/feed/',
        'base_url': 'https://www.highsnobiety.com'
    },
    {
        'name': 'Sneaker News',
        'url': 'https://sneakernews.com/feed/',
        'base_url': 'https://sneakernews.com'
    }
]

# Популярные бренды для фильтрации
BRANDS = [
    'Nike', 'Jordan', 'Adidas', 'New Balance', 'Supreme', 'Palace', 
    'Bape', 'Stussy', 'Off-White', 'Balenciaga', 'Gucci', 'Dior',
    'Louis Vuitton', 'Prada', 'Chanel', 'Versace', 'Yeezy', 'Travis Scott',
    'Fragment', 'Converse', 'Vans', 'Timberland', 'Arc\'teryx', 'Salomon'
]

class SimpleTranslator:
    def __init__(self):
        self.translator = Translator()
        
    def translate_text(self, text):
        """Простой перевод текста"""
        try:
            if len(text) > 5000:
                text = text[:5000]
            translated = self.translator.translate(text, dest='ru')
            return translated.text
        except Exception as e:
            logger.warning(f"Translation failed: {e}")
            return text

class ContentExtractor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
    
    def extract_full_content(self, url):
        """Извлекает полный контент и изображения со страницы"""
        try:
            response = self.session.get(url, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Удаляем ненужные элементы
            for element in soup.find_all(['script', 'style', 'nav', 'footer', 'aside']):
                element.decompose()
            
            # Ищем основной контент
            content_selectors = [
                'article',
                '.post-content',
                '.entry-content',
                '.article-content',
                '.content',
                'main'
            ]
            
            content_element = None
            for selector in content_selectors:
                content_element = soup.select_one(selector)
                if content_element:
                    break
            
            if not content_element:
                content_element = soup.find('body')
            
            # Извлекаем текст
            text_content = self.clean_text(content_element.get_text())
            
            # Извлекаем все изображения
            images = self.extract_images(soup, url)
            
            return text_content, images
            
        except Exception as e:
            logger.error(f"Error extracting content from {url}: {e}")
            return None, []
    
    def clean_text(self, text):
        """Очищает текст"""
        # Удаляем лишние пробелы и переносы
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\n+', '\n', text)
        return text.strip()
    
    def extract_images(self, soup, base_url):
        """Извлекает все изображения со страницы"""
        images = []
        img_selectors = [
            'img',
            '.wp-post-image',
            '.article-image img',
            '.post-image img',
            '.entry-content img',
            '.content img',
            'figure img'
        ]
        
        for selector in img_selectors:
            for img in soup.select(selector):
                src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                if src:
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = urljoin(base_url, src)
                    
                    # Проверяем, что это нормальное изображение
                    if self.is_valid_image(src):
                        images.append(src)
        
        # Убираем дубликаты
        return list(dict.fromkeys(images))
    
    def is_valid_image(self, url):
        """Проверяет валидность изображения"""
        excluded = ['logo', 'icon', 'avatar', 'thumbnail', 'pixel', 'spinner']
        if any(term in url.lower() for term in excluded):
            return False
        
        valid_ext = ['.jpg', '.jpeg', '.png', '.webp', '.gif']
        if not any(ext in url.lower() for ext in valid_ext):
            return False
            
        return True

class DatabaseManager:
    def __init__(self):
        self.init_database()
    
    def init_database(self):
        """Инициализирует базу данных"""
        conn = sqlite3.connect('news.db')
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sent_news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url_hash TEXT UNIQUE,
                source TEXT,
                title TEXT,
                sent_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
    
    def is_news_sent(self, url):
        """Проверяет, была ли новость отправлена"""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        conn = sqlite3.connect('news.db')
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM sent_news WHERE url_hash = ?', (url_hash,))
        result = cursor.fetchone() is not None
        conn.close()
        return result
    
    def mark_news_sent(self, url, source, title):
        """Помечает новость как отправленную"""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        conn = sqlite3.connect('news.db')
        cursor = conn.cursor()
        try:
            cursor.execute(
                'INSERT INTO sent_news (url_hash, source, title) VALUES (?, ?, ?)',
                (url_hash, source, title[:200])
            )
            conn.commit()
        except sqlite3.IntegrityError:
            pass
        conn.close()

class TelegramPublisher:
    def __init__(self, token, channel):
        self.token = token
        self.channel = channel
        self.session = requests.Session()
    
    def send_photo_group(self, caption, photo_urls):
        """Отправляет группу фотографий с подписью"""
        if not photo_urls:
            return self.send_message(caption)
        
        # Отправляем первую фотографию с подписью
        first_photo = photo_urls[0]
        additional_photos = photo_urls[1:4]  # Максимум 5 фото в группе
        
        try:
            # Скачиваем первую фотографию
            response = self.session.get(first_photo, timeout=10)
            if response.status_code != 200:
                return self.send_message(caption)
            
            files = {'photo': ('image.jpg', response.content, 'image/jpeg')}
            data = {
                'chat_id': self.channel,
                'caption': caption,
                'parse_mode': 'HTML'
            }
            
            # Отправляем первую фото с подписью
            url = f'https://api.telegram.org/bot{self.token}/sendPhoto'
            response = self.session.post(url, files=files, data=data, timeout=30)
            
            if response.status_code == 200 and additional_photos:
                # Получаем ID первого сообщения для группировки
                first_message_id = response.json()['result']['message_id']
                
                # Отправляем остальные фото как группа
                for photo_url in additional_photos:
                    try:
                        photo_response = self.session.get(photo_url, timeout=10)
                        if photo_response.status_code == 200:
                            files = {'photo': ('image.jpg', photo_response.content, 'image/jpeg')}
                            data = {
                                'chat_id': self.channel,
                                'reply_to_message_id': first_message_id
                            }
                            self.session.post(url, files=files, data=data, timeout=30)
                            time.sleep(1)  # Задержка между отправками
                    except:
                        continue
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending photos: {e}")
            return self.send_message(caption)
    
    def send_message(self, text):
        """Отправляет текстовое сообщение"""
        url = f'https://api.telegram.org/bot{self.token}/sendMessage'
        data = {
            'chat_id': self.channel,
            'text': text,
            'parse_mode': 'HTML',
            'disable_web_page_preview': False
        }
        
        try:
            response = self.session.post(url, json=data, timeout=30)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False

class FashionNewsBot:
    def __init__(self):
        self.db = DatabaseManager()
        self.translator = SimpleTranslator()
        self.extractor = ContentExtractor()
        self.publisher = TelegramPublisher(BOT_TOKEN, CHANNEL)
    
    def check_sources(self):
        """Проверяет все источники на новые новости"""
        all_news = []
        
        for source in SOURCES:
            try:
                logger.info(f"🔍 Checking {source['name']}...")
                news_items = self.parse_feed(source)
                all_news.extend(news_items)
                time.sleep(2)  # Задержка между запросами
            except Exception as e:
                logger.error(f"Error parsing {source['name']}: {e}")
                continue
        
        return all_news
    
    def parse_feed(self, source):
        """Парсит RSS фид источника"""
        news_items = []
        
        try:
            feed = feedparser.parse(source['url'])
            
            for entry in feed.entries[:10]:  # Берем 10 последних записей
                if self.is_recent(entry) and self.is_fashion_related(entry):
                    news_item = {
                        'title': entry.title,
                        'url': entry.link,
                        'source': source['name'],
                        'published': getattr(entry, 'published', ''),
                        'summary': getattr(entry, 'summary', '')[:500]  # Берем краткое описание
                    }
                    news_items.append(news_item)
                    
        except Exception as e:
            logger.error(f"Error parsing feed {source['name']}: {e}")
        
        return news_items
    
    def is_recent(self, entry, max_hours=24):
        """Проверяет, свежая ли новость"""
        try:
            date_str = getattr(entry, 'published', '')
            if not date_str:
                return True
                
            # Простая проверка свежести
            formats = [
                '%a, %d %b %Y %H:%M:%S %Z',
                '%a, %d %b %Y %H:%M:%S %z',
                '%Y-%m-%dT%H:%M:%SZ'
            ]
            
            for fmt in formats:
                try:
                    news_date = datetime.strptime(date_str, fmt)
                    time_diff = datetime.now() - news_date
                    return time_diff.total_seconds() / 3600 <= max_hours
                except:
                    continue
                    
            return True
        except:
            return True
    
    def is_fashion_related(self, entry):
        """Проверяет, относится ли новость к моде"""
        content = f"{entry.title} {getattr(entry, 'summary', '')}".lower()
        
        # Ключевые слова для фильтрации
        fashion_keywords = [
            'sneaker', 'collection', 'collaboration', 'release', 'drop',
            'fashion', 'streetwear', 'luxury', 'designer', 'boot',
            'jacket', 'hoodie', 'shoe', 'apparel', 'capsule'
        ]
        
        brand_keywords = [brand.lower() for brand in BRANDS]
        
        return any(keyword in content for keyword in fashion_keywords + brand_keywords)
    
    def process_news(self, news_item):
        """Обрабатывает новость и создает пост"""
        # Проверяем, не отправляли ли уже
        if self.db.is_news_sent(news_item['url']):
            return None
        
        logger.info(f"📝 Processing: {news_item['title']}")
        
        # Извлекаем полный контент
        full_content, images = self.extractor.extract_full_content(news_item['url'])
        
        if not full_content:
            full_content = news_item['summary']
        
        # Переводим
        translated_title = self.translator.translate_text(news_item['title'])
        translated_content = self.translator.translate_text(full_content)
        
        # Обрезаем контент до 100+ слов
        words = translated_content.split()
        if len(words) > 100:
            translated_content = ' '.join(words[:400]) + '...'  # ~100+ слов
        
        # Создаем пост
        post = self.create_post(translated_title, translated_content, news_item, images)
        
        # Помечаем как отправленную
        self.db.mark_news_sent(news_item['url'], news_item['source'], news_item['title'])
        
        return post, images
    
    def create_post(self, title, content, news_item, images):
        """Создает пост для Telegram"""
        # Простой и чистый формат
        post = f"<b>{title}</b>\n\n"
        post += f"{content}\n\n"
        post += f"📰 Источник: {news_item['source']}\n"
        post += f"🔗 <a href='{news_item['url']}'>Читать полностью</a>"
        
        return post
    
    def run(self):
        """Запускает бота"""
        logger.info("🚀 Starting Fashion News Bot")
        
        # Проверяем источники
        all_news = self.check_sources()
        logger.info(f"📰 Found {len(all_news)} new news items")
        
        # Обрабатываем и публикуем каждую новость
        for news_item in all_news:
            try:
                result = self.process_news(news_item)
                if result:
                    post, images = result
                    
                    # Публикуем пост
                    success = self.publisher.send_photo_group(post, images)
                    
                    if success:
                        logger.info(f"✅ Published: {news_item['title'][:50]}...")
                    else:
                        logger.error(f"❌ Failed to publish: {news_item['title'][:50]}...")
                    
                    # Задержка между постами
                    time.sleep(10)
                    
            except Exception as e:
                logger.error(f"❌ Error processing news: {e}")
                continue

if __name__ == "__main__":
    bot = FashionNewsBot()
    bot.run()
    logger.info("✅ Bot finished!")
