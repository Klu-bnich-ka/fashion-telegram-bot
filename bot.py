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
from urllib.parse import urljoin
import sqlite3
from contextlib import contextmanager

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Настройки
BOT_TOKEN = os.environ['BOT_TOKEN']
CHANNEL = os.environ['CHANNEL']

# Инициализация базы данных для хранения отправленных новостей
def init_database():
    conn = sqlite3.connect('news_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sent_news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            news_hash TEXT UNIQUE,
            brand TEXT,
            title TEXT,
            sent_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hash ON sent_news(news_hash)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_date ON sent_news(sent_date)')
    conn.commit()
    conn.close()

@contextmanager
def get_db_connection():
    conn = sqlite3.connect('news_bot.db')
    try:
        yield conn
    finally:
        conn.close()

def is_news_sent(news_hash):
    """Проверяет, была ли новость уже отправлена"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM sent_news WHERE news_hash = ?', (news_hash,))
        return cursor.fetchone() is not None

def mark_news_sent(news_hash, brand, title):
    """Помечает новость как отправленную"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                'INSERT INTO sent_news (news_hash, brand, title) VALUES (?, ?, ?)',
                (news_hash, brand, title[:200])  # Ограничиваем длину title
            )
            conn.commit()
        except sqlite3.IntegrityError:
            pass  # Уже существует

