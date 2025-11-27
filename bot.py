"""
Fashion News Bot - Final Enterprise-Grade Version
Author: Gemini AI
Version: 3.0 (The Image Hunter)
Description: Stable RSS parsing with aggressive content filtering and multi-level image extraction.
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
import json
from typing import List, Optional, Tuple, Set
from dataclasses import dataclass
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from fake_useragent import UserAgent

# ================= 1. CONFIGURATION & LOGGING =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("Bot")

# Глобальные настройки
BOT_TOKEN = os.environ.get('BOT_TOKEN')
CHANNEL = os.environ.get('CHANNEL')
DB_NAME = 'news.db'

# Список надежных RSS лент для моды
RSS_SOURCES = [
    {'name': 'Vogue', 'url': 'https://www.vogue.com/feed/rss'},
    {'name': 'Fashionista', 'url': 'https://fashionista.com/.rss/full/'},
    {'name': 'Hypebeast', 'url': 'https://hypebeast.com/fashion/feed'},
    {'name': 'Guardian Fashion', 'url': 'https://www.theguardian.com/fashion/rss'}
]

# Ключевые слова для фильтрации новостей
FASHION_KEYWORDS = [
    'fashion house', 'collaboration', 'collab', 'clothing', 
    'drop', 'collection', 'brand', 'designer', 'runway', 
    'couture', 'ready-to-wear', 'capsule', 'sneaker', 'apparel',
    'мода', 'дроп', 'коллекция', 'бренд', 'дизайнер', 'одежда', 'кроссовки'
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

# ================= 2. DATABASE LAYER =================
class Database:
    """Обработчик базы данных для хранения истории публикаций."""
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
        """Проверяет, была ли новость с этим URL уже опубликована."""
        h = hashlib.md5(url.encode()).hexdigest()
        res = self.cursor.execute('SELECT 1 FROM history WHERE hash = ?', (h,)).fetchone()
        return res is not None

    def add(self, url: str, title: str):
        """Добавляет новость в историю."""
        h = hashlib.md5(url.encode()).hexdigest()
        try:
            self.cursor.execute('INSERT OR IGNORE INTO history (hash, title) VALUES (?, ?)', (h, title))
            self.conn.commit()
        except Exception as e:
            logger.error(f"DB add error: {e}")

# ================= 3. TOOLS: SANITIZER & TRANSLATOR =================
class TextSanitizer:
    """Очистка текста от служебных фраз и HTML-тегов."""
    @staticmethod
    def clean(text: str) -> str:
        if not text: return ""
        text = BeautifulSoup(text, "lxml").get_text(separator=' ')
        bad_phrases = ['Read more', 'Source:', 'Photo:', 'Courtesy of', 'Click here', 
                       'Subscribe', 'Advertisement', 'Image Credit', 'Shop Now', 'Share this article']
        for phrase in bad_phrases:
            text = re.sub(phrase, '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

class TranslatorService:
    """Сервис перевода через Google Translator."""
    def __init__(self):
        self.translator = GoogleTranslator(source='auto', target='ru')

    def translate(self, text: str) -> str:
        """Переводит текст с паузой для стабильности."""
        try:
            if not text: return ""
            if len(text) > 4000: text = text[:4000]
            time.sleep(1) 
            return self.translator.translate(text)
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return text

# ================= 4. CONTENT EXTRACTOR (THE IMAGE HUNTER) =================
class Extractor:
    """Извлекает текст и изображения из статьи с агрессивным поиском фото."""
    def __init__(self):
        self.ua = UserAgent()
        self.session = requests.Session()
        self.sanitizer = TextSanitizer()

    def _get_article_soup(self, url: str) -> Optional[BeautifulSoup]:
        """Загружает страницу и удаляет мусорные блоки."""
        try:
            headers = {'User-Agent': self.ua.random, 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9'}
            resp = self.session.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"⚠️ Failed to load content (HTTP {resp.status_code}) from {url}")
                return None
            
            soup = BeautifulSoup(resp.content, 'lxml')
            for el in soup.find_all(['script', 'style', 'nav', 'footer', 'aside', 'iframe', 'header', '.ad', '.sidebar', '.paywall']):
                if el: el.decompose()
            return soup
        except Exception as e:
            logger.error(f"Network or Soup error: {e}")
            return None

    def _clean_image_url(self, src: str, base_url: str) -> Optional[str]:
        """Нормализует, чистит и проверяет URL изображения."""
        if not src: return None
        
        # Если это srcset, берем первую (самую большую) ссылку
        if ' ' in src and ',' in src: 
            src = src.split(',')[0].strip().split(' ')[0]
        
        # Нормализация протокола
        if src.startswith('//'): src = 'https:' + src
        if not src.startswith('http'): src = urljoin(base_url, src)

        # Фильтр мусора и проверка формата
        if any(x in src.lower() for x in ['logo', 'icon', 'avatar', 'svg', 'thumb', 'small', 'ads', 'gif']):
            return None
        if not src.endswith(('.jpg', '.jpeg', '.png', '.webp', '.avif')):
            return None
            
        return src

    def _find_all_images(self, soup: BeautifulSoup, url: str) -> Set[str]:
        """<-- САМЫЙ ВАЖНЫЙ БЛОК: МНОГОУРОВНЕВЫЙ ПОИСК КАРТИНОК -->"""
        images: Set[str] = set()
        
        # 1. Поиск в мета-тегах (самый надежный способ найти главное фото)
        # og:image (Facebook/Open Graph)
        og_image = soup.find('meta', property='og:image')
        if og_image and og_image.get('content'):
            clean_src = self._clean_image_url(og_image['content'], url)
            if clean_src: images.add(clean_src)

        # 2. Поиск в JSON-LD (Schema.org, часто используется Google)
        try:
            scripts = soup.find_all('script', type='application/ld+json')
            for script in scripts:
                data = json.loads(script.string)
                if isinstance(data, dict) and data.get('image'):
                    img_data = data['image']
                    if isinstance(img_data, str):
                        clean_src = self._clean_image_url(img_data, url)
                        if clean_src: images.add(clean_src)
                    elif isinstance(img_data, dict) and img_data.get('url'):
                        clean_src = self._clean_image_url(img_data['url'], url)
                        if clean_src: images.add(clean_src)
        except:
            pass
        
        # 3. Агрессивный поиск в HTML-теле статьи
        article_body = soup.find('article') or soup.find('main') or soup.body
        if article_body:
            # Селекторы, которые ищут изображения во всех возможных местах
            img_tags = article_body.select('picture img, figure img, img[data-src], img[srcset], img')
            
            for tag in img_tags:
                src = tag.get('data-src') or tag.get('srcset') or tag.get('src')
                if src:
                    clean_src = self._clean_image_url(src, url)
                    if clean_src: images.add(clean_src)
                    
        return images

    def get_full_content(self, url: str) -> Tuple[Optional[str], List[str]]:
        """Извлекает текст (сокращено до 3 абзацев) и изображения из статьи."""
        soup = self._get_article_soup(url)
        if not soup: return None, []
        
        article_body = soup.find('article') or soup.find('main') or soup.body

        # 1. Поиск текста (берем первые 3 содержательных параграфа)
        full_text = ""
        if article_body:
            paragraphs = article_body.find_all('p')
            text_parts = [self.sanitizer.clean(p.get_text()) for p in paragraphs if len(p.get_text()) > 50][:3]
            full_text = "\n\n".join(text_parts)

        # 2. Поиск картинок
        raw_images = self._find_all_images(soup, url)
        
        # 3. Выборка: берем не более 3 изображений
        final_images = list(raw_images)[:3]
        logger.info(f"🖼️ Successfully extracted {len(final_images)} images from {url}")
        
        return full_text, final_images

# ================= 5. TELEGRAM SENDER =================
class TelegramSender:
    """Отправка сообщения в Telegram с поддержкой фотоальбомов."""
    def __init__(self):
        self.api = f"https://api.telegram.org/bot{BOT_TOKEN}"

    def send(self, article: Article) -> bool:
        """Отправляет статью (фото + текст или только текст)."""
        caption = f"<b>{article.title}</b>\n\n{article.content}"
        
        # Ограничение длины подписи
        MAX_CAPTION_LENGTH = 700 
        if len(caption) > MAX_CAPTION_LENGTH: 
            caption = caption[:(MAX_CAPTION_LENGTH - 4)] + "..."
        
        try:
            if article.images:
                media = []
                # Формируем медиа-группу
                for i, img in enumerate(article.images):
                    item = {'type': 'photo', 'media': img}
                    if i == 0: 
                        item['caption'] = caption
                        item['parse_mode'] = 'HTML'
                    media.append(item)
                
                # Попытка отправки фотоальбома
                r = requests.post(f"{self.api}/sendMediaGroup", json={'chat_id': CHANNEL, 'media': media})
                if r.status_code == 200: 
                    logger.info("Sent via MediaGroup successfully.")
                    return True
                
                logger.warning(f"Failed to send media group. Trying text fallback. Status: {r.status_code}")
            
            # Фолбек: Отправка только текста
            data = {'chat_id': CHANNEL, 'text': caption, 'parse_mode': 'HTML', 'disable_web_page_preview': True}
            r = requests.post(f"{self.api}/sendMessage", json=data)
            return r.status_code == 200

        except Exception as e:
            logger.error(f"Telegram send critical error: {e}")
            return False

# ================= 6. MAIN CONTROLLER =================
def is_relevant(title: str) -> bool:
    """Проверяет, соответствует ли заголовок теме моды/дропов."""
    check_text = title.lower()
    return any(k in check_text for k in FASHION_KEYWORDS)

def run():
    logger.info("🚀 Bot started (Final Enterprise Run)")

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

            # Проверяем до 5 свежих новостей, чтобы найти релевантную
            for entry in feed.entries[:5]: 
                url = entry.link
                title = entry.title
                
                if db.exists(url): continue
                
                # Фильтрация по теме
                if not is_relevant(title):
                    logger.info(f"Title '{title}' is not relevant to drops/collabs. Skipping.")
                    continue
                
                logger.info(f"Found relevant news: {title}")
                
                # 1. Извлечение контента и картинок
                site_text, site_images = extractor.get_full_content(url)
                
                content_en = site_text or getattr(entry, 'summary', '')
                
                if len(content_en) < 150: 
                    logger.info("Content too short, skipping")
                    continue

                # 2. Перевод
                logger.info("Translating...")
                title_ru = translator_service.translate(title)
                content_ru = translator_service.translate(content_en)
                
                # 3. Отправка
                article = Article(title_ru, url, content_ru, site_images, source['name'])
                if sender.send(article):
                    logger.info("✅ Article published successfully!")
                    db.add(url, title)
                    news_sent += 1
                    break # Переходим к следующему запуску
                else:
                    logger.error("❌ Failed to send article data.")
                
                time.sleep(5)

        except Exception as e:
            logger.error(f"Error processing source {source['name']}: {e}")

    logger.info("💤 Cycle finished.")

if __name__ == "__main__":
    run()
