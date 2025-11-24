import requests
import os
import re
import time
import logging
import hashlib
import sqlite3
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import feedparser
from datetime import datetime
from googletrans import Translator

# --- Логирование ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Настройки ---
BOT_TOKEN = os.environ['BOT_TOKEN']
CHANNEL = os.environ['CHANNEL']

SOURCES = [
    {'name': 'Hypebeast', 'url': 'https://hypebeast.com/fashion/feed', 'base_url': 'https://hypebeast.com'},
    {'name': 'Highsnobiety', 'url': 'https://www.highsnobiety.com/feed/', 'base_url': 'https://www.highsnobiety.com'},
    {'name': 'Sneaker News', 'url': 'https://sneakernews.com/feed/', 'base_url': 'https://sneakernews.com'}
]

MAX_NEWS_PER_RUN = 3
MAX_IMAGES = 3

# --- Переводчик ---
translator = Translator()

# --- База данных ---
class DatabaseManager:
    def __init__(self):
        self.init_db()
    
    def init_db(self):
        conn = sqlite3.connect('news.db')
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sent_news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url_hash TEXT UNIQUE,
                sent_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()

    def is_sent(self, url):
        url_hash = hashlib.md5(url.encode()).hexdigest()
        conn = sqlite3.connect('news.db')
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM sent_news WHERE url_hash=?', (url_hash,))
        result = cursor.fetchone() is not None
        conn.close()
        return result

    def mark_sent(self, url):
        url_hash = hashlib.md5(url.encode()).hexdigest()
        conn = sqlite3.connect('news.db')
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO sent_news (url_hash) VALUES (?)', (url_hash,))
            conn.commit()
        except sqlite3.IntegrityError:
            pass
        conn.close()

# --- Telegram ---
class TelegramPublisher:
    def __init__(self, token, channel):
        self.token = token
        self.channel = channel
        self.session = requests.Session()

    def send_photo_group(self, caption, photo_urls):
        if not photo_urls:
            return self.send_message(caption)

        # Первая фото с подписью
        first_photo = photo_urls[0]
        try:
            response = self.session.get(first_photo, timeout=10)
            if response.status_code != 200:
                return self.send_message(caption)

            files = {'photo': ('image.jpg', response.content, 'image/jpeg')}
            data = {'chat_id': self.channel, 'caption': caption, 'parse_mode': 'HTML'}
            url = f'https://api.telegram.org/bot{self.token}/sendPhoto'
            self.session.post(url, files=files, data=data, timeout=30)

            # Остальные фото без подписи
            for photo_url in photo_urls[1:MAX_IMAGES]:
                resp = self.session.get(photo_url, timeout=10)
                if resp.status_code == 200:
                    files = {'photo': ('image.jpg', resp.content, 'image/jpeg')}
                    data = {'chat_id': self.channel}
                    self.session.post(url, files=files, data=data, timeout=30)
                    time.sleep(1)
            return True
        except Exception as e:
            logger.error(f"Error sending photos: {e}")
            return False

    def send_message(self, text):
        url = f'https://api.telegram.org/bot{self.token}/sendMessage'
        data = {'chat_id': self.channel, 'text': text, 'parse_mode': 'HTML', 'disable_web_page_preview': False}
        try:
            resp = self.session.post(url, json=data, timeout=30)
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False

# --- Контент ---
class ContentExtractor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent':'Mozilla/5.0'})
    
    def fetch_article(self, url, base_url):
        try:
            r = self.session.get(url, timeout=10)
            soup = BeautifulSoup(r.content, 'html.parser')
            # Очистка
            for tag in soup(['script','style','nav','footer','aside','form']):
                tag.decompose()
            text = soup.get_text(separator=' ', strip=True)
            images = self.get_images(soup, url)
            return text, images
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return "", []

    def get_images(self, soup, base_url):
        images = []
        for img in soup.find_all('img'):
            src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
            if src:
                if src.startswith('/'):
                    src = urljoin(base_url, src)
                if src.lower().endswith(('jpg','jpeg','png','webp')):
                    images.append(src)
            if len(images) >= MAX_IMAGES:
                break
        return images

# --- Выделение ключевых слов ---
def highlight_key_points(text):
    key_phrases = [
        'коллаборация', 'релиз', 'лимитированн', 'эксклюзивн',
        'новый модель', 'впервые', 'ограниченный тираж',
        'специальный выпуск', 'капсульная коллекция'
    ]
    for phrase in key_phrases:
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        text = pattern.sub(lambda m: f"<b>{m.group(0)}</b>", text)
    return text

# --- Бот ---
class FashionNewsBot:
    def __init__(self):
        self.db = DatabaseManager()
        self.publisher = TelegramPublisher(BOT_TOKEN, CHANNEL)
        self.extractor = ContentExtractor()

    def run(self):
        all_news = []
        for source in SOURCES:
            try:
                feed = feedparser.parse(source['url'])
                for entry in feed.entries[:15]:
                    if self.is_recent(entry) and self.is_fashion_related(entry):
                        all_news.append({
                            'title': entry.title,
                            'url': entry.link,
                            'summary': getattr(entry, 'summary', '')[:300]
                        })
            except Exception as e:
                logger.error(f"Error parsing {source['name']}: {e}")

        # Сортировка по "важности": ключевые слова в заголовке
        all_news.sort(key=lambda x: self.score_news(x['title']), reverse=True)

        sent_count = 0
        for news in all_news:
            if sent_count >= MAX_NEWS_PER_RUN:
                break
            if self.db.is_sent(news['url']):
                continue

            # Контент
            text, images = self.extractor.fetch_article(news['url'], news['url'])
            if not text:
                text = news['summary']

            # Перевод
            try:
                translated_title = translator.translate(news['title'], dest='ru').text
                translated_text = translator.translate(text, dest='ru').text
            except:
                translated_title = news['title']
                translated_text = text

            # Выделение ключевых слов
            translated_text = highlight_key_points(translated_text)

            # Формируем пост
            post = f"<b>{translated_title}</b>\n\n{translated_text}"

            # Отправка
            success = self.publisher.send_photo_group(post, images)
            if success:
                self.db.mark_sent(news['url'])
                sent_count += 1
                logger.info(f"Published: {translated_title[:50]}...")

    def is_recent(self, entry, hours=24):
        date_str = getattr(entry, 'published', '')
        if not date_str:
            return True
        for fmt in ['%a, %d %b %Y %H:%M:%S %Z','%a, %d %b %Y %H:%M:%S %z','%Y-%m-%dT%H:%M:%SZ']:
            try:
                dt = datetime.strptime(date_str, fmt)
                return (datetime.now() - dt).total_seconds() / 3600 <= hours
            except:
                continue
        return True

    def is_fashion_related(self, entry):
        content = f"{entry.title} {getattr(entry, 'summary','')}".lower()
        keywords = ['sneaker','collection','collaboration','release','drop','fashion','streetwear','luxury','designer','boot','jacket','hoodie','shoe','apparel','capsule']
        return any(k in content for k in keywords)

    def score_news(self, title):
        score = 0
        important_keywords = ['release','collaboration','limited','exclusive','new','collection','drop','launch']
        for kw in important_keywords:
            if kw in title.lower():
                score += 5
        return score

if __name__ == "__main__":
    bot = FashionNewsBot()
    bot.run()
    logger.info("Bot finished!")