def cleanup_old_news(days=7):
    """Очищает старые записи из базы"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM sent_news WHERE sent_date < datetime("now", ?)', (f"-{days} days",))
        conn.commit()

# Стили форматирования для Telegram
class TextStyler:
    @staticmethod
    def bold(text):
        return f"<b>{text}</b>"

    @staticmethod
    def italic(text):
        return f"<i>{text}</i>"

    @staticmethod
    def underline(text):
        return f"<u>{text}</u>"

    @staticmethod
    def create_header(text, emoji="✨"):
        return f"{emoji} {TextStyler.bold(text.upper())}"

    @staticmethod
    def create_quote(text):
        return f"❝{text}❞"

# Инициализация стилера
styler = TextStyler()

# БАЗА ИСТОЧНИКОВ
SOURCES = [
    {'name': 'Vogue', 'url': 'https://www.vogue.com/rss', 'lang': 'en'},
    {'name': 'Business of Fashion', 'url': 'https://www.businessoffashion.com/feed', 'lang': 'en'},
    {'name': 'Hypebeast', 'url': 'https://hypebeast.com/fashion/feed', 'lang': 'en'},
    {'name': 'Highsnobiety', 'url': 'https://www.highsnobiety.com/feed/', 'lang': 'en'},
    {'name': 'Fashionista', 'url': 'https://fashionista.com/.rss', 'lang': 'en'},
    {'name': 'WWD', 'url': 'https://wwd.com/feed/', 'lang': 'en'},
    {'name': 'The Cut', 'url': 'https://www.thecut.com/rss/index.xml', 'lang': 'en'},
    {'name': 'Complex', 'url': 'https://www.complex.com/feeds/style', 'lang': 'en'},
    {'name': 'Sneaker News', 'url': 'https://sneakernews.com/feed/', 'lang': 'en'},
    {'name': 'Nice Kicks', 'url': 'https://www.nicekicks.com/feed/', 'lang': 'en'},
    {'name': 'Kicks On Fire', 'url': 'https://www.kicksonfire.com/feed/', 'lang': 'en'},
    {'name': 'Robb Report', 'url': 'https://robbreport.com/feed/', 'lang': 'en'},
    {'name': "Harper's Bazaar", 'url': 'https://www.harpersbazaar.com/feed/rss/', 'lang': 'en'},
    {'name': 'Elle Global', 'url': 'https://www.elle.com/rss/all.xml', 'lang': 'en'},
    {'name': 'NYT Fashion', 'url': 'https://rss.nytimes.com/services/xml/rss/nyt/FashionandStyle.xml', 'lang': 'en'},
    {'name': 'Guardian Fashion', 'url': 'https://www.theguardian.com/fashion/rss', 'lang': 'en'},
    {'name': 'Dazed', 'url': 'https://www.dazeddigital.com/rss', 'lang': 'en'},
    {'name': 'i-D Magazine', 'url': 'https://i-d.vice.com/en_us/rss', 'lang': 'en'},
    {'name': 'SSENSE', 'url': 'https://www.ssense.com/en-us/feed', 'lang': 'en'},
    {'name': 'Grailed', 'url': 'https://www.grailed.com/drycleanonly/feed', 'lang': 'en'},
]

# РАСШИРЕННЫЙ СПИСОК БРЕНДОВ
BRANDS = [
    'Gucci', 'Prada', 'Dior', 'Chanel', 'Louis Vuitton', 'Balenciaga',
    'Versace', 'Hermes', 'Valentino', 'Fendi', 'Dolce & Gabbana',
    'Bottega Veneta', 'Loewe', 'Off-White', 'Balmain', 'Givenchy',
    'Burberry', 'Tom Ford', 'Alexander McQueen', 'Saint Laurent',
    'Celine', 'JW Anderson', 'Vetements', 'Comme des Garçons',
    'Maison Margiela', 'Acne Studios', 'Issey Miyake', 'Kenzo',
    'Moschino', 'Raf Simons', 'Rick Owens', 'Yves Saint Laurent',
    'Miu Miu', 'Moncler', 'Stone Island', 'Palm Angels',
    'Supreme', 'Palace', 'Stussy', 'Bape', 'Kith', 'Noah',
    'Aime Leon Dore', 'Carhartt WIP', 'Brain Dead', 'Awake NY',
    'Fear of God', 'Essentials', 'Rhude', 'Amiri', 'A-Cold-Wall',
    'Nike', 'Jordan', 'Adidas', 'New Balance', 'Converse',
]

# Эмодзи для брендов
BRAND_EMOJIS = {
    'Gucci': '🐍', 'Prada': '🔺', 'Dior': '🌹', 'Chanel': '👑',
    'Louis Vuitton': '🧳', 'Balenciaga': '👟', 'Versace': '🌞',
    'Hermes': '🟠', 'Valentino': '🔴', 'Fendi': '🟡',
    'Raf Simons': '🎨', 'Rick Owens': '⚫', 'Yves Saint Laurent': '💄',
    'Supreme': '🔴', 'Palace': '🔷', 'Bape': '🐒', 'Stussy': '🏄',
    'Nike': '👟', 'Jordan': '🅰️', 'Adidas': '❌', 'Off-White': '🟨',
    'Stone Island': '🧭', 'Moncler': '🦢', 'Bottega Veneta': '🟢',
    'Loewe': '🐘', 'Givenchy': '⚜️', 'Burberry': '🧥', 'Tom Ford': '🕶️',
    'Alexander McQueen': '💀', 'Celine': '⚡', 'Vetements': '🔵',
    'Maison Margiela': '🥼', 'Acne Studios': '🌀', 'Comme des Garçons': '❤️',
    'default': '👗'
}

class AdvancedAITranslator:
    def __init__(self):
        self.cache = {}
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def translate_with_deepl(self, text):
        """Перевод через DeepL"""
        try:
            # Используем неофициальный API DeepL
            url = "https://api-free.deepl.com/v2/translate"
            params = {
                'auth_key': 'free',
                'text': text,
                'target_lang': 'RU',
                'source_lang': 'EN'
            }
            response = self.session.post(url, data=params, timeout=10)
            if response.status_code == 200:
                result = response.json()
                return result['translations'][0]['text']
        except Exception as e:
            logger.warning(f"DeepL translation failed: {e}")
        return None

    def translate_with_google(self, text):
        """Перевод через Google Translate"""
        try:
            url = "https://translate.googleapis.com/translate_a/single"
            params = {
                'client': 'gtx',
                'sl': 'en',
                'tl': 'ru',
                'dt': 't',
                'q': text
            }
            response = self.session.get(url, params=params, timeout=10)
            if response.status_code == 200:
                result = response.json()
                return ''.join([item[0] for item in result[0] if item[0]])
        except Exception as e:
            logger.warning(f"Google translation failed: {e}")
        return None

    def translate_with_libre(self, text):
        """Перевод через LibreTranslate"""
        try:
            url = "https://libretranslate.de/translate"
            data = {
                'q': text,
                'source': 'en',
                'target': 'ru',
                'format': 'text'
            }
            response = self.session.post(url, json=data, timeout=15)
            if response.status_code == 200:
                result = response.json()
                return result['translatedText']
        except Exception as e:
            logger.warning(f"LibreTranslate failed: {e}")
        return None

    def smart_translate(self, text):
        """Умный перевод с использованием лучшего доступного сервиса"""
        if not text or len(text.strip()) < 10:
            return text

        # Проверяем кэш
        cache_key = hashlib.md5(text.encode()).hexdigest()
        if cache_key in self.cache:
            return self.cache[cache_key]

        # Пробуем разные переводчики в порядке качества
        translators = [
            self.translate_with_deepl,
            self.translate_with_google,
            self.translate_with_libre
        ]

        translated = None
        for translator in translators:
            translated = translator(text)
            if translated and len(translated) > len(text) * 0.3:  # Проверяем что перевод адекватный
                break

        # Если все переводчики не сработали, используем fallback
        if not translated:
            translated = self.fallback_translate(text)

        # Кэшируем результат
        if translated:
            self.cache[cache_key] = translated
            return translated

        return text

    def fallback_translate(self, text):
        """Резервный перевод на основе правил"""
        translations = {
            'collection': 'коллекция', 'sneakers': 'кроссовки', 'handbag': 'сумка',
            'accessories': 'аксессуары', 'runway': 'показ', 'designer': 'дизайнер',
            'luxury': 'люкс', 'limited': 'лимитированный', 'exclusive': 'эксклюзивный',
            'collaboration': 'коллаборация', 'release': 'релиз', 'announced': 'анонсировал',
            'launched': 'запустил', 'new': 'новый', 'innovative': 'инновационный',
            'revolutionary': 'революционный', 'capsule': 'капсула', 'campaign': 'кампания',
            'show': 'шоу', 'fashion': 'мода', 'style': 'стиль', 'trend': 'тренд',
            'premium': 'премиум', 'quality': 'качество', 'craftsmanship': 'мастерство'
        }

        translated = text
        for en, ru in translations.items():
            translated = re.sub(rf'\b{en}\b', ru, translated, flags=re.IGNORECASE)
        
        return translated

    def generate_unique_expert_comment(self, brand, content):
        """Генерирует уникальные экспертные комментарии на основе контента"""
        content_lower = content.lower()
        
        # Определяем тему новости
        if any(word in content_lower for word in ['коллаборация', 'collaboration', 'collab']):
            theme = 'collaboration'
            templates = [
                f"🤝 {styler.bold('СТРАТЕГИЧЕСКИЙ АЛЬЯНС')}: {brand} объединяет креативные вселенные, создавая уникальный синтез стилей.",
                f"🎭 {styler.bold('ТВОРЧЕСКИЙ ДИАЛОГ')}: Эта коллаборация демонстрирует как {brand} переосмысливает границы моды через диалог с новым партнером.",
                f"⚡ {styler.bold('СИНЕРГИЯ ТАЛАНТОВ')}: Совместный проект {brand} рождает неожиданные эстетические решения, объединяя лучшее из разных миров.",
            ]
        elif any(word in content_lower for word in ['архив', 'vintage', 'ретро', 'архивный']):
            theme = 'archive'
            templates = [
                f"🏛️ {styler.bold('ИСТОРИЧЕСКОЕ НАСЛЕДИЕ')}: {brand} возрождает архивные находки, переосмысливая классику через призму современности.",
                f"📜 {styler.bold'НОСТАЛЬГИЯ С ПРИЦЕЛОМ НА БУДУЩЕЕ')}: Обращаясь к архивам, {brand} демонстрирует timeless-подход к дизайну.",
                f"💎 {styler.bold('ВЕЧНЫЕ ЦЕННОСТИ')}: Архивная коллекция {brand} подтверждает - настоящая роскошь не подвластна времени.",
            ]
        elif any(word in content_lower for word in ['устойчив', 'sustainable', 'экологич', 'эко']):
            theme = 'sustainable'
            templates = [
                f"🌱 {styler.bold('ОСОЗНАННЫЙ ПОДХОД')}: {brand} задает новые стандарты в sustainable-моде, сочетая роскошь и ответственность.",
                f"♻️ {styler.bold('ЭКО-РЕВОЛЮЦИЯ')}: Коллекция демонстрирует commitment {brand} к устойчивому развитию и инновационным материалам.",
                f"🌍 {styler.bold('МОДА БУДУЩЕГО')}: {brand} переосмысливает люкс через призму экологичности и осознанного потребления.",
            ]
        elif any(word in content_lower for word in ['кроссовк', 'sneaker', 'обувь']):
            theme = 'sneakers'
            templates = [
                f"👟 {styler.bold('КУЛЬТУРНЫЙ ФЕНОМЕН')}: Новые кроссовки {brand} обещают стать must-have сезона, объединяя комфорт и стиль.",
                f"🔥 {styler.bold('ХАЙП-МАШИНА')}: {brand} запускает очередную волну ажиотажа в кроссовочной индустрии.",
                f"🎯 {styler.bold('ТОЧНЫЙ ВЫСТРЕЛ')}: Коллекция обуви {brand} идеально попадает в запросы современного потребителя.",
            ]
        else:
            theme = 'collection'
            templates = [
                f"🎨 {styler.bold('ТВОРЧЕСКИЙ ПРОРЫВ')}: {brand} переосмысливает каноны роскоши, предлагая свежий взгляд на привычные силуэты.",
                f"💫 {styler.bold('ИННОВАЦИЯ В ДЕТАЛЯХ')}: В новой коллекции {brand} прослеживается смелый эксперимент с материалами и конструкцией.",
                f"🔮 {styler.bold('ТРЕНДСЕТТЕР')}: {brand} задает вектор развития индустрии, предвосхищая запросы нового поколения.",
                f"🌟 {styler.bold('КУЛЬТУРНЫЙ ФЕНОМЕН')}: Релиз {brand} выходит за рамки моды, становясь арт-высказыванием.",
                f"🚀 {styler.bold('ТЕХНОЛОГИЧЕСКИЙ ПРОРЫВ')}: {brand} внедряет инновационные решения, меняющие представление о роскоши.",
            ]

        # Добавляем случайные факты в зависимости от темы
        random_facts = {
            'collaboration': [
                "Эксперты отмечают стратегическую важность этого партнерства для обоих брендов.",
                "Ожидается, что коллаборация станет одной из самых обсуждаемых в этом сезоне.",
                "Инсайдеры прогнозиют рекордный спрос на лимитированную коллекцию."
            ],
            'archive': [
                "Архивные модели получают современные апгрейды, сохраняя дух оригинала.",
                "Коллекционеры уже проявляют повышенный интерес к релизу.",
                "Исторические отсылки сочетаются с инновационными производственными техниками."
            ],
            'sustainable': [
                "Бренд инвестирует в исследования экологичных материалов следующего поколения.",
                "Устойчивый подход становится ключевым элементом ДНК бренда.",
                "Коллекция соответствует самым строгим экологическим стандартам."
            ],
            'sneakers': [
                "Технологические инновации в подошве и материалах впечатляют специалистов.",
                "Ожидается, что релиз установит новые стандарты в сегменте премиум-обуви.",
                "Дизайн идеально балансирует между спортивной функциональностью и стилем."
            ],
            'collection': [
                "Внимание к деталям и качество исполнения впечатляют даже искушенных критиков.",
                "Коллекция отражает современные тренды, сохраняя уникальный почерк бренда.",
                "Ожидается, что релиз окажет значительное влияние на fashion-индустрию."
            ]
        }

        main_comment = random.choice(templates)
        additional_fact = random.choice(random_facts.get(theme, random_facts['collection']))
        
        return f"{main_comment} {additional_fact}"

# Инициализация переводчика
translator = AdvancedAITranslator()

def parse_rss_date(date_string):
    """Парсит дату из RSS в универсальном формате"""
    if not date_string:
        return None
        
    date_formats = [
        '%a, %d %b %Y %H:%M:%S %Z',
        '%a, %d %b %Y %H:%M:%S %z',
        '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%d %H:%M:%S',
        '%d %b %Y %H:%M:%S'
    ]
    
    for fmt in date_formats:
        try:
            return datetime.strptime(date_string, fmt)
        except:
            continue
    
    try:
        parsed_time = feedparser._parse_date(date_string)
        if parsed_time:
            return datetime.fromtimestamp(time.mktime(parsed_time))
    except:
        pass
        
    return None

def is_recent_news(entry, max_hours_old=24):
    """Проверяет, является ли новость свежей"""
    date_fields = ['published', 'updated', 'created', 'pubDate']
    news_date = None
    
    for field in date_fields:
        date_str = getattr(entry, field, None)
        if date_str:
            parsed_date = parse_rss_date(date_str)
            if parsed_date:
                news_date = parsed_date
                break
    
    if not news_date:
        return False
    
    now = datetime.now()
    time_diff = now - news_date
    hours_diff = time_diff.total_seconds() / 3600
    
    return hours_diff <= max_hours_old

def generate_news_hash(entry, brand):
    """Генерирует уникальный хэш для новости"""
    content = f"{entry.title}_{entry.link}_{brand}"
    return hashlib.md5(content.encode()).hexdigest()

def extract_high_quality_image(url):
    """Агрессивный поиск качественных изображений"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        }
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        image_selectors = [
            'meta[property="og:image"]',
            'meta[name="twitter:image"]',
            'meta[property="twitter:image:src"]',
            'meta[name="og:image"]',
            'link[rel="image_src"]',
            'article img',
            '.wp-post-image',
            '.article-image img',
            '.post-image img',
            '.entry-content img',
            '.content img',
            'figure img',
            '.hero-image img',
            '.main-image img',
            '.featured-image img',
            '[class*="image"] img',
            'img[src*="large"]',
            'img[src*="medium"]',
            'img[src*="main"]',
            'img[src*="featured"]',
            'img'
        ]
        
        candidates = []
        for selector in image_selectors:
            elements = soup.select(selector)
            for element in elements:
                if selector.startswith('meta'):
                    image_url = element.get('content', '')
                else:
                    image_url = element.get('src') or element.get('data-src') or element.get('data-lazy-src')
                
                if image_url and is_high_quality_image(image_url):
                    score = rate_image_quality(image_url, element)
                    candidates.append((image_url, score))
        
        if candidates:
            candidates.sort(key=lambda x: x[1], reverse=True)
            best_image = candidates[0][0]
            
            if best_image.startswith('//'):
                best_image = 'https:' + best_image
            elif best_image.startswith('/'):
                best_image = urljoin(url, best_image)
            
            logger.info(f"✅ Found high-quality image")
            return best_image
            
    except Exception as e:
        logger.warning(f"Image extraction error: {e}")
    
    return None

