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
from googletrans import Translator

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ['BOT_TOKEN']
CHANNEL = os.environ['CHANNEL']
MAX_IMAGES = 3  # максимум фото в одной публикации
MAX_NEWS = 3    # максимум новостей за запуск

SOURCES = [
    {'name': 'Hypebeast', 'url': 'https://hypebeast.com/fashion/feed', 'base_url': 'https://hypebeast.com'},
    {'name': 'Highsnobiety', 'url': 'https://www.highsnobiety.com/feed/', 'base_url': 'https://www.highsnobiety.com'},
    {'name': 'Sneaker News', 'url': 'https://sneakernews.com/feed/', 'base_url': 'https://sneakernews.com'}
]

# ------------------- Database Manager -------------------

class DatabaseManager:
    def __init__(self):
        self.init_database()

    def init_database(self):
        conn = sqlite3.connect('news.db')
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sent_news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url_hash TEXT UNIQUE,
                title TEXT,
                sent_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()

    def is_news_sent(self, url):
        url_hash = hashlib.md5(url.encode()).hexdigest()
        conn = sqlite3.connect('news.db')
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM sent_news WHERE url_hash = ?', (url_hash,))
        result = cursor.fetchone() is not None
        conn.close()
        return result

    def mark_news_sent(self, url, title):
        url_hash = hashlib.md5(url.encode()).hexdigest()
        conn = sqlite3.connect('news.db')
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO sent_news (url_hash, title) VALUES (?, ?)', (url_hash, title[:200]))
            conn.commit()
        except sqlite3.IntegrityError:
            pass
        conn.close()

# ------------------- Content Processor -------------------

class ContentProcessor:
    def __init__(self):
        self.translator = Translator()

    def translate_text(self, text):
        try:
            if len(text) > 4000:
                text = text[:4000]
            translated = self.translator.translate(text, dest='ru')
            return translated.text
        except Exception as e:
            logger.warning(f"Translation failed: {e}")
            return text

    def clean_text(self, text):
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\n+', ' ', text)
        technical_phrases = [
            'read more', 'read full article', 'click here', 'continue reading',
            'source:', 'image credit:', 'photo via', 'courtesy of'
        ]
        for phrase in technical_phrases:
            text = re.sub(phrase, '', text, flags=re.IGNORECASE)
        text = re.sub(r'http\S+', '', text)
        return text.strip()

# ------------------- Content Extractor -------------------

class SmartContentExtractor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0'})
        self.processor = ContentProcessor()

    def extract_content(self, url):
        try:
            response = self.session.get(url, timeout=10)
            soup = BeautifulSoup(response.content, 'lxml')

            # удаляем ненужное
            for el in soup.find_all(['script', 'style', 'nav', 'footer', 'aside', 'form']):
                el.decompose()

            article = self.find_article(soup)
            if not article:
                return None, []

            text = self.processor.clean_text(article.get_text())
            images = self.extract_images(soup, url)
            return text, images
        except Exception as e:
            logger.error(f"Error extracting content from {url}: {e}")
            return None, []

    def find_article(self, soup):
        selectors = [
            'article .post-content', 'article .entry-content', 'article .article-content',
            'article .content', '.post-content', '.entry-content', '.article-content', '.content', 'article'
        ]
        for sel in selectors:
            element = soup.select_one(sel)
            if element and len(element.get_text(strip=True)) > 200:
                return element
        return soup.find('body')

    def extract_images(self, soup, base_url):
        images = []
        selectors = [
            '.wp-post-image', '.article-image img', '.post-image img',
            '.featured-image img', '.hero-image img', 'figure img',
            '.entry-content img:first-of-type', '.content img:first-of-type'
        ]
        for sel in selectors:
            imgs = soup.select(sel)
            for img in imgs[:2]:
                src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                if src:
                    full = urljoin(base_url, src)
                    images.append(full)
        if not images:
            all_imgs = soup.find_all('img')
            for img in all_imgs[:3]:
                src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                if src:
                    images.append(urljoin(base_url, src))
        return list(dict.fromkeys(images))[:MAX_IMAGES]

# ------------------- Telegram Publisher -------------------

