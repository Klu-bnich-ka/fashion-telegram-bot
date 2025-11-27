import requests
import os
import re
import time
import hashlib
import sqlite3
import logging
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import feedparser
from deep_translator import GoogleTranslator

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Проверка переменных окружения
BOT_TOKEN = os.environ.get('BOT_TOKEN')
CHANNEL = os.environ.get('CHANNEL')

if not BOT_TOKEN or not CHANNEL:
    logger.error("❌ BOT_TOKEN или CHANNEL не найдены в Secrets!")
    exit(1)

MAX_IMAGES = 3
MAX_NEWS = 3

SOURCES = [
    {'name': 'Hypebeast', 'url': 'https://hypebeast.com/fashion/feed', 'base_url': 'https://hypebeast.com'},
    {'name': 'Highsnobiety', 'url': 'https://www.highsnobiety.com/feed/', 'base_url': 'https://www.highsnobiety.com'},
    {'name': 'Sneaker News', 'url': 'https://sneakernews.com/feed/', 'base_url': 'https://sneakernews.com'}
]

# --- Database ---
class DatabaseManager:
    def __init__(self):
        self.db_file = 'news.db'
        self.init_database()

    def init_database(self):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sent_news (
                url_hash TEXT PRIMARY KEY,
                title TEXT,
                sent_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()

    def is_news_sent(self, url):
        url_hash = hashlib.md5(url.encode()).hexdigest()
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM sent_news WHERE url_hash = ?', (url_hash,))
        result = cursor.fetchone() is not None
        conn.close()
        return result

    def mark_news_sent(self, url, title):
        url_hash = hashlib.md5(url.encode()).hexdigest()
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT OR IGNORE INTO sent_news (url_hash, title) VALUES (?, ?)', (url_hash, title[:200]))
            conn.commit()
        except Exception as e:
            logger.error(f"DB Error: {e}")
        conn.close()

# --- Content ---
class ContentProcessor:
    def __init__(self):
        # Используем deep-translator, он стабильнее
        self.translator = GoogleTranslator(source='auto', target='ru')

    def translate_text(self, text):
        if not text:
            return ""
        try:
            # Разбиваем текст, если он слишком длинный (лимит 5000)
            if len(text) > 4500:
                text = text[:4500]
            return self.translator.translate(text)
        except Exception as e:
            logger.warning(f"Translation warning: {e}")
            return text

    def clean_text(self, text):
        if not text: return ""
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'http\S+', '', text)
        return text.strip()

class SmartContentExtractor:
    def __init__(self):
        self.session = requests.Session()
        # Имитируем настоящий браузер Chrome на Windows
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5'
        })
        self.processor = ContentProcessor()

    def extract_content(self, url):
        try:
            response = self.session.get(url, timeout=15)
            if response.status_code != 200:
                logger.warning(f"⚠️ Status {response.status_code} for {url}")
                return None, []
            
            soup = BeautifulSoup(response.content, 'lxml')
            
            # Чистка
            for el in soup.find_all(['script', 'style', 'nav', 'footer', 'aside', 'iframe', 'ads']):
                el.decompose()

            article = self.find_article(soup)
            text = ""
            if article:
                text = self.processor.clean_text(article.get_text())
            
            images = self.extract_images(soup, url)
            return text, images
        except Exception as e:
            logger.error(f"Error extracting content: {e}")
            return None, []

    def find_article(self, soup):
        selectors = ['article', 'div[class*="content"]', 'div[class*="post"]', 'main']
        for sel in selectors:
            el = soup.select_one(sel)
            if el and len(el.get_text()) > 100:
                return el
        return soup.find('body')

    def extract_images(self, soup, base_url):
        images = []
        # Расширенный поиск картинок
        imgs = soup.find_all('img')
        for img in imgs:
            src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
            if src and 'avatar' not in src and 'logo' not in src and 'icon' not in src:
                if src.startswith('//'):
                    src = 'https:' + src
                full_url = urljoin(base_url, src)
                # Фильтруем мелкие иконки по расширению
                if full_url.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                    images.append(full_url)
        
        # Удаляем дубликаты сохраняя порядок
        seen = set()
        unique = []
        for x in images:
            if x not in seen:
                unique.append(x)
                seen.add(x)
        return unique[:MAX_IMAGES]