def is_high_quality_image(url):
    """Проверяет, является ли изображение качественным"""
    if not url.startswith(('http://', 'https://')):
        return False
    
    valid_extensions = {'.jpg', '.jpeg', '.png', '.webp'}
    if not any(ext in url.lower() for ext in valid_extensions):
        return False
    
    excluded_terms = ['icon', 'logo', 'thumbnail', 'small', 'avatar', 'sprite', 'pixel']
    if any(term in url.lower() for term in excluded_terms):
        return False
    
    return True

def rate_image_quality(url, element):
    """Оценивает качество изображения"""
    score = 0
    
    if element.name == 'meta':
        score += 100
    
    width = element.get('width', '')
    height = element.get('height', '')
    if width and height:
        try:
            w = int(''.join(filter(str.isdigit, str(width))))
            h = int(''.join(filter(str.isdigit, str(height))))
            if w > 300 and h > 200:
                score += 50
            if w > 600 and h > 400:
                score += 30
        except:
            pass
    
    quality_indicators = ['large', 'xlarge', 'xxlarge', 'original', 'full', 'main', 'hero', 'featured']
    for indicator in quality_indicators:
        if indicator in url.lower():
            score += 20
    
    return score

def generate_unique_title(brand, content):
    """Генерирует уникальные заголовки на основе контента"""
    content_lower = content.lower()
    
    # Разные стили заголовков
    style_templates = {
        'question': [
            f"{brand} представляет новую коллекцию: что известно?",
            f"Что скрывает новый релиз {brand}?",
            f"{brand} меняет правила игры: готовы ли вы?",
        ],
        'news': [
            f"{brand} анонсирует революционную коллекцию",
            f"Эксклюзив: {brand} раскрывает детали нового релиза",
            f"Свежий дроп от {brand} уже здесь",
        ],
        'creative': [
            f"{brand} × Искусство: новый взгляд на моду",
            f"Революция стиля: {brand} задает тренды",
            f"Из будущего: {brand} представляет инновации",
        ],
        'minimal': [
            f"{brand} | Новая коллекция",
            f"{brand}: свежий релиз",
            f"{brand} обновляет каталог",
        ]
    }
    
    # Выбираем случайный стиль
    style = random.choice(list(style_templates.keys()))
    templates = style_templates[style]
    
    # Добавляем тематические заголовки в зависимости от контента
    if any(word in content_lower for word in ['коллаборация', 'collaboration']):
        templates += [
            f"{brand} объединяется с новым партнером",
            f"Коллаборация мечты: {brand} представляет совместный проект",
            f"{brand} × [Бренд]: неожиданный альянс",
        ]
    elif any(word in content_lower for word in ['архив', 'vintage']):
        templates += [
            f"{brand} возрождает архивные модели",
            f"Из прошлого в будущее: {brand} и классика",
            f"{brand} | Возвращение легенд",
        ]
    elif any(word in content_lower for word in ['устойчив', 'sustainable']):
        templates += [
            f"{brand} и экология: новый подход",
            f"Зеленая мода: {brand} представляет sustainable-коллекцию",
            f"{brand} заботится о планете",
        ]
    
    return random.choice(templates)

