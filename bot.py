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
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import sent_tokenize, word_tokenize
import string

# Скачиваем необходимые данные для nltk
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords')

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

class ContentProcessor:
    def __init__(self):
        self.translator = Translator()
        self.stop_words = set(stopwords.words('english'))
        
    def extract_key_points(self, text, max_sentences=3):
        """Извлекает ключевые моменты из текста"""
        # Разбиваем на предложения
        sentences = sent_tokenize(text)
        
        # Оцениваем важность каждого предложения
        scored_sentences = []
        for i, sentence in enumerate(sentences):
            score = self.score_sentence(sentence, i, len(sentences))
            scored_sentences.append((sentence, score))
        
        # Сортируем по важности
        scored_sentences.sort(key=lambda x: x[1], reverse=True)
        
        # Берем топ предложения
        top_sentences = [s[0] for s in scored_sentences[:max_sentences]]
        
        # Сортируем по порядку в тексте
        final_sentences = []
        for original_sentence in sentences:
            if original_sentence in top_sentences:
                final_sentences.append(original_sentence)
        
        return ' '.join(final_sentences)
    
    def score_sentence(self, sentence, position, total_sentences):
        """Оценивает важность предложения"""
        score = 0
        
        # Предложения в начале обычно важнее
        score += (1 - position / total_sentences) * 2
        
        # Длина предложения (средняя длина лучше)
        words = word_tokenize(sentence)
        if 8 <= len(words) <= 25:
            score += 2
        
        # Ключевые слова
        important_keywords = [
            'collaboration', 'release', 'limited', 'exclusive', 'new',
            'collection', 'drop', 'launch', 'announce', 'available',
            'first', 'special', 'edition', 'capsule', 'sneaker'
        ]
        
        for keyword in important_keywords:
            if keyword in sentence.lower():
                score += 3
        
        # Бренды в предложении
        brands_in_sentence = any(brand.lower() in sentence.lower() for brand in [
            'Nike', 'Jordan', 'Adidas', 'Supreme', 'Bape', 'Gucci'
        ])
        if brands_in_sentence:
            score += 2
        
        return score
    
    def clean_and_improve_text(self, text):
        """Очищает и улучшает текст"""
        # Удаляем лишние пробелы и переносы
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\n+', ' ', text)
        
        # Удаляем технические фразы
        technical_phrases = [
            'read more', 'read full article', 'click here', 'continue reading',
            'source:', 'image credit:', 'photo via', 'courtesy of'
        ]
        
        for phrase in technical_phrases:
            text = re.sub(phrase, '', text, flags=re.IGNORECASE)
        
        # Удаляем ссылки
        text = re.sub(r'http\S+', '', text)
        
        # Улучшаем начало предложений
        text = self.improve_sentence_structure(text)
        
        return text.strip()
    
    def improve_sentence_structure(self, text):
        """Улучшает структуру предложений"""
        # Делаем первое предложение более impactful
        sentences = sent_tokenize(text)
        if sentences:
            first_sentence = sentences[0]
            # Убираем вводные конструкции
            first_sentence = re.sub(r'^(according to|reports indicate that|it has been announced that)\s+', '', first_sentence, flags=re.IGNORECASE)
            sentences[0] = first_sentence.capitalize()
        
        return ' '.join(sentences)
    
    def smart_translate(self, text):
        """Умный перевод с улучшением качества"""
        try:
            if len(text) > 4000:
                text = text[:4000]
            
            translated = self.translator.translate(text, dest='ru')
            
            # Улучшаем русский текст
            improved_russian = self.improve_russian_text(translated.text)
            return improved_russian
            
        except Exception as e:
            logger.warning(f"Translation failed: {e}")
            return text
    
    def improve_russian_text(self, text):
        """Улучшает качество русского текста"""
        # Исправляем частые ошибки перевода
        improvements = {
            'релиз': 'релиз',
            'коллаборация': 'коллаборация',
            'коллекция': 'коллекция',
            'кроссовки': 'кроссовки',
            'лимитированный': 'лимитированный',
            'эксклюзивный': 'эксклюзивный',
            'доступен': 'доступен',
            'анонсировал': 'анонсировал',
            'запустил': 'запустил'
        }
        
        for eng, ru in improvements.items():
            text = text.replace(eng, ru)
        
        # Делаем текст более естественным
        text = text.replace(' ,', ',')
        text = text.replace(' .', '.')
        text = re.sub(r'\s+', ' ', text)
        
        return text

