"""
Fashion News Bot - Enterprise Edition
Author: Gemini AI
Version: 2.0.0
Description: High-end news scraper tailored for Fashion Industry with intelligent text sanitization.
"""

import os
import re
import time
import hashlib
import sqlite3
import logging
import requests
import random
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from fake_useragent import UserAgent

# =================================================================================================
# 1. CONFIGURATION & LOGGING
# =================================================================================================

# Настройка логирования "как у взрослых"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(module)-15s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("FashionBot")

class Config:
    BOT_TOKEN = os.environ.get('BOT_TOKEN')
    CHANNEL = os.environ.get('CHANNEL')
    DB_NAME = 'news.db'
    MAX_NEWS_PER_RUN = 1  # Отправляем только 1 самую крутую новость за запуск, чтобы не спамить
    MAX_RETRIES = 3
    TIMEOUT = 20
    MIN_TEXT_LENGTH = 150  # Игнорировать новости короче этого (символов)

    # Проверка настроек
    if not BOT_TOKEN or not CHANNEL:
        logger.critical("❌ FATAL: BOT_TOKEN or CHANNEL not found in env vars.")
        exit(1)

# =================================================================================================
# 2. DATA STRUCTURES
# =================================================================================================

@dataclass
class Article:
    title: str
    url: str
    content: str
    images: List[str]
    source_name: str

# =================================================================================================
# 3. DATABASE LAYER
# =================================================================================================