def create_unique_post(brand, content, image_url=None):
    """Создает уникальный пост с разнообразным форматированием"""
    emoji = BRAND_EMOJIS.get(brand, BRAND_EMOJIS['default'])
    
    # Генерируем уникальный заголовок
    title = generate_unique_title(brand, content)
    
    # Улучшаем и переводим контент
    translated_content = translator.smart_translate(content)
    
    # Улучшаем стиль контента
    styled_content = enhance_content_style(translated_content, brand)
    
    # Генерируем уникальный экспертный комментарий
    expert_comment = translator.generate_unique_expert_comment(brand, content)
    
    # Разные форматы постов
    post_formats = [
        # Формат 1: Классический
        lambda: f"{emoji} {styler.create_header(title)}\n\n"
                f"📖 {styled_content}\n\n"
                f"💎 {expert_comment}\n\n"
                f"{'─' * 30}\n\n"
                f"💬 {styler.italic('Обсуждаем в комментариях!')}",
        
        # Формат 2: С цитатой
        lambda: f"{emoji} {styler.create_header(title)}\n\n"
                f"📖 {styled_content}\n\n"
                f"✨ {styler.create_quote(expert_comment)}\n\n"
                f"{'・' * 20}\n\n"
                f"🎯 {styler.italic('Ваше мнение?')}",
        
        # Формат 3: Минималистичный
        lambda: f"{emoji} {styler.brand}\n\n"
                f"{styler.bold(title)}\n\n"
                f"{styled_content}\n\n"
                f"🌟 {expert_comment}\n\n"
                f"{'・' * 15}",
        
        # Формат 4: Детальный
        lambda: f"{emoji} {styler.create_header(title, '🚀')}\n\n"
                f"📰 {styled_content}\n\n"
                f"💡 {styler.bold('ЭКСПЕРТНОЕ МНЕНИЕ:')}\n"
                f"{expert_comment}\n\n"
                f"{'═' * 35}\n\n"
                f"💬 {styler.italic('Ждем ваши мысли ниже!')}"
    ]
    
    return random.choice(post_formats)()