class TelegramPublisher:
    def __init__(self, token, channel):
        self.token = token
        self.channel = channel
        self.session = requests.Session()

    def send_photo_group(self, caption, photo_urls):
        if not photo_urls:
            return self.send_message(caption)

        media = []
        for i, url in enumerate(photo_urls[:MAX_IMAGES]):
            media.append({
                "type": "photo",
                "media": url,
                "caption": caption if i == 0 else "",
                "parse_mode": "HTML"
            })

        url_api = f"https://api.telegram.org/bot{self.token}/sendMediaGroup"
        try:
            response = self.session.post(url_api, json={"chat_id": self.channel, "media": media}, timeout=30)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Error sending media group: {e}")
            return False

    def send_message(self, text):
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        data = {'chat_id': self.channel, 'text': text, 'parse_mode': 'HTML'}
        try:
            response = self.session.post(url, json=data, timeout=30)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False

# ------------------- Post Creator -------------------

class PostCreator:
    def create_post(self, title, content, images_count):
        post = f"<b>{title}</b>\n\n"
        post += f"{content}\n\n"
        if images_count > 0:
            post += f"🖼️ В материале: {images_count} фото"
        return post

# ------------------- Main Bot -------------------

class FashionNewsBot:
    def __init__(self):
        self.db = DatabaseManager()
        self.extractor = SmartContentExtractor()
        self.publisher = TelegramPublisher(BOT_TOKEN, CHANNEL)
        self.processor = ContentProcessor()
        self.post_creator = PostCreator()

    def check_sources(self):
        all_news = []
        for source in SOURCES:
            try:
                feed = feedparser.parse(source['url'])
                for entry in feed.entries[:15]:
                    if self.is_recent(entry) and self.is_fashion(entry):
                        all_news.append({
                            'title': entry.title,
                            'url': entry.link,
                            'summary': getattr(entry, 'summary', '')[:300]
                        })
            except Exception as e:
                logger.error(f"Error parsing {source['name']}: {e}")
        # сортируем по ключевым словам (важность)
        all_news.sort(key=lambda x: self.news_score(x['title']), reverse=True)
        # уникальные по URL
        unique_news = []
        seen = set()
        for n in all_news:
            if n['url'] not in seen:
                unique_news.append(n)
                seen.add(n['url'])
        return unique_news[:MAX_NEWS]

    def is_recent(self, entry, max_hours=24):
        try:
            date_str = getattr(entry, 'published', '')
            if not date_str:
                return True
            formats = ['%a, %d %b %Y %H:%M:%S %Z', '%a, %d %b %Y %H:%M:%S %z', '%Y-%m-%dT%H:%M:%SZ']
            for fmt in formats:
                try:
                    news_date = datetime.strptime(date_str, fmt)
                    return (datetime.now() - news_date).total_seconds()/3600 <= max_hours
                except:
                    continue
            return True
        except:
            return True

    def is_fashion(self, entry):
        content = f"{entry.title} {getattr(entry, 'summary', '')}".lower()
        keywords = ['sneaker','collection','collaboration','release','drop','fashion','streetwear','luxury','designer']
        return any(k in content for k in keywords)

    def news_score(self, title):
        score = 0
        keywords = ['collaboration','release','limited','exclusive','new','collection','drop','launch','announce']
        for k in keywords:
            if k in title.lower():
                score += 2
        return score

    def run(self):
        logger.info("🚀 Bot started")
        news_list = self.check_sources()
        logger.info(f"📰 {len(news_list)} news items to process")
        count = 0
        for news in news_list:
            if self.db.is_news_sent(news['url']):
                continue
            text, images = self.extractor.extract_content(news['url'])
            if not text:
                text = news['summary']
            title_ru = self.processor.translate_text(news['title'])
            text_ru = self.processor.translate_text(text)
            post = self.post_creator.create_post(title_ru, text_ru, len(images))
            success = self.publisher.send_photo_group(post, images)
            if success:
                self.db.mark_news_sent(news['url'], news['title'])
                count += 1
            time.sleep(5)
        logger.info(f"🎉 Published {count} news items")

if __name__ == "__main__":
    bot = FashionNewsBot()
    bot.run()
