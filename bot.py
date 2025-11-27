"""
Fashion News Bot - Final Stable Version with Content Filtering
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
from typing import List, Optional, Tuple
from dataclasses import dataclass
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from fake_useragent import UserAgent

# ================= CONFIGURATION & LOGGING =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("Bot")

BOT_TOKEN = os.environ.get('BOT_TOKEN')
CHANNEL = os.environ.get('CHANNEL')
DB_NAME = 'news.db'

# Список самых надежных RSS лент для моды
RSS_SOURCES = [
    {'name': 'Vogue', 'url': 'https://www.vogue.com/feed/rss'},
    {'name': 'Fashionista', 'url': 'https://fashionista.com/.rss/full/'},
    {'name': 'Hypebeast', 'url': 'https://hypebeast.com/fashion/feed'},
    {'name': 'Guardian Fashion', 'url': 'https://www.theguardian.com/fashion/rss'}
]

# Ключевые слова для фильтрации новостей (только про дома моды, дропы, коллабы)
FASHION_KEYWORDS = [
    'fashion house', 'collaboration', 'collab', 'clothing', 
    'drop', 'collection', 'brand', 'designer', 'runway', 
    'couture', 'ready-to-wear', 'capsule', 'sneaker', 'apparel'
]

@dataclass
class Article:
    title: str
    url: str
    content: str
    images: List[str]
    source: str

# Проверка переменных окружения
if not BOT_TOKEN or not CHANNEL:
    logger.critical("❌ FATAL: BOT_TOKEN or CHANNEL not found in env vars.")
    exit(1) 

# ================= DATABASE LAYER =================
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

    def exists(self, url: str) -> bool:
        h = hashlib.md5(url.encode()).hexdigest()
        res = self.cursor.execute('SELECT 1 FROM history WHERE hash = ?', (h,)).fetchone()
        return res is not None

    def add(self, url: str, title: str):
        h = hashlib.md5(url.encode()).hexdigest()
        try:
            self.cursor.execute('INSERT OR IGNORE INTO history (hash, title) VALUES (?, ?)', (h, title))
            self.conn.commit()
        except Exception as e:
            logger.error(f"DB add error: {e}")

# ================= TOOLS: SANITIZER & TRANSLATOR =================
class TextSanitizer:
    @staticmethod
    def clean(text: str) -> str:
        if not text: return ""
        # 1. Удаляем HTML теги и получаем чистый текст
        text = BeautifulSoup(text, "lxml").get_text(separator=' ')
        # 2. Убираем мусорные фразы
        bad_phrases = ['Read more', 'Source:', 'Photo:', 'Courtesy of', 'Click here', 
                       'Subscribe', 'Advertisement', 'Image Credit', 'Shop Now']
        for phrase in bad_phrases:
            text = re.sub(phrase, '', text, flags=re.IGNORECASE)
        # 3. Убираем лишние пробелы
        text = re.sub(r'\s+', ' ', text).strip()
        return text

class TranslatorService:
    def __init__(self):
        self.translator = GoogleTranslator(source='auto', target='ru')

    def translate(self, text: str) -> str:
        try:
            if not text: return ""
            if len(text) > 4000: text = text[:4000]
            time.sleep(1) 
            return self.translator.translate(text)
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return text

# ================= CONTENT EXTRACTOR =================
class Extractor:
    def __init__(self):
        self.ua = UserAgent()
        self.session = requests.Session()
        self.sanitizer = TextSanitizer()

    def _get_article_soup(self, url: str) -> Optional[BeautifulSoup]:
        """Получение и очистка HTML статьи"""
        try:
            headers = {'User-Agent': self.ua.random, 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9'}
            resp = self.session.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"⚠️ Failed to load content (HTTP {resp.status_code}) from {url}")
                return None
            
            soup = BeautifulSoup(resp.content, 'lxml')
            
            # Удаляем мусорные блоки до парсинга
            for el in soup.find_all(['script', 'style', 'nav', 'footer', 'aside', 'iframe', 'header', '.ad', '.sidebar']):
                if el: el.decompose()
            
            return soup
        except Exception as e:
            logger.error(f"Network or Soup error: {e}")
            return None

    def get_full_content(self, url: str) -> Tuple[Optional[str], List[str]]:
        """Извлекает текст (сокращено до 3 абзацев) и изображения из статьи."""
        soup = self._get_article_soup(url)
        if not soup: return None, []
        
        # 1. Определение основного контейнера статьи
        article_body = soup.find('article') or soup.find('main') or soup.body

        # 2. Поиск текста (берем первые 3 содержательных параграфа)
        full_text = ""
        if article_body:
            paragraphs = article_body.find_all('p')
            # <--- ИЗМЕНЕНИЕ 1: Сокращение текста до 3 абзацев --->
            text_parts = [self.sanitizer.clean(p.get_text()) for p in paragraphs if len(p.get_text()) > 50][:3]
            full_text = "\n\n".join(text_parts)

        # 3. УСИЛЕННЫЙ ПОИСК КАРТИНОК
        images = []
        
        # Ищем в <picture> и <figure>
        for tag in article_body.select('picture img, figure img, img[data-src], img[srcset]'):
            src = tag.get('data-src') or tag.get('srcset') or tag.get('src')
            if not src: continue
            
            if ' ' in src and ',' in src: 
                src = src.split(',')[0].strip().split(' ')[0]
            
            if src.startswith('//'): src = 'https:' + src
            if not src.startswith('http'): src = urljoin(url, src)

            # Фильтр мусора и проверка формата
            if any(x in src.lower() for x in ['logo', 'icon', 'avatar', 'svg', 'thumb', 'small']):
                continue
            if src.endswith(('.jpg', '.jpeg', '.png', '.webp')) and src not in images:
                images.append(src)

        unique_images = list(dict.fromkeys(images))
        logger.info(f"🖼️ Found {len(unique_images)} unique images for {url}")
        
        return full_text, unique_images[:3]

# ================= TELEGRAM SENDER =================
class TelegramSender:
    def __init__(self):
        self.api = f"https://api.telegram.org/bot{BOT_TOKEN}"

    def send(self, article: Article) -> bool:
        # 1. Форматирование подписи
        caption = f"<b>{article.title}</b>\n\n{article.content}"
        
        # <--- ИЗМЕНЕНИЕ 2: Сокращение подписи в Telegram --->
        MAX_CAPTION_LENGTH = 700 
        if len(caption) > MAX_CAPTION_LENGTH: 
            caption = caption[:(MAX_CAPTION_LENGTH - 4)] + "..."
        
        # 2. Логика отправки
        try:
            # А. Если есть картинки (Отправка альбома)
            if article.images:
                media = []
                for i, img in enumerate(article.images):
                    item = {'type': 'photo', 'media': img}
                    if i == 0: # Подпись только к первому элементу
                        item['caption'] = caption
                        item['parse_mode'] = 'HTML'
                    media.append(item)
                
                r = requests.post(f"{self.api}/sendMediaGroup", json={'chat_id': CHANNEL, 'media': media})
                if r.status_code == 200: return True
                
                logger.warning(f"Failed to send media group. Trying text fallback. Error: {r.text}")
            
            # Б. Фолбек: Отправка только текста
            data = {'chat_id': CHANNEL, 'text': caption, 'parse_mode': 'HTML', 'disable_web_page_preview': True}
            r = requests.post(f"{self.api}/sendMessage", json=data)
            return r.status_code == 200

        except Exception as e:
            logger.error(f"Telegram send critical error: {e}")
            return False

# ================= MAIN CONTROLLER =================

def is_relevant(title: str) -> bool:
    """<--- ИЗМЕНЕНИЕ 3: Проверка на релевантность по ключевым словам --->"""
    check_text = title.lower()
    
    # Если в заголовке есть хотя бы одно ключевое слово, считаем новость релевантной
    return any(k in check_text for k in FASHION_KEYWORDS)


def run():
    logger.info("🚀 Bot started (Final Stable Mode)")

    db = Database()
    extractor = Extractor()
    sender = TelegramSender()
    translator_service = TranslatorService()
    
    random.shuffle(RSS_SOURCES)
    
    news_sent = 0
    MAX_NEWS_PER_RUN = 1 
    
    for source in RSS_SOURCES:
        if news_sent >= MAX_NEWS_PER_RUN: break

        logger.info(f"📡 Checking {source['name']}...")
        try:
            feed = feedparser.parse(source['url'])
            if not feed.entries:
                logger.warning(f"Empty feed for {source['name']}")
                continue

            for entry in feed.entries[:5]: # Проверяем больше новостей, чтобы найти релевантную
                url = entry.link
                title = entry.title
                
                if db.exists(url): continue
                
                # --- Шаг фильтрации ---
                if not is_relevant(title):
                    logger.info(f"Title '{title}' is not relevant to drops/collabs. Skipping.")
                    continue
                
                logger.info(f"Found relevant news: {title}")
                
                # 1. Достаем контент с сайта
                site_text, site_images = extractor.get_full_content(url)
                
                content_en = site_text or getattr(entry, 'summary', '')
                
                if len(content_en) < 150: 
                    logger.info("Content too short, skipping")
                    continue

                # 2. Переводим
                logger.info("Translating...")
                title_ru = translator_service.translate(title)
                content_ru = translator_service.translate(content_en)
                
                # 3. Отправляем
                article = Article(title_ru, url, content_ru, site_images, source['name'])
                if sender.send(article):
                    logger.info("✅ Sent successfully!")
                    db.add(url, title)
                    news_sent += 1
                    break # Переходим к следующему запуску
                else:
                    logger.error("Failed to send article data.")
                
                time.sleep(5)

        except Exception as e:
            logger.error(f"Error processing source {source['name']}: {e}")

    logger.info("💤 Cycle finished.")

if __name__ == "__main__":
    run()