def enhance_content_style(text, brand):
    """Улучшает стиль контента"""
    # Выделяем ключевые слова
    important_keywords = [
        'эксклюзивн', 'лимитирован', 'коллаборация', 'революцион',
        'инновацион', 'культов', 'дебют', 'премьер', 'анонс',
        'релиз', 'коллекция', 'капсула', 'архив', 'винтаж',
        'премиум', 'люкс', 'роскош', 'уникальн', 'особый'
    ]
    
    for keyword in important_keywords:
        if keyword in text.lower():
            pattern = re.compile(re.escape(keyword), re.IGNORECASE)
            text = pattern.sub(styler.bold(r'\g<0>'), text)
    
    # Выделяем бренд
    if brand in text:
        text = text.replace(brand, styler.bold(brand))
    
    # Добавляем эмодзи
    if any(word in text.lower() for word in ['кроссовки', 'sneakers']):
        text = "👟 " + text
    elif any(word in text.lower() for word in ['сумк', 'bag', 'handbag']):
        text = "👜 " + text
    elif any(word in text.lower() for word in ['одежд', 'collection']):
        text = "👗 " + text
    
    return text

def send_telegram_post(post, image_url=None):
    """Отправляет пост в Telegram"""
    try:
        if image_url:
            headers = {'User-Agent': 'Mozilla/5.0'}
            image_response = requests.get(image_url, headers=headers, timeout=10)
            if image_response.status_code == 200 and len(image_response.content) > 5000:
                url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto'
                data = {
                    'chat_id': CHANNEL,
                    'caption': post,
                    'parse_mode': 'HTML'
                }
                files = {'photo': ('image.jpg', image_response.content, 'image/jpeg')}
                response = requests.post(url, data=data, files=files, timeout=30)
                if response.status_code == 200:
                    logger.info("✅ Post sent successfully with image")
                    return True
        
        # Fallback: отправка без изображения
        url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
        data = {
            'chat_id': CHANNEL,
            'text': post,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True
        }
        response = requests.post(url, json=data, timeout=30)
        return response.status_code == 200
        
    except Exception as e:
        logger.error(f"❌ Telegram send error: {e}")
        return False