class SmartContentExtractor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.processor = ContentProcessor()
    
    def extract_quality_content(self, url):
        """Извлекает качественный контент и изображения"""
        try:
            response = self.session.get(url, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Удаляем ненужные элементы
            for element in soup.find_all(['script', 'style', 'nav', 'footer', 'aside', 'form']):
                element.decompose()
            
            # Ищем основной контент статьи
            article_content = self.find_article_content(soup)
            
            if not article_content:
                return None, []
            
            # Извлекаем чистый текст
            raw_text = article_content.get_text()
            clean_text = self.processor.clean_and_improve_text(raw_text)
            
            # Извлекаем ключевые моменты
            key_points = self.processor.extract_key_points(clean_text)
            
            # Извлекаем качественные изображения
            images = self.extract_quality_images(soup, url)
            
            return key_points, images
            
        except Exception as e:
            logger.error(f"Error extracting content from {url}: {e}")
            return None, []
    
    def find_article_content(self, soup):
        """Находит основной контент статьи"""
        content_selectors = [
            'article .post-content',
            'article .entry-content',
            'article .article-content',
            'article .content',
            '.post-content',
            '.entry-content',
            '.article-content',
            '.content',
            'article'
        ]
        
        for selector in content_selectors:
            element = soup.select_one(selector)
            if element and len(element.get_text(strip=True)) > 200:
                return element
        
        return soup.find('body')
    
    def extract_quality_images(self, soup, base_url):
        """Извлекает только качественные изображения"""
        images = []
        
        # Приоритетные селекторы для главных изображений
        priority_selectors = [
            '.wp-post-image',
            '.article-image img',
            '.post-image img',
            '.featured-image img',
            '.hero-image img',
            'figure img',
            '.entry-content img:first-of-type',
            '.content img:first-of-type'
        ]
        
        # Сначала ищем приоритетные изображения
        for selector in priority_selectors:
            imgs = soup.select(selector)
            for img in imgs[:2]:  # Берем только первые 2
                src = self.get_image_src(img)
                if src and self.is_quality_image(src):
                    full_url = self.make_absolute_url(src, base_url)
                    if full_url:
                        images.append(full_url)
        
        # Если нет приоритетных, ищем любые качественные
        if not images:
            all_imgs = soup.find_all('img')
            for img in all_imgs[:3]:  # Ограничиваем количество
                src = self.get_image_src(img)
                if src and self.is_quality_image(src):
                    full_url = self.make_absolute_url(src, base_url)
                    if full_url:
                        images.append(full_url)
        
        # Убираем дубликаты и ограничиваем количество
        return list(dict.fromkeys(images))[:3]  # Максимум 3 изображения
    
    def get_image_src(self, img_element):
        """Получает URL изображения из элемента"""
        return (img_element.get('src') or 
                img_element.get('data-src') or 
                img_element.get('data-lazy-src'))
    
    def make_absolute_url(self, url, base_url):
        """Преобразует относительный URL в абсолютный"""
        if url.startswith('//'):
            return 'https:' + url
        elif url.startswith('/'):
            return urljoin(base_url, url)
        elif url.startswith(('http://', 'https://')):
            return url
        return None
    
    def is_quality_image(self, url):
        """Проверяет, является ли изображение качественным"""
        excluded_terms = [
            'logo', 'icon', 'avatar', 'thumbnail', 'pixel', 'spinner',
            'advertisement', 'banner', 'widget', 'placeholder'
        ]
        
        if any(term in url.lower() for term in excluded_terms):
            return False
        
        valid_extensions = ['.jpg', '.jpeg', '.png', '.webp']
        if not any(ext in url.lower() for ext in valid_extensions):
            return False
        
        # Проверяем размер в URL (признак качественного изображения)
        size_indicators = ['large', 'xlarge', 'xxlarge', 'original', 'full', 'main']
        if any(indicator in url.lower() for indicator in size_indicators):
            return True
        
        return True

class PostCreator:
    def __init__(self):
        self.processor = ContentProcessor()
    
    def create_clean_post(self, title, content, source, images_count=0):
        """Создает чистый и привлекательный пост"""
        # Улучшаем заголовок
        improved_title = self.improve_title(title)
        
        # Улучшаем контент
        improved_content = self.improve_content(content)
        
        # Создаем пост
        post = f"<b>{improved_title}</b>\n\n"
        post += f"{improved_content}\n\n"
        
        # Добавляем информацию об изображениях
        if images_count > 0:
            post += f"🖼️ В материале: {images_count} фото\n\n"
        
        post += f"📰 {source}"
        
        return post
    
    def improve_title(self, title):
        """Улучшает заголовок"""
        # Убираем технические элементы
        title = re.sub(r'\s*-\s*[^-]*$', '', title)  # Убираем "- Source Name"
        title = re.sub(r'\s*\|.*$', '', title)  # Убираем "| Section"
        
        # Делаем первую букву заглавной
        if title:
            title = title[0].upper() + title[1:]
        
        return title.strip()
    
    def improve_content(self, content):
        """Улучшает содержание"""
        # Разбиваем на предложения
        sentences = sent_tokenize(content)
        
        if not sentences:
            return content
        
        # Выделяем ключевые моменты жирным
        improved_sentences = []
        for sentence in sentences:
            improved_sentence = self.highlight_key_points(sentence)
            improved_sentences.append(improved_sentence)
        
        return ' '.join(improved_sentences)
    
    def highlight_key_points(self, sentence):
        """Выделяет ключевые моменты жирным"""
        # Ключевые фразы для выделения
        key_phrases = [
            r'коллаборация\w*',
            r'лимитированн\w*',
            r'эксклюзивн\w*',
            r'релиз\w*',
            r'новый модель',
            r'впервые',
            r'ограниченный тираж',
            r'специальный выпуск',
            r'капсульная коллекция'
        ]
        
        result = sentence
        for phrase in key_phrases:
            matches = re.finditer(phrase, result, re.IGNORECASE)
            for match in matches:
                original = match.group()
                highlighted = f"<b>{original}</b>"
                result = result.replace(original, highlighted)
        
        return result

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
            
            if response.status_code == 200 and len(photo_urls) > 1:
                # Отправляем остальные фото
                for photo_url in photo_urls[1:3]:  # Максимум 3 фото
                    try:
                        photo_response = self.session.get(photo_url, timeout=10)
                        if photo_response.status_code == 200:
                            files = {'photo': ('image.jpg', photo_response.content, 'image/jpeg')}
                            data = {'chat_id': self.channel}
                            self.session.post(url, files=files, data=data, timeout=30)
                            time.sleep(1)
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
        self.extractor = SmartContentExtractor()
        self.publisher = TelegramPublisher(BOT_TOKEN, CHANNEL)
        self.post_creator = PostCreator()
        self.translator = ContentProcessor()
    
    def check_sources(self):
        """Проверяет все источники на новые новости"""
        all_news = []
        
        for source in SOURCES:
            try:
                logger.info(f"🔍 Checking {source['name']}...")
                news_items = self.parse_feed(source)
                all_news.extend(news_items)
                time.sleep(2)
            except Exception as e:
                logger.error(f"Error parsing {source['name']}: {e}")
                continue
        
        return all_news
    
    def parse_feed(self, source):
        """Парсит RSS фид источника"""
        news_items = []
        
        try:
            feed = feedparser.parse(source['url'])
            
            for entry in feed.entries[:15]:  # Берем 15 последних записей
                if self.is_recent(entry) and self.is_fashion_related(entry):
                    news_item = {
                        'title': entry.title,
                        'url': entry.link,
                        'source': source['name'],
                        'published': getattr(entry, 'published', ''),
                        'summary': getattr(entry, 'summary', '')[:300]
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
        
        fashion_keywords = [
            'sneaker', 'collection', 'collaboration', 'release', 'drop',
            'fashion', 'streetwear', 'luxury', 'designer', 'boot',
            'jacket', 'hoodie', 'shoe', 'apparel', 'capsule'
        ]
        
        return any(keyword in content for keyword in fashion_keywords)
    
    def process_news(self, news_item):
        """Обрабатывает новость и создает пост"""
        if self.db.is_news_sent(news_item['url']):
            return None
        
        logger.info(f"📝 Processing: {news_item['title']}")
        
        # Извлекаем качественный контент
        content, images = self.extractor.extract_quality_content(news_item['url'])
        
        if not content:
            content = news_item['summary']
        
        # Переводим и улучшаем
        translated_title = self.translator.smart_translate(news_item['title'])
        translated_content = self.translator.smart_translate(content)
        
        # Создаем чистый пост
        post = self.post_creator.create_clean_post(
            translated_title, 
            translated_content, 
            news_item['source'],
            len(images)
        )
        
        # Помечаем как отправленную
        self.db.mark_news_sent(news_item['url'], news_item['source'], news_item['title'])
        
        return post, images
    
    def run(self):
        """Запускает бота"""
        logger.info("🚀 Starting Smart Fashion News Bot")
        
        # Проверяем источники
        all_news = self.check_sources()
        logger.info(f"📰 Found {len(all_news)} new news items")
        
        # Обрабатываем и публикуем каждую новость
        success_count = 0
        for news_item in all_news:
            try:
                result = self.process_news(news_item)
                if result:
                    post, images = result
                    
                    # Публикуем пост
                    success = self.publisher.send_photo_group(post, images)
                    
                    if success:
                        success_count += 1
                        logger.info(f"✅ Published: {news_item['title'][:50]}...")
                    else:
                        logger.error(f"❌ Failed to publish: {news_item['title'][:50]}...")
                    
                    # Задержка между постами
                    if success_count < 3:  # Максимум 3 поста за раз
                        time.sleep(10)
                    else:
                        break
                    
            except Exception as e:
                logger.error(f"❌ Error processing news: {e}")
                continue
        
        logger.info(f"🎉 Published {success_count} news items")

if __name__ == "__main__":
    bot = FashionNewsBot()
    bot.run()
    logger.info("✅ Bot finished!")