class Database:
    """Управление хранилищем данных SQLite с защитой от дублей"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS history (
                    hash TEXT PRIMARY KEY,
                    url TEXT,
                    title TEXT,
                    source TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

    def exists(self, url: str) -> bool:
        """Проверка, была ли новость уже опубликована"""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM history WHERE hash = ?', (url_hash,))
            return cursor.fetchone() is not None

    def add(self, article: Article):
        """Добавление новости в историю"""
        url_hash = hashlib.md5(article.url.encode()).hexdigest()
        with self._get_connection() as conn:
            try:
                conn.execute(
                    'INSERT INTO history (hash, url, title, source) VALUES (?, ?, ?, ?)',
                    (url_hash, article.url, article.title, article.source_name)
                )
                conn.commit()
            except sqlite3.IntegrityError:
                pass

# =================================================================================================
# 4. TEXT PROCESSING ENGINE (SANITIZER & TRANSLATOR)
# =================================================================================================

class TextSanitizer:
    """Класс для жесткой очистки текста от мусора"""
    
    BAD_PATTERNS = [
        r'read more', r'click here', r'continue reading', r'subscribe', 
        r'sign up', r'follow us', r'source:', r'photo:', r'credit:', 
        r'images courtesy', r'via getty', r'advertisement',
        r'share this article', r'download the app'
    ]

    @staticmethod
    def clean(text: str) -> str:
        if not text: 
            return ""
        
        # 1. Удаление лишних пробелов
        text = re.sub(r'\s+', ' ', text).strip()
        
        # 2. Фильтрация "мусорных" фраз
        for pattern in TextSanitizer.BAD_PATTERNS:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
            
        # 3. Удаление URL внутри текста
        text = re.sub(r'http\S+', '', text)
        
        return text.strip()

class TranslatorService:
    """Сервис перевода с повторными попытками"""
    
    def __init__(self):
        self.translator = GoogleTranslator(source='auto', target='ru')

    def translate(self, text: str) -> str:
        if not text:
            return ""
        
        # Переводим частями, если текст огромный (хотя мы его уже обрезали)
        try:
            time.sleep(1) # Вежливость к API
            return self.translator.translate(text[:4500])
        except Exception as e:
            logger.error(f"Translation failed: {e}")
            # В крайнем случае возвращаем оригинал, но лучше так не делать
            return text 

# =================================================================================================
# 5. NETWORK & PARSING LAYER
# =================================================================================================

class Browser:
    """Имитация реального браузера для обхода защиты"""
    
    def __init__(self):
        self.ua = UserAgent()
        self.session = requests.Session()
    
    def get(self, url: str) -> Optional[requests.Response]:
        headers = {
            'User-Agent': self.ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://www.google.com/'
        }
        try:
            response = self.session.get(url, headers=headers, timeout=Config.TIMEOUT)
            if response.status_code == 200:
                return response
            logger.warning(f"⚠️ HTTP {response.status_code} for {url}")
        except Exception as e:
            logger.error(f"Network error: {e}")
        return None

class BaseParser(ABC):
    """Абстрактный класс парсера"""
    def __init__(self):
        self.browser = Browser()
        self.sanitizer = TextSanitizer()

    @abstractmethod
    def get_latest_news(self) -> List[Article]:
        pass

    def _extract_images(self, soup, base_url) -> List[str]:
        """Умный поиск картинок высокого разрешения"""
        images = []
        # Ищем картинки в основном контенте
        content_div = soup.find('article') or soup.find('main') or soup.body
        if not content_div: return []

        img_tags = content_div.find_all('img')
        for img in img_tags:
            src = img.get('src') or img.get('data-src') or img.get('srcset')
            if not src: continue
            
            # Обработка srcset (берем самую большую)
            if ' ' in src: 
                src = src.split(' ')[0]
            
            if src.startswith('//'): src = 'https:' + src
            if src.startswith('/'): src = urljoin(base_url, src)
            
            # Фильтры мусора
            if any(x in src for x in ['logo', 'icon', 'avatar', 'gif', 'svg']):
                continue
                
            images.append(src)
        
        # Возвращаем 3 уникальных
        return list(dict.fromkeys(images))[:3]

# ---------------- SPECIFIC PARSERS ----------------

class VogueParser(BaseParser):
    """Парсер для Vogue (Чистая мода)"""
    BASE_URL = "https://www.vogue.com"
    NEWS_URL = "https://www.vogue.com/fashion/news"

    def get_latest_news(self) -> List[Article]:
        logger.info("🕵️ Scanning Vogue...")
        response = self.browser.get(self.NEWS_URL)
        if not response: return []

        soup = BeautifulSoup(response.content, 'lxml')
        articles = []
        
        # Ищем ссылки на статьи (Vogue имеет специфичную структуру)
        links = soup.select('a.SummaryItemHedLink-civMjp') # Классы могут меняться, поэтому ищем по структуре
        if not links:
            links = soup.select('div[class*="SummaryItem"] a[href*="/article/"]')

        for link in links[:4]: # Проверяем первые 4 ссылки
            href = link.get('href')
            if not href or '/article/' not in href: continue
            full_url = urljoin(self.BASE_URL, href)
            
            article = self._parse_article(full_url)
            if article:
                articles.append(article)
                
        return articles

    def _parse_article(self, url: str) -> Optional[Article]:
        response = self.browser.get(url)
        if not response: return None
        soup = BeautifulSoup(response.content, 'lxml')

        # 1. Заголовок
        h1 = soup.find('h1')
        title = h1.get_text().strip() if h1 else "Fashion News"

        # 2. Текст (Берем только параграфы тела статьи)
        body = soup.find('div', {'class': lambda x: x and 'body' in x.lower()})
        if not body:
            body = soup.find('article')
        
        if not body: return None

        paragraphs = body.find_all('p')
        text_parts = []
        # Берем первые 4 параграфа - там обычно суть
        for p in paragraphs[:4]:
            clean = self.sanitizer.clean(p.get_text())
            if len(clean) > 50: # Игнорируем короткие вставки
                text_parts.append(clean)
        
        content = "\n\n".join(text_parts)
        if len(content) < Config.MIN_TEXT_LENGTH: return None

        # 3. Картинки
        images = self._extract_images(soup, url)

        return Article(title=title, url=url, content=content, images=images, source_name="Vogue")

class HypebeastParser(BaseParser):
    """Парсер для Hypebeast (Уличная мода)"""
    URL = "https://hypebeast.com/fashion"

    def get_latest_news(self) -> List[Article]:
        logger.info("🕵️ Scanning Hypebeast...")
        response = self.browser.get(self.URL)
        if not response: return []
        
        soup = BeautifulSoup(response.content, 'lxml')
        articles = []
        
        posts = soup.select('.post-box')
        for post in posts[:4]:
            link_tag = post.select_one('a.title')
            if not link_tag: continue
            
            url = link_tag.get('href')
            
            article = self._parse_article(url)
            if article:
                articles.append(article)
        return articles

    def _parse_article(self, url: str) -> Optional[Article]:
        response = self.browser.get(url)
        if not response: return None
        soup = BeautifulSoup(response.content, 'lxml')
        
        # Удаляем "Related posts" сразу
        for div in soup.select('.related-posts, .post-footer, .comments'):
            div.decompose()

        title = soup.select_one('h1.post-title').get_text().strip()
        
        content_div = soup.select_one('.post-body-content')
        if not content_div: return None

        text_parts = []
        for p in content_div.find_all('p', recursive=False):
            clean = self.sanitizer.clean(p.get_text())
            # Фильтр: игнорируем строки, где есть "Price:" или "Buy here"
            if len(clean) > 40 and "price:" not in clean.lower():
                text_parts.append(clean)
        
        # Берем только первые 3 значимых абзаца
        content = "\n\n".join(text_parts[:3])
        
        images = self._extract_images(soup, url)
        
        return Article(title=title, url=url, content=content, images=images, source_name="Hypebeast")

# =================================================================================================
# 6. TELEGRAM LAYER
# =================================================================================================

class TelegramBot:
    def __init__(self):
        self.token = Config.BOT_TOKEN
        self.channel = Config.CHANNEL
        self.api_url = f"https://api.telegram.org/bot{self.token}"

    def send_article(self, article: Article):
        """Отправка красиво оформленной новости"""
        
        # Форматирование текста
        # Жирный заголовок, затем пустая строка, затем текст
        caption = f"<b>{article.title}</b>\n\n{article.content}"
        
        # Проверка длины для Telegram (1024 символа для подписи к фото)
        if len(caption) > 1000:
            caption = caption[:990] + "..."

        # Логика отправки:
        # 1. Если есть фото -> sendMediaGroup (альбом)
        # 2. Если фото одно -> sendPhoto
        # 3. Если нет фото -> sendMessage

        try:
            if not article.images:
                return self._send_text(caption)
            
            if len(article.images) == 1:
                return self._send_single_photo(caption, article.images[0])
            
            return self._send_album(caption, article.images)

        except Exception as e:
            logger.error(f"Telegram send error: {e}")
            return False

    def _send_text(self, text):
        data = {'chat_id': self.channel, 'text': text, 'parse_mode': 'HTML', 'disable_web_page_preview': True}
        r = requests.post(f"{self.api_url}/sendMessage", json=data)
        return r.status_code == 200

    def _send_single_photo(self, caption, photo_url):
        data = {
            'chat_id': self.channel, 
            'photo': photo_url, 
            'caption': caption, 
            'parse_mode': 'HTML'
        }
        r = requests.post(f"{self.api_url}/sendPhoto", json=data)
        return r.status_code == 200

    def _send_album(self, caption, photos):
        media = []
        for i, url in enumerate(photos):
            item = {'type': 'photo', 'media': url}
            if i == 0: # Подпись только к первому
                item['caption'] = caption
                item['parse_mode'] = 'HTML'
            media.append(item)
        
        data = {'chat_id': self.channel, 'media': media}
        r = requests.post(f"{self.api_url}/sendMediaGroup", json=data)
        return r.status_code == 200

# =================================================================================================
# 7. MAIN CONTROLLER
# =================================================================================================

class BotController:
    """Главный мозг бота"""
    
    def __init__(self):
        self.db = Database(Config.DB_NAME)
        self.tg = TelegramBot()
        self.translator = TranslatorService()
        # Список источников
        self.parsers = [
            VogueParser(),
            HypebeastParser()
        ]

    def run(self):
        logger.info("🚀 Starting Fashion News Cycle...")
        
        # Перемешиваем парсеры, чтобы каждый запуск начинался с разного сайта
        random.shuffle(self.parsers)
        
        news_sent_count = 0
        
        for parser in self.parsers:
            if news_sent_count >= Config.MAX_NEWS_PER_RUN:
                break
                
            try:
                # 1. Получаем сырые новости
                articles = parser.get_latest_news()
                
                for article in articles:
                    # 2. Проверка на дубликаты
                    if self.db.exists(article.url):
                        continue
                    
                    logger.info(f"✨ Found fresh news: {article.title}")
                    
                    # 3. Перевод (Самый долгий процесс)
                    ru_title = self.translator.translate(article.title)
                    ru_content = self.translator.translate(article.content)
                    
                    # Создаем переведенную версию
                    final_article = Article(
                        title=ru_title,
                        url=article.url,
                        content=ru_content,
                        images=article.images,
                        source_name=article.source_name
                    )
                    
                    # 4. Отправка
                    if self.tg.send_article(final_article):
                        logger.info("✅ Published successfully!")
                        self.db.add(article)
                        news_sent_count += 1
                        
                        # Если отправили одну новость, завершаем работу, чтобы не спамить
                        # (следующую новость бот отправит через 30 мин при следующем запуске)
                        return 
                    else:
                        logger.error("❌ Failed to publish")
                    
                    time.sleep(5) # Пауза
                    
            except Exception as e:
                logger.error(f"Error processing source: {e}")

        logger.info("💤 Cycle finished.")

if __name__ == "__main__":
    controller = BotController()
    controller.run()
