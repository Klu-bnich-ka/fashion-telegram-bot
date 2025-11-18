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
from googlesearch import search as google_search
import urllib.parse

# Отключаем предупреждения SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Настройки
BOT_TOKEN = os.environ['BOT_TOKEN']
CHANNEL = os.environ['CHANNEL']

# Только 3 самых популярных источника
SOURCES = [
    {
        'name': 'Hypebeast', 
        'url': 'https://hypebeast.com/fashion/feed',
        'lang': 'en',
        'weight': 10  # Приоритет в поиске
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

# Расширенный список брендов для лучшего покрытия
BRANDS = [
    'Nike', 'Jordan', 'Adidas', 'New Balance', 'Supreme', 'Palace', 
    'Bape', 'Stussy', 'Off-White', 'Balenciaga', 'Gucci', 'Dior',
    'Louis Vuitton', 'Prada', 'Chanel', 'Versace', 'Yeezy', 'Fear of God',
    'Essentials', 'Rhude', 'Amiri', 'A-Cold-Wall', 'Kith', 'Noah',
    'Aime Leon Dore', 'Brain Dead', 'Awake NY', 'Carhartt WIP', 'Stone Island',
    'Moncler', 'Bottega Veneta', 'Loewe', 'Givenchy', 'Burberry', 'Tom Ford',
    'Alexander McQueen', 'Saint Laurent', 'Celine', 'Vetements', 'Comme des Garçons',
    'Maison Margiela', 'Acne Studios', 'Rick Owens', 'Raf Simons', 'JW Anderson',
    'Palm Angels', 'Heron Preston', 'Martine Rose', 'CP Company', 'Arc\'teryx',
    'Salomon', 'Asics', 'Converse', 'Vans', 'Puma', 'Reebok', 'Dr. Martens',
    'Birkenstock', 'Crocs', 'Champion', 'Fila', 'Ellesse', 'Kappa', 'Lacoste',
    'Fred Perry', 'Ben Sherman', 'Baracuta', 'Timberland', 'Wolverine', 'Red Wing'
]

# Эмодзи для брендов в стиле Топора
BRAND_EMOJIS = {
    'Nike': '👟', 'Jordan': '🅰️', 'Adidas': '❌', 'Supreme': '🔴', 
    'Palace': '🔷', 'Bape': '🐒', 'Stussy': '🏄', 'Off-White': '🟨',
    'Balenciaga': '👟', 'Gucci': '🐍', 'Dior': '🌹', 'Louis Vuitton': '🧳',
    'Prada': '🔺', 'Chanel': '👑', 'Yeezy': '🌊', 'Fear of God': '☁️',
    'Essentials': '⚫', 'Rhude': '🌵', 'Amiri': '⭐', 'A-Cold-Wall': '🧱',
    'Kith': '🍦', 'Stone Island': '🧭', 'Moncler': '🦢', 'default': '👕'
}

class ToporStyleFormatter:
    """Форматирование в стиле Топора"""
    
    @staticmethod
    def create_news_post(brand, title, content, engagement_data, image_url=None):
        """Создает пост в стиле Топора"""
        
        emoji = BRAND_EMOJIS.get(brand, BRAND_EMOJIS['default'])
        
        # Основной заголовок (как в Топоре)
        main_title = f"{emoji} {title}"
        
        # Основной контент (2-3 предложения)
        content_paragraphs = content.split('. ')
        short_content = '. '.join(content_paragraphs[:2]) + '.'
        
        # Статистика (подписчики, комментарии - генерируем реалистичные числа)
        subscribers = f"{random.randint(800, 1500)}K" 
        comments = random.randint(200, 3000)
        views = f"{random.randint(1, 3)}.{random.randint(1, 9)}M"
        
        # Время публикации (рандомное в пределах 2 часов)
        time_posted = f"{random.randint(12, 23)}:{random.randint(10, 59)}"
        
        # Форматируем пост
        post = f"""{main_title}

{short_content}

Топор +18. Подписаться
{subscribers} {time_posted}

{comments} комментариев

Топор+
"""
        return post

    @staticmethod
    def create_viral_post(brand, title, content, engagement_data):
        """Создает виральный пост с высокой вовлеченностью"""
        
        emoji = BRAND_EMOJIS.get(brand, BRAND_EMOJIS['default'])
        
        subscribers = f"{random.randint(500, 1200)}K"
        comments = random.randint(500, 5000)
        time_posted = f"{random.randint(10, 22)}:{random.randint(10, 59)}"
        
        post = f"""{emoji} {title}

{content}

Топор +18. Подписаться  
{subscribers} {time_posted}  

{comments} комментариев  

Топор+
"""
        return post

class AdvancedNewsAggregator:
    """Продвинутый агрегатор новостей"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        })
        
    def get_trending_keywords(self):
        """Получает трендовые ключевые слова в моде"""
        trending_keywords = [
            "new collection", "collaboration", "limited edition", "sneaker release",
            "fashion week", "designer collection", "streetwear", "luxury fashion",
            "capsule collection", "resell market", "drop", "exclusive"
        ]
        return random.sample(trending_keywords, 3)
    
    def calculate_engagement_score(self, title, content, brand):
        """Рассчитывает оценку вовлеченности контента"""
        score = 0
        
        # Бонусы за популярные бренды
        popular_brands = ['Nike', 'Jordan', 'Supreme', 'Adidas', 'Balenciaga', 'Gucci']
        if brand in popular_brands:
            score += 30
            
        # Бонус за ключевые слова
        viral_keywords = ['collaboration', 'limited', 'exclusive', 'release', 'new', 'first']
        for keyword in viral_keywords:
            if keyword.lower() in title.lower():
                score += 10
                
        # Бонус за длину контента (оптимальная 100-300 символов)
        content_length = len(content)
        if 100 <= content_length <= 300:
            score += 20
        elif content_length > 300:
            score += 10
            
        return min(score, 100)
    
    def find_most_viral_content(self):
        """Ищет самый виральный контент из всех источников"""
        all_news = []
        
        for source in SOURCES:
            try:
                logger.info(f"🔍 Checking {source['name']}...")
                news_items = self.parse_source(source)
                all_news.extend(news_items)
                time.sleep(2)  # Задержка между запросами
            except Exception as e:
                logger.error(f"❌ Error parsing {source['name']}: {e}")
                continue
                
        if not all_news:
            return None
            
        # Сортируем по оценке вовлеченности
        all_news.sort(key=lambda x: x['engagement_score'], reverse=True)
        
        # Возвращаем топ-3 самых виральных новости
        return all_news[:3]
    
    def parse_source(self, source):
        """Парсит конкретный источник"""
        news_items = []
        
        try:
            feed = feedparser.parse(source['url'])
            
            for entry in feed.entries[:10]:  # Берем только 10 последних
                if self.is_recent_news(entry):
                    news_item = self.process_news_entry(entry, source)
                    if news_item:
                        news_items.append(news_item)
                        
        except Exception as e:
            logger.error(f"❌ Error parsing feed {source['name']}: {e}")
            
        return news_items
    
    def is_recent_news(self, entry, max_hours=6):
        """Проверяет, является ли новость свежей (до 6 часов)"""
        date_fields = ['published', 'updated', 'pubDate']
        
        for field in date_fields:
            date_str = getattr(entry, field, None)
            if date_str:
                try:
                    news_date = self.parse_date(date_str)
                    if news_date:
                        time_diff = datetime.now() - news_date
                        return time_diff.total_seconds() / 3600 <= max_hours
                except:
                    continue
        return False
    
    def parse_date(self, date_string):
        """Парсит дату из различных форматов"""
        formats = [
            '%a, %d %b %Y %H:%M:%S %Z',
            '%a, %d %b %Y %H:%M:%S %z',
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%d %H:%M:%S',
            '%d %b %Y %H:%M:%S'
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_string, fmt)
            except:
                continue
        return None
    
    def process_news_entry(self, entry, source):
        """Обрабатывает запись новости"""
        title = getattr(entry, 'title', '')
        description = getattr(entry, 'description', '')
        link = getattr(entry, 'link', '')
        
        if not title:
            return None
            
        # Ищем бренды в контенте
        brand = self.extract_brand(title + " " + description)
        if not brand:
            return None
            
        # Извлекаем контент
        content = self.clean_content(description or title)
        
        # Извлекаем изображение
        image_url = self.extract_image(entry, link)
        
        # Рассчитываем оценку вовлеченности
        engagement_score = self.calculate_engagement_score(title, content, brand)
        
        return {
            'title': title,
            'content': content,
            'brand': brand,
            'source': source['name'],
            'engagement_score': engagement_score,
            'image_url': image_url,
            'link': link,
            'original_title': title
        }
    
    def extract_brand(self, text):
        """Извлекает бренд из текста"""
        text_lower = text.lower()
        
        for brand in BRANDS:
            if brand.lower() in text_lower:
                return brand
                
        return None
    
    def clean_content(self, content):
        """Очищает и форматирует контент"""
        # Удаляем HTML теги
        clean = re.sub('<[^<]+?>', '', content)
        
        # Удаляем лишние пробелы
        clean = re.sub('\s+', ' ', clean).strip()
        
        # Обрезаем до разумной длины
        if len(clean) > 300:
            sentences = clean.split('. ')
            clean = '. '.join(sentences[:2]) + '.'
            
        return clean
    
    def extract_image(self, entry, link):
        """Извлекает изображение из записи"""
        # Сначала проверяем медиа-контент в RSS
        if hasattr(entry, 'media_content'):
            for media in entry.media_content:
                if media.get('type', '').startswith('image/'):
                    return media['url']
                    
        if hasattr(entry, 'links'):
            for link_obj in entry.links:
                if link_obj.get('type', '').startswith('image/'):
                    return link_obj['href']
        
        # Парсим страницу для поиска изображений
        return self.extract_image_from_page(link)
    
    def extract_image_from_page(self, url):
        """Извлекает изображение со страницы"""
        try:
            response = self.session.get(url, timeout=10, verify=False)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Приоритетные селекторы для изображений
            selectors = [
                'meta[property="og:image"]',
                'meta[name="twitter:image"]',
                'meta[property="twitter:image:src"]',
                '.article-image img',
                '.post-image img',
                '.wp-post-image',
                '.entry-content img',
                '.content img',
                'figure img',
                '.hero-image img',
                '.featured-image img',
                'img[src*="large"]',
                'img[src*="medium"]',
                'img'
            ]
            
            for selector in selectors:
                images = soup.select(selector)
                for img in images:
                    src = None
                    if selector.startswith('meta'):
                        src = img.get('content', '')
                    else:
                        src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                    
                    if src and self.is_quality_image(src):
                        if src.startswith('//'):
                            src = 'https:' + src
                        elif src.startswith('/'):
                            src = urljoin(url, src)
                            
                        # Проверяем, что изображение доступно
                        if self.verify_image(src):
                            return src
                            
        except Exception as e:
            logger.warning(f"⚠️ Image extraction failed: {e}")
            
        return None
    
    def is_quality_image(self, url):
        """Проверяет, является ли изображение качественным"""
        if not url.startswith(('http://', 'https://')):
            return False
            
        excluded = ['icon', 'logo', 'thumbnail', 'avatar', 'pixel', 'spinner']
        if any(term in url.lower() for term in excluded):
            return False
            
        valid_ext = ['.jpg', '.jpeg', '.png', '.webp']
        if not any(ext in url.lower() for ext in valid_ext):
            return False
            
        return True
    
    def verify_image(self, url):
        """Проверяет доступность изображения"""
        try:
            response = self.session.head(url, timeout=5, verify=False)
            return response.status_code == 200
        except:
            return False

class SmartContentEnhancer:
    """Умный усилитель контента"""
    
    def __init__(self):
        self.translation_cache = {}
        
    def enhance_content(self, original_content, brand):
        """Улучшает и адаптирует контент"""
        # Сначала переводим, если нужно
        content = self.smart_translate(original_content)
        
        # Улучшаем стиль
        content = self.improve_writing_style(content, brand)
        
        # Добавляем виральные элементы
        content = self.add_viral_elements(content, brand)
        
        return content
    
    def smart_translate(self, text):
        """Умный перевод контента"""
        if self.is_english(text):
            return self.translate_to_russian(text)
        return text
    
    def is_english(self, text):
        """Определяет, является ли текст английским"""
        try:
            blob = TextBlob(text)
            return blob.detect_language() == 'en'
        except:
            # Если TextBlob не работает, используем простую эвристику
            english_words = ['the', 'and', 'of', 'to', 'a', 'in', 'is', 'it', 'you', 'that']
            count = sum(1 for word in english_words if word in text.lower().split())
            return count > 2
    
    def translate_to_russian(self, text):
        """Переводит текст на русский (упрощенная версия)"""
        # Кэшируем переводы
        text_hash = hashlib.md5(text.encode()).hexdigest()
        if text_hash in self.translation_cache:
            return self.translation_cache[text_hash]
        
        # Простой переводчик на основе правил
        translation_rules = {
            'release': 'релиз',
            'collection': 'коллекция',
            'collaboration': 'коллаборация',
            'sneakers': 'кроссовки',
            'limited': 'лимитированный',
            'edition': 'издание',
            'exclusive': 'эксклюзивный',
            'new': 'новый',
            'designer': 'дизайнер',
            'fashion': 'мода',
            'streetwear': 'стритвир',
            'luxury': 'люкс',
            'brand': 'бренд',
            'drop': 'дроп',
            'capsule': 'капсула',
            'season': 'сезон',
            'available': 'доступен',
            'price': 'цена',
            'colorway': 'расцветка',
            'material': 'материал',
            'leather': 'кожа',
            'suede': 'замша',
            'mesh': 'сетка',
            'rubber': 'резина',
        }
        
        translated = text
        for eng, rus in translation_rules.items():
            translated = re.sub(rf'\b{eng}\b', rus, translated, flags=re.IGNORECASE)
            
        self.translation_cache[text_hash] = translated
        return translated
    
    def improve_writing_style(self, content, brand):
        """Улучшает стиль написания в стиле Топора"""
        # Делаем более разговорным
        content = content.replace('представляет', 'выкатывает')
        content = content.replace('анонсирует', 'рассказывает про')
        content = content.replace('коллекция', 'новая коллекция')
        
        # Добавляем эмоции
        emotional_words = ['🔥', '💥', '👀', '✨']
        if random.random() > 0.7:
            content = emotional_words[0] + ' ' + content
            
        return content
    
    def add_viral_elements(self, content, brand):
        """Добавляет виральные элементы"""
        viral_phrases = [
            "Это точно взорвет интернеты!",
            "Ждем, когда появится в продаже!",
            "Что думаете о новинке?",
            "Насколько это вообще круто?",
            "Будете брать?",
        ]
        
        if random.random() > 0.5:
            content += " " + random.choice(viral_phrases)
            
        return content

class DatabaseManager:
    """Менеджер базы данных"""
    
    def __init__(self):
        self.init_database()
    
    @contextmanager
    def get_db_connection(self):
        conn = sqlite3.connect('fashion_news.db')
        try:
            yield conn
        finally:
            conn.close()
    
    def init_database(self):
        """Инициализирует базу данных"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sent_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_hash TEXT UNIQUE,
                    brand TEXT,
                    title TEXT,
                    engagement_score INTEGER,
                    sent_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_post_hash ON sent_posts(post_hash)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sent_date ON sent_posts(sent_date)')
            conn.commit()
    
    def is_post_sent(self, post_hash):
        """Проверяет, был ли пост уже отправлен"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM sent_posts WHERE post_hash = ?', (post_hash,))
            return cursor.fetchone() is not None
    
    def mark_post_sent(self, post_hash, brand, title, engagement_score):
        """Помечает пост как отправленный"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    'INSERT INTO sent_posts (post_hash, brand, title, engagement_score) VALUES (?, ?, ?, ?)',
                    (post_hash, brand, title[:200], engagement_score)
                )
                conn.commit()
            except sqlite3.IntegrityError:
                pass
    
    def cleanup_old_posts(self, days=3):
        """Очищает старые посты"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM sent_posts WHERE sent_date < datetime("now", ?)', (f"-{days} days",))
            conn.commit()

class TelegramBot:
    """Telegram бот для отправки постов"""
    
    def __init__(self, token, channel):
        self.token = token
        self.channel = channel
        self.session = requests.Session()
    
    def send_post(self, content, image_url=None):
        """Отправляет пост в Telegram канал"""
        try:
            if image_url and self.is_valid_image(image_url):
                return self.send_photo(content, image_url)
            else:
                return self.send_text(content)
        except Exception as e:
            logger.error(f"❌ Telegram send error: {e}")
            return False
    
    def is_valid_image(self, image_url):
        """Проверяет валидность изображения"""
        try:
            response = self.session.head(image_url, timeout=5, verify=False)
            content_type = response.headers.get('content-type', '')
            return response.status_code == 200 and content_type.startswith('image/')
        except:
            return False
    
    def send_photo(self, caption, photo_url):
        """Отправляет фото с подписью"""
        url = f'https://api.telegram.org/bot{self.token}/sendPhoto'
        
        # Скачиваем изображение
        try:
            response = self.session.get(photo_url, timeout=10, verify=False)
            if response.status_code != 200:
                return self.send_text(caption)
                
            files = {'photo': ('image.jpg', response.content, 'image/jpeg')}
            data = {
                'chat_id': self.channel,
                'caption': caption,
                'parse_mode': 'HTML'
            }
            
            response = self.session.post(url, files=files, data=data, timeout=30)
            return response.status_code == 200
            
        except Exception as e:
            logger.warning(f"⚠️ Photo send failed, falling back to text: {e}")
            return self.send_text(caption)
    
    def send_text(self, text):
        """Отправляет текстовый пост"""
        url = f'https://api.telegram.org/bot{self.token}/sendMessage'
        data = {
            'chat_id': self.channel,
            'text': text,
            'parse_mode': 'HTML',
            'disable_web_page_preview': False
        }
        
        response = self.session.post(url, json=data, timeout=30)
        return response.status_code == 200

class FashionNewsBot:
    """Главный класс бота модных новостей"""
    
    def __init__(self):
        self.db = DatabaseManager()
        self.aggregator = AdvancedNewsAggregator()
        self.enhancer = SmartContentEnhancer()
        self.bot = TelegramBot(BOT_TOKEN, CHANNEL)
        self.formatter = ToporStyleFormatter()
        
    def generate_post_hash(self, content, brand):
        """Генерирует хэш поста"""
        return hashlib.md5(f"{content}_{brand}".encode()).hexdigest()
    
    def find_best_news(self):
        """Ищет лучшую новость для публикации"""
        logger.info("🎯 Searching for the most viral content...")
        
        viral_news = self.aggregator.find_most_viral_content()
        if not viral_news:
            logger.warning("⚠️ No viral news found, generating curated content...")
            return self.generate_curated_content()
        
        # Выбираем лучшую новость
        best_news = viral_news[0]
        
        # Проверяем, не публиковали ли уже
        post_hash = self.generate_post_hash(best_news['content'], best_news['brand'])
        if self.db.is_post_sent(post_hash):
            logger.info("⏭️ This news was already posted, trying next...")
            if len(viral_news) > 1:
                best_news = viral_news[1]
                post_hash = self.generate_post_hash(best_news['content'], best_news['brand'])
                if self.db.is_post_sent(post_hash) and len(viral_news) > 2:
                    best_news = viral_news[2]
                    post_hash = self.generate_post_hash(best_news['content'], best_news['brand'])
        
        if self.db.is_post_sent(post_hash):
            logger.warning("⚠️ All recent news already posted, generating curated content...")
            return self.generate_curated_content()
            
        return best_news, post_hash
    
    def generate_curated_content(self):
        """Генерирует курируемый контент когда нет новостей"""
        brands = ['Nike', 'Adidas', 'Supreme', 'Balenciaga', 'Gucci']
        brand = random.choice(brands)
        
        curated_templates = [
            f"{brand} готовит сюрприз на следующий сезон. Инсайдеры говорят о коллаборации с известным брендом.",
            f"Слухи: {brand} работает над новой капсульной коллекцией. Ожидается ограниченный тираж.",
            f"{brand} может представить обновление культовой модели. Фанаты ждут с нетерпением.",
            f"В сети появились первые тизеры новой коллекции {brand}. Выглядит многообещающе!",
        ]
        
        content = random.choice(curated_templates)
        engagement_score = random.randint(60, 85)
        
        curated_news = {
            'title': f"{brand} | Свежие слухи",
            'content': content,
            'brand': brand,
            'engagement_score': engagement_score,
            'image_url': None,
            'source': 'Curated'
        }
        
        post_hash = self.generate_post_hash(content, brand)
        return curated_news, post_hash
    
    def create_final_post(self, news_item):
        """Создает финальный пост для публикации"""
        brand = news_item['brand']
        original_title = news_item['original_title']
        content = news_item['content']
        
        # Улучшаем контент
        enhanced_content = self.enhancer.enhance_content(content, brand)
        
        # Создаем привлекательный заголовок
        title = self.create_catchy_title(original_title, brand)
        
        # Выбираем стиль поста на основе engagement score
        engagement_score = news_item['engagement_score']
        
        if engagement_score >= 80:
            post_content = self.formatter.create_viral_post(brand, title, enhanced_content, engagement_score)
        else:
            post_content = self.formatter.create_news_post(brand, title, enhanced_content, engagement_score)
            
        return post_content
    
    def create_catchy_title(self, original_title, brand):
        """Создает цепляющий заголовок"""
        # Упрощаем и делаем более виральным
        title_variations = [
            f"{brand} запускает новый дроп",
            f"Новинка от {brand} уже здесь",
            f"{brand} представляет: смотрите первыми",
            f"Хит сезона от {brand}",
            f"{brand} удивляет новым релизом",
            f"Не пропустите: новый релиз {brand}",
            f"{brand} анонсирует коллаборацию",
        ]
        
        return random.choice(title_variations)
    
    def run(self):
        """Запускает бота"""
        logger.info("🚀 Starting Fashion News Bot (Topor Style)")
        
        # Очищаем старые посты
        self.db.cleanup_old_posts(days=3)
        
        # Ищем лучшую новость
        news_item, post_hash = self.find_best_news()
        
        if not news_item:
            logger.error("❌ No content found for posting")
            return False
        
        # Создаем пост
        post_content = self.create_final_post(news_item)
        
        # Отправляем пост
        logger.info(f"📤 Posting about {news_item['brand']} (engagement: {news_item['engagement_score']})")
        
        success = self.bot.send_post(post_content, news_item.get('image_url'))
        
        if success:
            # Сохраняем в базу
            self.db.mark_post_sent(
                post_hash, 
                news_item['brand'], 
                news_item['title'], 
                news_item['engagement_score']
            )
            logger.info("✅ Post sent successfully!")
            return True
        else:
            logger.error("❌ Failed to send post")
            return False

if __name__ == "__main__":
    try:
        bot = FashionNewsBot()
        success = bot.run()
        
        if success:
            logger.info("🎉 Bot finished successfully!")
        else:
            logger.error("💥 Bot finished with errors")
            
    except Exception as e:
        logger.error(f"💥 Critical error: {e}")
