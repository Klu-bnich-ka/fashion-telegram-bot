"""
Fashion News Bot - Stable RSS Edition
Author: Gemini AI
"""

import os
import re
import time
import hashlib
import sqlite3
import logging
import requests
import feedparser
import random
from typing import List, Optional
from dataclasses import dataclass
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from fake_useragent import UserAgent

# ================= CONFIG =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("Bot")

BOT_TOKEN = os.environ.get('BOT_TOKEN')
CHANNEL = os.environ.get('CHANNEL')
DB_NAME = 'news.db'

# Список надежных RSS лент (Мода)
RSS_SOURCES = [
    # Vogue (Официальный RSS)
    {'name': 'Vogue', 'url': 'https://www.vogue.com/feed/rss'},
    # Fashionista (Очень дружелюбный сайт)
    {'name': 'Fashionista', 'url': 'https://fashionista.com/.rss/full/'},
    # The Guardian Fashion (Всегда работает)
    {'name': 'Guardian', 'url': 'https://www.theguardian.com/fashion/rss'},
    # Hypebeast (RSS версия, ее не блочат)
    {'name': 'Hypebeast', 'url': 'https://hypebeast.com/fashion/feed'}
]

@dataclass
class Article:
    title: str
    url: str
    content: str
    images: List[str]
    source: str

# ================= DATABASE =================
class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_NAME)
        self.cursor = self.conn.cursor()
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS history (
                hash TEXT PRIMARY KEY,
                title TEXT,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.commit()

    def exists(self, url):
        h = hashlib.md5(url.encode()).hexdigest()
        res = self.cursor.execute('SELECT 1 FROM history WHERE hash = ?', (h,)).fetchone()
        return res is not None

    def add(self, url, title):
        h = hashlib.md5(url.encode()).hexdigest()
        try:
            self.cursor.execute('INSERT INTO history (hash, title) VALUES (?, ?)', (h, title))
            self.conn.commit()
        except:
            pass

# ================= TOOLS =================
class TextSanitizer:
    @staticmethod
    def clean(text):
        if not text: return ""
        # Убираем HTML теги
        text = BeautifulSoup(text, "lxml").get_text(separator=' ')
        # Убираем мусор
        bad_phrases = ['Read more', 'Source:', 'Photo:', 'Courtesy of', 'Click here', 'Subscribe']
        for phrase in bad_phrases:
            text = re.sub(phrase, '', text, flags=re.IGNORECASE)
        # Убираем лишние пробелы
        text = re.sub(r'\s+', ' ', text).strip()
        return text

class Extractor:
    def __init__(self):
        self.ua = UserAgent()
        self.session = requests.Session()
        self.translator = GoogleTranslator(source='auto', target='ru')

    def get_full_content(self, url):
        """Заходит на страницу, чтобы найти картинки и полный текст"""
        try:
            headers = {'User-Agent': self.ua.random}
            resp = self.session.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                return None, []
            
            soup = BeautifulSoup(resp.content, 'lxml')
            
            # --- Поиск картинок ---
            images = []
            # Ищем большие картинки в теле статьи
            for img in soup.find_all('img'):
                src = img.get('src') or img.get('data-src')
                if not src: continue
                if src.startswith('//'): src = 'https:' + src
                if not src.startswith('http'): src = urljoin(url, src)
                
                # Фильтр мелких иконок
                if any(x in src.lower() for x in ['logo', 'avatar', 'icon', 'svg', 'pixel']):
                    continue
                if src not in images:
                    images.append(src)
            
            # --- Поиск текста (если RSS дал мало) ---
            # Пытаемся найти основной контейнер
            article_body = soup.find('article') or soup.find('main') or soup.find('div', class_=re.compile('content|post'))
            full_text = ""
            if article_body:
                paragraphs = article_body.find_all('p')
                # Берем первые 5 параграфов
                text_parts = [p.get_text() for p in paragraphs[:5] if len(p.get_text()) > 50]
                full_text = " ".join(text_parts)

            return full_text, images[:3] # Макс 3 картинки
        except Exception as e:
            logger.error(f"Extractor error: {e}")
            return None, []

    def translate(self, text):
        try:
            if len(text) > 4000: text = text[:4000]
            return self.translator.translate(text)
        except:
            return text

# ================= TELEGRAM =================
class TelegramSender:
    def __init__(self):
        self.api = f"https://api.telegram.org/bot{BOT_TOKEN}"

    def send(self, article: Article):
        # Подпись
        caption = f"<b>{article.title}</b>\n\n{article.content[:900]}"
        if len(article.content) > 900: caption += "..."
        
        data = {'chat_id': CHANNEL, 'parse_mode': 'HTML'}
        
        # Если есть картинки, шлем альбом (или одну)
        if article.images:
            if len(article.images) == 1:
                data['photo'] = article.images[0]
                data['caption'] = caption
                requests.post(f"{self.api}/sendPhoto", json=data)
                return True
            else:
                # Альбом
                media = []
                for i, img in enumerate(article.images):
                    item = {'type': 'photo', 'media': img}
                    if i == 0: 
                        item['caption'] = caption
                        item['parse_mode'] = 'HTML'
                    media.append(item)
                r = requests.post(f"{self.api}/sendMediaGroup", json={'chat_id': CHANNEL, 'media': media})
                if r.status_code == 200: return True
                # Если альбом не прошел (битая картинка), пробуем просто текст
        
        # Фолбек: просто текст
        data['text'] = caption
        requests.post(f"{self.api}/sendMessage", json=data)
        return True

# ================= MAIN =================
def run():
    logger.info("🚀 Bot started (RSS Mode)")
    if not BOT_TOKEN or not CHANNEL:
        logger.error("No token/channel")
        return

    db = Database()
    extractor = Extractor()
    sender = TelegramSender()
    sanitizer = TextSanitizer()

    # Перемешиваем источники
    random.shuffle(RSS_SOURCES)
    
    news_sent = 0
    
    for source in RSS_SOURCES:
        if news_sent >= 1: break # 1 новость за запуск

        logger.info(f"📡 Checking {source['name']}...")
        try:
            feed = feedparser.parse(source['url'])
            if not feed.entries:
                logger.warning(f"Empty feed for {source['name']}")
                continue

            # Проверяем новости
            for entry in feed.entries[:3]:
                url = entry.link
                title = entry.title
                
                if db.exists(url):
                    continue
                
                logger.info(f"Found new: {title}")
                
                # 1. Достаем контент
                # Сначала берем то, что в RSS
                raw_summary = getattr(entry, 'summary', '') or getattr(entry, 'description', '')
                
                # Пытаемся улучшить (скачать с сайта)
                site_text, site_images = extractor.get_full_content(url)
                
                # Выбираем лучший текст (с сайта или из RSS)
                content_en = site_text if site_text and len(site_text) > len(raw_summary) else raw_summary
                
                # Чистим
                content_en = sanitizer.clean(content_en)
                if len(content_en) < 100: # Слишком коротко
                    logger.info("Content too short, skipping")
                    continue

                # 2. Переводим
                logger.info("Translating...")
                title_ru = extractor.translate(title)
                content_ru = extractor.translate(content_en)
                
                # 3. Отправляем
                article = Article(title_ru, url, content_ru, site_images, source['name'])
                if sender.send(article):
                    logger.info("✅ Sent!")
                    db.add(url, title)
                    news_sent += 1
                    break # Выходим из цикла статей, идем к следующему запуску
                else:
                    logger.error("Failed to send")
                
                time.sleep(5)

        except Exception as e:
            logger.error(f"Error parsing {source['name']}: {e}")

if __name__ == "__main__":
    run()
