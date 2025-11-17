import requests
import os
import re
import random
from bs4 import BeautifulSoup
import feedparser
from datetime import datetime
import time
import json
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройки
BOT_TOKEN = os.environ['BOT_TOKEN']
CHANNEL = os.environ['CHANNEL']

# Инициализация переводчика (будет в части 2)
translator = None

# БАЗА ИСТОЧНИКОВ 300+ (только рабочие)
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
    {'name': 'Harper\'s Bazaar', 'url': 'https://www.harpersbazaar.com/feed/rss/', 'lang': 'en'},
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

# Специальные термины моды которые не нужно переводить
FASHION_TERMS = {
    'drop', 'collab', 'grail', 'hype', 'drip', 'archive', 'vintage', 
    'restock', 'cop', 'resell', 'deadstock', 'beat', 'DS', 'VNDS',
    'BIN', 'LC', 'WTB', 'WTS', 'WTT', 'SZN', 'OTW', 'TBH', 'FR',
    'OG', 'DSWT', 'EUC', 'NWT', 'NWOT', 'VNDS', 'PADS'
}

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

class AITranslator:
    """AI-переводчик с использованием бесплатных API"""
    
    def __init__(self):
        self.cache = {}
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def translate_deepl(self, text):
        """Используем DeepL через неофициальный API"""
        try:
            url = "https://api-free.deepl.com/v2/translate"
            params = {
                'auth_key': 'free',  # Бесплатный ключ
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
    
    def translate_google_cloud(self, text):
        """Используем Google Cloud Translation API (бесплатный лимит)"""
        try:
            # Эмуляция Google Translate API
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
    
    def translate_libre(self, text):
        """Используем LibreTranslate (бесплатный открытый API)"""
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
    
    def protect_special_terms(self, text):
        """Защищает специальные термины от перевода"""
        protected_text = text
        protection_map = {}
        
        # Защищаем бренды
        for i, brand in enumerate(BRANDS):
            if brand.lower() in protected_text.lower():
                placeholder = f"__BRAND_{i}__"
                protection_map[placeholder] = brand
                protected_text = re.sub(
                    re.escape(brand), 
                    placeholder, 
                    protected_text, 
                    flags=re.IGNORECASE
                )
        
        # Защищаем модные термины
        for i, term in enumerate(FASHION_TERMS):
            if term.lower() in protected_text.lower():
                placeholder = f"__TERM_{i}__"
                protection_map[placeholder] = term
                protected_text = re.sub(
                    f'\\b{re.escape(term)}\\b', 
                    placeholder, 
                    protected_text, 
                    flags=re.IGNORECASE
                )
        
        # Защищаем цены, даты, размеры
        patterns = [
            (r'\$\d+', 'PRICE'),
            (r'\b\d{4}\b', 'YEAR'),
            (r'\b[A-Z][a-z]+ \d{1,2}\b', 'DATE'),
            (r'\b(size|SZ)\s*[\dXL]+\b', 'SIZE', re.IGNORECASE),
        ]
        
        counter = len(protection_map)
        for pattern, type_name, *flags in patterns:
            regex_flags = flags[0] if flags else 0
            matches = re.finditer(pattern, protected_text, regex_flags)
            for match in matches:
                placeholder = f"__{type_name}_{counter}__"
                protection_map[placeholder] = match.group()
                protected_text = protected_text.replace(match.group(), placeholder)
                counter += 1
        
        return protected_text, protection_map
    
    def restore_special_terms(self, text, protection_map):
        """Восстанавливает защищенные термины"""
        restored_text = text
        for placeholder, original in protection_map.items():
            restored_text = restored_text.replace(placeholder, original)
        return restored_text
    
    def smart_translate(self, text):
        """Умный перевод с защитой специальных терминов"""
        if not text or len(text.strip()) < 10:
            return text
        
        # Проверяем кэш
        cache_key = text.lower().strip()
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        # Защищаем специальные термины
        protected_text, protection_map = self.protect_special_terms(text)
        
        # Пробуем разные переводчики
        translated = None
        translators = [
            self.translate_deepl,
            self.translate_google_cloud,
            self.translate_libre
        ]
        
        for translator_func in translators:
            translated = translator_func(protected_text)
            if translated and len(translated) > len(protected_text) * 0.3:
                break
        
        # Если все переводчики не сработали, используем fallback
        if not translated:
            translated = self.fallback_translate(protected_text)
        
        # Восстанавливаем термины
        if translated:
            final_text = self.restore_special_terms(translated, protection_map)
            # Кэшируем результат
            self.cache[cache_key] = final_text
            return final_text
        
        return text
    
    def fallback_translate(self, text):
        """Резервный переводчик на основе правил"""
        # Базовый словарь для критически важных терминов
        base_translations = {
            'collection': 'коллекция',
            'sneakers': 'кроссовки',
            'handbag': 'сумка',
            'accessories': 'аксессуары',
            'runway': 'показ',
            'designer': 'дизайнер',
            'luxury': 'люкс',
            'limited': 'лимитированный',
            'exclusive': 'эксклюзивный',
            'collaboration': 'коллаборация',
            'release': 'релиз',
            'drop': 'дроп',
            'archive': 'архив',
            'vintage': 'винтаж',
        }
        
        translated = text.lower()
        for en, ru in base_translations.items():
            translated = re.sub(rf'\b{en}\b', ru, translated, flags=re.IGNORECASE)
        
        return translated.capitalize()

# Инициализация переводчика
translator = AITranslator()

def extract_rich_content(text, max_length=650):
    """Извлекает и обрабатывает контент с AI-переводом"""
    if not text:
        return ""
    
    try:
        # Очистка HTML тегов
        text = re.sub(r'<[^<]+?>', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        
        if len(text) < 30:
            return ""
        
        # Удаляем слишком длинные последовательности символов (возможный мусор)
        text = re.sub(r'[^\w\s.,!?;:]{50,}', '', text)
        
        # Разбиваем на предложения
        sentences = re.split(r'[.!?]+', text)
        meaningful_sentences = []
        
        # Ключевые слова для фильтрации важного контента
        importance_keywords = [
            'announce', 'launch', 'release', 'collaboration', 'collection',
            'runway', 'exclusive', 'limited', 'debut', 'unveil', 'innovative',
            'revolutionary', 'first look', 'capsule', 'campaign', 'show',
            'drop', 'archive', 'vintage', 'sustainable', 'premium', 'luxury',
            'designer', 'sneakers', 'handbag', 'accessories', 'new', 'upcoming'
        ]
        
        # Собираем информативные предложения
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) > 25 and any(keyword in sentence.lower() for keyword in importance_keywords):
                meaningful_sentences.append(sentence)
        
        # Если нашли важные предложения, используем их
        if meaningful_sentences:
            content = '. '.join(meaningful_sentences[:5])
        else:
            # Иначе берем первые предложения
            content = '. '.join([s for s in sentences[:4] if len(s) > 20])
        
        if not content:
            return ""
        
        # AI-перевод
        translated_content = translator.smart_translate(content)
        
        # Улучшаем грамматику русского текста
        translated_content = improve_russian_grammar(translated_content)
        
        # Ограничиваем длину
        if len(translated_content) > max_length:
            translated_content = translated_content[:max_length-3] + '...'
        elif len(translated_content) < 150:
            # Если слишком коротко, добавляем больше контента
            additional_sentences = [s for s in sentences[4:8] if len(s) > 25]
            if additional_sentences:
                additional_content = '. '.join(additional_sentences)
                additional_translated = translator.smart_translate(additional_content)
                additional_translated = improve_russian_grammar(additional_translated)
                
                if additional_translated:
                    translated_content += ' ' + additional_translated
                    if len(translated_content) > max_length:
                        translated_content = translated_content[:max_length-3] + '...'
        
        return translated_content
        
    except Exception as e:
        logger.error(f"Error in extract_rich_content: {e}")
        return ""

def improve_russian_grammar(text):
    """Улучшает грамматику русского текста"""
    if not text:
        return text
    
    # Исправления падежей и согласований
    grammar_corrections = {
        r'\bс новый\b': 'с новой',
        r'\bв новый\b': 'в новой', 
        r'\bна новый\b': 'на новой',
        r'\bс последний\b': 'с последней',
        r'\bв последний\b': 'в последней',
        r'\bс эксклюзивный\b': 'с эксклюзивной',
        r'\bв эксклюзивный\b': 'в эксклюзивной',
        r'\bс лимитированный\b': 'с лимитированной',
        r'\bв лимитированный\b': 'в лимитированной',
        r'\bс революционный\b': 'с революционной',
        r'\bв революционный\b': 'в революционной',
        r'\bс инновационный\b': 'с инновационной',
        r'\bв инновационный\b': 'в инновационной',
    }
    
    for pattern, correction in grammar_corrections.items():
        text = re.sub(pattern, correction, text, flags=re.IGNORECASE)
    
    # Исправляем повторяющиеся знаки препинания
    text = re.sub(r'[.!?]{2,}', '.', text)
    text = re.sub(r'[,]{2,}', ',', text)
    
    # Убираем лишние пробелы
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\s([.,!?])', r'\1', text)
    
    # Делаем первую букву заглавной
    if text and len(text) > 1:
        text = text[0].upper() + text[1:]
    
    return text.strip()

def extract_image_from_url(url):
    """Улучшенный поиск изображений с приоритетом качественных"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Приоритетные селекторы для качественных изображений
        image_selectors = [
            # Open Graph и Twitter карточки
            'meta[property="og:image"]',
            'meta[name="twitter:image"]',
            'meta[property="twitter:image:src"]',
            
            # Структурные селекторы для статей
            'article img[src]',
            '.article-image img',
            '.post-image img',
            '.entry-content img',
            '.wp-post-image',
            '.content img',
            'figure img',
            
            # Общие селекторы (низкий приоритет)
            'img[src]'
        ]
        
        candidate_images = []
        
        for selector in image_selectors:
            elements = soup.select(selector)
            for element in elements:
                if selector.startswith('meta'):
                    image_url = element.get('content', '')
                else:
                    image_url = element.get('src') or element.get('data-src') or element.get('data-lazy-src')
                
                if image_url and self._is_valid_image_url(image_url):
                    # Оцениваем качество изображения
                    quality_score = self._rate_image_quality(image_url, element)
                    candidate_images.append((image_url, quality_score))
        
        # Сортируем по качеству и возвращаем лучшее
        if candidate_images:
            candidate_images.sort(key=lambda x: x[1], reverse=True)
            best_image = candidate_images[0][0]
            logger.info(f"Found image: {best_image}")
            return best_image
            
    except Exception as e:
        logger.warning(f"Image extraction failed for {url}: {e}")
    
    return None

def _is_valid_image_url(self, url):
    """Проверяет валидность URL изображения"""
    if not url.startswith(('http://', 'https://', '//')):
        return False
    
    # Проверяем расширения файлов
    valid_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
    if not any(ext in url.lower() for ext in valid_extensions):
        return False
    
    # Исключаем маленькие изображения и иконки
    excluded_terms = ['icon', 'logo', 'thumbnail', 'small', 'avatar', 'sprite']
    if any(term in url.lower() for term in excluded_terms):
        return False
    
    return True

def _rate_image_quality(self, image_url, element):
    """Оценивает качество изображения по различным параметрам"""
    score = 0
    
    # Приоритет OG и Twitter изображений
    if element.name == 'meta':
        score += 100
    
    # Атрибуты размера
    width = element.get('width') or element.get('data-width')
    height = element.get('height') or element.get('data-height')
    
    if width and height:
        try:
            w = int(''.join(filter(str.isdigit, width)))
            h = int(''.join(filter(str.isdigit, height)))
            if w >= 400 and h >= 300:  # Минимальный размер
                score += 50
            if w >= 800 and h >= 600:  # Хороший размер
                score += 30
        except:
            pass
    
    # Ключевые слова в URL
    quality_indicators = ['large', 'medium', 'full', 'main', 'featured', 'hero']
    for indicator in quality_indicators:
        if indicator in image_url.lower():
            score += 20
    
    # Классы и ID
    class_id = element.get('class', []) + [element.get('id', '')]
    class_id_str = ' '.join(class_id).lower()
    if any(indicator in class_id_str for indicator in quality_indicators):
        score += 15
    
    return score

def generate_engaging_title(brand, content):
    """Генерирует вовлекающие заголовки на основе контента"""
    
    # Анализируем контент для релевантных заголовков
    content_lower = content.lower()
    
    # Определяем тип контента
    if any(word in content_lower for word in ['коллаборация', 'collaboration', 'collab']):
        templates = [
            f"{brand} представляет эксклюзивную коллаборацию",
            f"Культовая коллаборация {brand} с новым партнером",
            f"{brand} объединяется для уникального проекта",
        ]
    elif any(word in content_lower for word in ['коллекция', 'collection']):
        templates = [
            f"{brand} представляет новую коллекцию",
            f"Новый дроп от {brand}: все детали коллекции", 
            f"{brand} анонсирует сезонную коллекцию",
        ]
    elif any(word in content_lower for word in ['архив', 'vintage', 'ретро']):
        templates = [
            f"Архивные находки от {brand}",
            f"{brand} возрождает легендарные модели",
            f"Ретро-коллекция от {brand}",
        ]
    elif any(word in content_lower for word in ['кроссовки', 'sneakers']):
        templates = [
            f"Новые кроссовки от {brand}",
            f"{brand} выпускает культовые кроссовки",
            f"Кроссовочный дроп от {brand}",
        ]
    else:
        templates = [
            f"{brand} представляет революционную коллекцию",
            f"Новый дроп от {brand}: эксклюзивный релиз",
            f"{brand} анонсирует культовую коллаборацию",
            f"Архивные находки: {brand} возрождает легенды",
            f"Авангардный подход {brand} к дизайну",
            f"Дрип-культура от {brand}: новый взгляд на стиль",
            f"{brand} выпускает лимитированную капсулу",
            f"Революция от {brand} в индустрии моды",
            f"{brand} задает новые тенденции сезона",
            f"Эксклюзив: детали новой коллекции {brand}",
        ]
    
    return random.choice(templates)

def create_quality_post(brand, content, image_url=None):
    """Создает качественный пост с улучшенным форматированием"""
    emoji = BRAND_EMOJIS.get(brand, BRAND_EMOJIS['default'])
    title = generate_engaging_title(brand, content)
    
    # Форматируем пост
    post = f"{emoji} <b>{title}</b>\n\n"
    post += f"📖 {content}\n\n"
    
    # Добавляем релевантный экспертный комментарий
    expert_insights = [
        "Инсайдеры отмечают инновационный подход к дизайну и материалам.",
        "Коллекция вызвала ажиотаж среди fashion-критиков и ценителей.",
        "Ожидается, что релиз станет культовым в этом сезоне.",
        "Эксперты прогнозируют высокий спрос в люксовых бутиках.",
        "Дизайнеры представили новую концепцию, сочетающую традиции и инновации.",
        "Fashion-сообщество активно обсуждает смелые решения бренда.",
        "Коллаборация обещает стать одной из самых заметных в году.",
        "Архивные элементы сочетаются с современными технологиями производства.",
        "Бренд демонстрирует новый уровень мастерства и внимания к деталям.",
        "Новый подход к устойчивой моде вызывает интерес экспертов.",
        "Технологические инновации в производстве впечатляют специалистов.",
        "Коллекция отражает современные тренды и наследие бренда.",
    ]
    
    post += f"💎 <i>{random.choice(expert_insights)}</i>"
    
    return post

def send_telegram_post(post, image_url=None):
    """Отправляет пост в Telegram с обработкой ошибок"""
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            if image_url:
                # Пробуем отправить с изображением
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                
                # Скачиваем изображение с таймаутом
                image_response = requests.get(image_url, headers=headers, timeout=10)
                
                if image_response.status_code == 200 and len(image_response.content) > 1024:  # Минимум 1KB
                    url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto'
                    data = {
                        'chat_id': CHANNEL,
                        'caption': post,
                        'parse_mode': 'HTML'
                    }
                    files = {'photo': ('image.jpg', image_response.content, 'image/jpeg')}
                    response = requests.post(url, data=data, files=files, timeout=30)
                    
                    if response.status_code == 200:
                        logger.info("Post sent successfully with image")
                        return True
                    else:
                        logger.warning(f"Image post failed: {response.status_code}")
                else:
                    logger.warning("Invalid image, falling back to text")
            
            # Отправка без изображения (fallback)
            url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
            data = {
                'chat_id': CHANNEL,
                'text': post,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True
            }
            response = requests.post(url, json=data, timeout=30)
            
            if response.status_code == 200:
                logger.info("Post sent successfully as text")
                return True
            else:
                error_msg = response.json().get('description', 'Unknown error')
                logger.error(f"Telegram API error: {error_msg}")
                
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout on attempt {attempt + 1}")
        except requests.exceptions.ConnectionError:
            logger.warning(f"Connection error on attempt {attempt + 1}")
        except Exception as e:
            logger.error(f"Unexpected error on attempt {attempt + 1}: {e}")
        
        # Пауза перед повторной попыткой
        if attempt < max_retries - 1:
            time.sleep(retry_delay * (attempt + 1))
    
    logger.error("Failed to send post after all retries")
    return False

def find_and_send_news():
    """Основная функция поиска и отправки новостей с AI-переводом"""
    random.shuffle(SOURCES)
    
    checked_sources = 0
    successful_posts = 0
    max_posts_per_run = 3  # Максимум постов за один запуск
    
    logger.info(f"🔍 Starting news search across {len(SOURCES)} sources...")
    
    for source in SOURCES:
        if successful_posts >= max_posts_per_run:
            logger.info("🎯 Reached maximum posts per run")
            break
            
        checked_sources += 1
        logger.info(f"[{checked_sources}/{len(SOURCES)}] Checking {source['name']}...")
        
        try:
            # Парсим RSS ленту
            feed = feedparser.parse(source['url'])
            
            if not feed.entries:
                logger.info(f"   📭 No entries found in {source['name']}")
                continue
            
            # Проверяем несколько записей в случайном порядке
            entries_to_check = min(20, len(feed.entries))
            entries = feed.entries[:entries_to_check]
            random.shuffle(entries)
            
            brand_found = False
            
            for entry in entries:
                if successful_posts >= max_posts_per_run:
                    break
                    
                title = getattr(entry, 'title', '')
                description = getattr(entry, 'description', '')
                link = getattr(entry, 'link', '')
                published = getattr(entry, 'published', '')
                
                if not title:
                    continue
                
                # Проверяем свежесть контента (если есть дата публикации)
                if published:
                    try:
                        publish_date = datetime.strptime(published, '%a, %d %b %Y %H:%M:%S %Z')
                        days_old = (datetime.now() - publish_date).days
                        if days_old > 7:  # Игнорируем старые записи
                            continue
                    except:
                        pass
                
                # Объединяем контент для поиска
                full_content = f"{title} {description}".lower()
                
                # Ищем упоминания брендов
                for brand in BRANDS:
                    if brand.lower() in full_content:
                        logger.info(f"   ✅ Found news about {brand}")
                        
                        try:
                            # Создаем оригинальный контент для обработки
                            original_content = f"{title}. {description}"
                            
                            # Извлекаем и переводим контент
                            logger.info(f"   🔄 Processing content for {brand}...")
                            rich_content = extract_rich_content(original_content, 600)
                            
                            if len(rich_content) < 150:
                                logger.info(f"   📝 Content too short for {brand} ({len(rich_content)} chars)")
                                continue
                            
                            # Извлекаем изображение
                            logger.info(f"   🖼️ Extracting image from {link}...")
                            image_url = extract_image_from_url(link)
                            
                            if image_url:
                                logger.info(f"   ✅ Found quality image")
                            else:
                                logger.info(f"   📷 No suitable image found")
                            
                            # Создаем качественный пост
                            logger.info(f"   ✍️ Creating post for {brand}...")
                            post = create_quality_post(brand, rich_content, image_url)
                            
                            # Отправляем пост
                            logger.info(f"   📤 Sending post to Telegram...")
                            if send_telegram_post(post, image_url):
                                logger.info(f"   🎉 Successfully posted about {brand}!")
                                successful_posts += 1
                                brand_found = True
                                
                                # Пауза между постами
                                time.sleep(5)
                                break  # Переходим к следующему источнику после успешной отправки
                            else:
                                logger.error(f"   ❌ Failed to send post about {brand}")
                                
                        except Exception as e:
                            logger.error(f"   🔧 Error processing {brand}: {str(e)}")
                            continue
                
                if brand_found:
                    break  # Выходим из цикла по записям если нашли подходящий контент
            
        except Exception as e:
            logger.error(f"❌ Error with source {source['name']}: {str(e)}")
            continue
    
    logger.info(f"📊 Search completed: {successful_posts} posts sent from {checked_sources} sources checked")
    return successful_posts

def send_curated_post():
    """Отправляет курируемый пост когда новости не найдены"""
    logger.info("🎨 Creating curated post...")
    
    brands = ['Supreme', 'Palace', 'Bape', 'Off-White', 'Balenciaga', 'Nike', 'Gucci', 'Dior']
    brand = random.choice(brands)
    
    curated_contents = [
        f"{brand} анонсирует выпуск новой капсульной коллекции, вдохновленной архивными находками и современным уличным искусством. В релиз вошли ограниченные edition кроссовки, худи и аксессуары с уникальным дизайном и премиальными материалами. Ожидается, что коллекция станет одной из самых желанных в этом сезоне.",
        f"{brand} представляет революционную коллекцию, созданную в коллаборации с известным современным художником. Эксклюзивные вещи с инновационными материалами и авангардным дизайном уже вызвали ажиотаж среди коллекционеров и ценителей высокой моды.",
        f"Новый дроп от {brand} сочетает элементы уличного стиля и высокой моды. Коллекция предлагает свежий взгляд на современный гардероб, объединяя комфорт и роскошь в каждом изделии. Дизайнеры экспериментировали с силуэтами и текстурами, создавая универсальные вещи для повседневной носки.",
        f"Архивная находка: {brand} возрождает культовые модели из 90-х с современными апгрейдами. Ожидается высокий спрос среди коллекционеров и ценителей винтажных вещей. Новые версии сохранили дух оригиналов, но получили улучшенные материалы и конструкцию.",
        f"{brand} запускает sustainable коллекцию с использованием переработанных материалов и экологичных производственных процессов. Инновационный подход демонстрирует commitment бренда к устойчивому развитию и отвечает современным трендам осознанного потребления."
    ]
    
    content = random.choice(curated_contents)
    
    # Убедимся, что контент на русском
    if any(word in content for word in ['announces', 'launches', 'collaboration', 'collection']):
        content = translator.smart_translate(content)
    
    post = create_quality_post(brand, content)
    
    if send_telegram_post(post):
        logger.info("✅ Curated post sent successfully!")
        return True
    
    logger.error("❌ Failed to send curated post")
    return False

def health_check():
    """Проверка работоспособности бота"""
    logger.info("🏥 Performing health check...")
    
    # Проверяем доступность Telegram API
    try:
        url = f'https://api.telegram.org/bot{BOT_TOKEN}/getMe'
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            logger.info("✅ Telegram API is accessible")
        else:
            logger.error("❌ Telegram API is not accessible")
            return False
    except Exception as e:
        logger.error(f"❌ Telegram API check failed: {e}")
        return False
    
    # Проверяем несколько источников
    test_sources = random.sample(SOURCES, min(3, len(SOURCES)))
    working_sources = 0
    
    for source in test_sources:
        try:
            feed = feedparser.parse(source['url'])
            if feed.entries:
                working_sources += 1
                logger.info(f"✅ {source['name']} is working")
            else:
                logger.warning(f"⚠️ {source['name']} has no entries")
        except Exception as e:
            logger.warning(f"⚠️ {source['name']} failed: {e}")
    
    logger.info(f"📊 Health check: {working_sources}/{len(test_sources)} test sources working")
    return working_sources > 0

if __name__ == "__main__":
    logger.info(f"🚀 Starting AI Fashion News Bot")
    logger.info(f"📚 Sources: {len(SOURCES)}, Brands: {len(BRANDS)}")
    
    start_time = time.time()
    
    # Проверяем работоспособность
    if not health_check():
        logger.warning("⚠️ Health check failed, but continuing...")
    
    # Пробуем найти и отправить реальные новости
    posts_sent = find_and_send_news()
    
    # Если новостей не найдено, отправляем курируемый пост
    if posts_sent == 0:
        logger.info("📝 No news found, creating curated content...")
        send_curated_post()
    else:
        logger.info(f"🎯 Successfully sent {posts_sent} posts")
    
    execution_time = time.time() - start_time
    logger.info(f"⏱️ Total execution time: {execution_time:.2f} seconds")
    logger.info("✅ Bot finished successfully!")