def find_and_send_single_news():
    """Ищет и отправляет ОДНУ уникальную новость"""
    random.shuffle(SOURCES)
    
    logger.info("🔍 Searching for ONE unique fresh news...")
    
    for source in SOURCES:
        try:
            logger.info(f"Checking {source['name']}...")
            feed = feedparser.parse(source['url'])
            
            if not feed.entries:
                continue
                
            # Ищем свежие записи
            fresh_entries = []
            for entry in feed.entries[:10]:
                if is_recent_news(entry, max_hours_old=24):
                    fresh_entries.append(entry)
            
            if not fresh_entries:
                continue
                
            logger.info(f"✅ Found {len(fresh_entries)} fresh news in {source['name']}")
            random.shuffle(fresh_entries)
            
            for entry in fresh_entries:
                title = getattr(entry, 'title', '')
                description = getattr(entry, 'description', '')
                link = getattr(entry, 'link', '')
                
                if not title:
                    continue
                
                # Ищем бренды в контенте
                full_content = f"{title} {description}".lower()
                
                for brand in BRANDS:
                    if brand.lower() in full_content:
                        # Проверяем, не отправляли ли уже эту новость
                        news_hash = generate_news_hash(entry, brand)
                        if is_news_sent(news_hash):
                            logger.info(f"⏭️ News already sent: {brand} - {title[:50]}...")
                            continue
                        
                        logger.info(f"🎯 Processing unique news: {brand}")
                        
                        try:
                            # Ищем картинку
                            image_url = extract_high_quality_image(link)
                            
                            # Создаем контент
                            original_content = f"{title}. {description}"
                            
                            # Создаем уникальный пост
                            post = create_unique_post(brand, original_content, image_url)
                            
                            # Отправляем пост
                            if send_telegram_post(post, image_url):
                                # Помечаем как отправленную
                                mark_news_sent(news_hash, brand, title)
                                logger.info(f"🎉 Successfully sent UNIQUE news about {brand}")
                                return True  # Отправляем только одну новость!
                            else:
                                logger.error(f"❌ Failed to send post about {brand}")
                                
                        except Exception as e:
                            logger.error(f"🔧 Error processing {brand}: {str(e)}")
                        
                        break  # Переходим к следующей новости после обработки бренда
                        
        except Exception as e:
            logger.error(f"❌ Error with source {source['name']}: {str(e)}")
            continue
            
    return False