# --- Telegram ---
class TelegramPublisher:
    def __init__(self, token, channel):
        self.token = token
        self.channel = channel
        self.session = requests.Session()

    def send_photo_group(self, caption, photo_urls):
        # Если картинок нет, шлем просто текст
        if not photo_urls:
            return self.send_message(caption)

        media = []
        # Телеграм требует чтобы caption был только у первого элемента
        for i, url in enumerate(photo_urls):
            media_item = {
                "type": "photo",
                "media": url
            }
            if i == 0:
                media_item["caption"] = caption
                media_item["parse_mode"] = "HTML"
            media.append(media_item)

        url_api = f"https://api.telegram.org/bot{self.token}/sendMediaGroup"
        try:
            # Логируем попытку отправки
            logger.info(f"📤 Sending album to {self.channel}")
            response = self.session.post(url_api, json={"chat_id": self.channel, "media": media}, timeout=30)
            
            if response.status_code != 200:
                logger.error(f"Telegram Error: {response.text}")
                # Если не получилось отправить альбом (например битая ссылка), пробуем текст
                return self.send_message(caption)
            return True
        except Exception as e:
            logger.error(f"Network error sending media: {e}")
            return False

    def send_message(self, text):
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        data = {'chat_id': self.channel, 'text': text, 'parse_mode': 'HTML', 'disable_web_page_preview': False}
        try:
            r = self.session.post(url, json=data)
            if r.status_code != 200:
                logger.error(f"Telegram Text Error: {r.text}")
            return r.status_code == 200
        except Exception:
            return False

# --- Main ---
class FashionNewsBot:
    def __init__(self):
        self.db = DatabaseManager()
        self.extractor = SmartContentExtractor()
        self.publisher = TelegramPublisher(BOT_TOKEN, CHANNEL)
        self.processor = ContentProcessor()

    def run(self):
        logger.info("🚀 Bot started processing...")
        
        # Получаем новости
        all_entries = []
        for source in SOURCES:
            logger.info(f"Checking {source['name']}...")
            try:
                feed = feedparser.parse(source['url'])
                if not feed.entries:
                    logger.warning(f"Empty feed for {source['name']}")
                    continue
                    
                for entry in feed.entries[:5]: # Берем только 5 свежих
                    all_entries.append(entry)
            except Exception as e:
                logger.error(f"Feed error: {e}")

        logger.info(f"Total entries found: {len(all_entries)}")
        
        sent_count = 0
        for entry in all_entries:
            if sent_count >= MAX_NEWS:
                break
                
            url = entry.link
            title = entry.title
            
            if self.db.is_news_sent(url):
                logger.info(f"Skipping (already sent): {title[:30]}")
                continue

            # Обработка
            logger.info(f"Processing new: {title}")
            
            # Получаем контент
            text, images = self.extractor.extract_content(url)
            
            # Если парсер не смог достать текст, берем из RSS
            if not text or len(text) < 50:
                summary = getattr(entry, 'summary', '') or getattr(entry, 'description', '')
                text = BeautifulSoup(summary, "lxml").get_text()

            # Перевод
            title_ru = self.processor.translate_text(title)
            text_ru = self.processor.translate_text(text)
            
            # Формирование поста
            post = f"<b>{title_ru}</b>\n\n"
            post += f"{text_ru[:800]}..." # Обрезаем, чтобы влезло
            post += f"\n\n<a href='{url}'>Читать оригинал</a>"

            # Отправка
            if self.publisher.send_photo_group(post, images):
                self.db.mark_news_sent(url, title)
                sent_count += 1
                logger.info("✅ Successfully sent")
                time.sleep(5) # Пауза чтобы не забанил ТГ
            else:
                logger.error("❌ Failed to send")

if __name__ == "__main__":
    FashionNewsBot().run()