def send_unique_curated_post():
    """Отправляет уникальный курируемый пост"""
    logger.info("🎨 Creating unique curated post...")
    
    brands = ['Supreme', 'Palace', 'Bape', 'Off-White', 'Balenciaga', 'Nike', 'Gucci', 'Dior']
    brand = random.choice(brands)
    
    curated_themes = [
        f"{brand} анонсирует выпуск новой капсульной коллекции, вдохновленной архивными находками и современным уличным искусством.",
        f"{brand} представляет революционную коллекцию, созданную в коллаборации с известным современным художником.",
        f"Новый дроп от {brand} сочетает элементы уличного стиля и высокой моды.",
        f"{brand} запускает sustainable коллекцию с использованием переработанных материалов.",
        f"Архивная находка: {brand} возрождает культовые модели с современными апгрейдами.",
    ]
    
    content = random.choice(curated_themes)
    post = create_unique_post(brand, content)
    
    if send_telegram_post(post):
        logger.info("✅ Unique curated post sent successfully!")
        return True
    
    return False

if __name__ == "__main__":
    # Инициализация базы данных
    init_database()
    cleanup_old_news(days=7)
    
    logger.info("🚀 Starting SINGLE NEWS BOT - One unique post per run")
    start_time = time.time()
    
    # Пробуем найти и отправить одну уникальную новость
    success = find_and_send_single_news()
    
    # Если не нашли уникальной новости, отправляем курируемый пост
    if not success:
        logger.info("📝 No unique news found, creating curated content...")
        send_unique_curated_post()
    
    execution_time = time.time() - start_time
    logger.info(f"⏱️ Execution time: {execution_time:.2f} seconds")
    logger.info("✅ Single news bot finished!")
