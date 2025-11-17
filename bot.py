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
from urllib.parse import urljoin

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Настройки
BOT_TOKEN = os.environ['BOT_TOKEN']
CHANNEL = os.environ['CHANNEL']

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
    def strikethrough(text):
        return f"<s>{text}</s>"
    
    @staticmethod
    def code(text):
        return f"<code>{text}</code>"
    
    @staticmethod
    def highlight_keywords(text, keywords):
        """Выделяет ключевые слова в тексте"""
        for keyword in keywords:
            if keyword.lower() in text.lower():
                text = text.replace(keyword, TextStyler.bold(keyword))
                text = text.replace(keyword.lower(), TextStyler.bold(keyword))
                text = text.replace(keyword.upper(), TextStyler.bold(keyword))
        return text
    
    @staticmethod
    def create_header(text, emoji="✨"):
        return f"{emoji} {TextStyler.bold(text.upper())}"
    
    @staticmethod
    def create_quote(text, author=""):
        quote = f"❝{text}❞"
        if author:
            quote += f"\n\n— {TextStyler.italic(author)}"
        return quote

# Инициализация стилера
styler = TextStyler()

# Эмодзи для разных типов контента
CONTENT_EMOJIS = {
    'collection': '👗',
    'sneakers': '👟', 
    'collaboration': '🤝',
    'luxury': '💎',
    'streetwear': '🏙️',
    'vintage': '🕰️',
    'show': '🎪',
    'campaign': '📸',
    'exclusive': '🔒',
    'limited': '🏷️',
    'innovation': '🚀',
    'sustainable': '🌱'
}

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
    
    def translate_text(self, text):
        """Упрощенный перевод через бесплатные API"""
        try:
            # Используем LibreTranslate как основной
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
            logger.warning(f"Translation failed: {e}")
        
        # Fallback: базовый словарь перевода
        translations = {
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
            'announced': 'анонсировал',
            'launched': 'запустил',
            'new': 'новый',
            'innovative': 'инновационный',
            'revolutionary': 'революционный',
        }
        
        translated = text
        for en, ru in translations.items():
            translated = re.sub(rf'\b{en}\b', ru, translated, flags=re.IGNORECASE)
        
        return translated
    
    def generate_expert_comment(self, brand, content_type="collection"):
        """Генерирует уникальные экспертные комментарии"""
        
        comment_templates = {
            'collection': [
                f"🏆 {styler.bold('ЭКСКЛЮЗИВ')}: Коллекция {brand} демонстрирует эволюцию ДНК бренда, сочетая архивные мотивы с футуристичным видением.",
                f"🎨 {styler.bold('ТВОРЧЕСКИЙ ПРОРЫВ')}: {brand} переосмысливает каноны роскоши, предлагая свежий взгляд на привычные силуэты.",
                f"💫 {styler.bold('ИННОВАЦИЯ')}: В новой коллекции {brand} прослеживается смелый эксперимент с материалами и конструкцией.",
                f"🔮 {styler.bold('ТРЕНДСЕТТЕР')}: {brand} задает вектор развития индустрии, предвосхищая запросы нового поколения.",
                f"🌟 {styler.bold('КУЛЬТУРНЫЙ ФЕНОМЕН')}: Релиз {brand} выходит за рамки моды, становясь арт-высказыванием."
            ],
            'collaboration': [
                f"🤝 {styler.bold('СТРАТЕГИЧЕСКИЙ АЛЬЯНС')}: Коллаборация {brand} объединяет лучшее из разных миров, создавая уникальный продукт.",
                f"🎭 {styler.bold('ТВОРЧЕСКИЙ ДИАЛОГ')}: {brand} вступает в диалог с новым партнером, рождая неожиданные эстетические решения.",
                f"⚡ {styler.bold('СИНЕРГИЯ')}: Совместный проект {brand} демонстрирует мощь творческого объединения талантов.",
                f"🌉 {styler.bold('МОСТ МЕЖДУ КУЛЬТУРАМИ')}: {brand} строит мост между различными creative-сообществами."
            ],
            'sneakers': [
                f"👟 {styler.bold('КУЛЬТОВЫЙ РЕЛИЗ')}: Новые кроссовки {brand} обещают стать must-have сезона.",
                f"🔥 {styler.bold('ХАЙП-МАШИНА')}: {brand} запускает очередную волну ажиотажа в кроссовочной индустрии.",
                f"🎯 {styler.bold('ТОЧНЫЙ ВЫСТРЕЛ')}: Коллекция обуви {brand} идеально попадает в запросы современного потребителя.",
                f"💥 {styler.bold('РЕВОЛЮЦИЯ В ОБУВИ')}: {brand} переписывает правила игры в сегменте streetwear-обуви."
            ],
            'innovation': [
                f"🚀 {styler.bold('ТЕХНОЛОГИЧЕСКИЙ ПРОРЫВ')}: {brand} внедряет инновационные решения, меняющие представление о роскоши.",
                f"🌱 {styler.bold('УСТОЙЧИВОЕ РАЗВИТИЕ')}: {brand} демонстрирует commitment к экологичным практикам.",
                f"🔬 {styler.bold('НАУЧНЫЙ ПОДХОД')}: В основе коллекции {brand} лежат глубокие исследования и эксперименты.",
                f"💡 {styler.bold('ФУТУРОЛОГИЯ')}: {brand} заглядывает в будущее, предлагая смелые технологические решения."
            ]
        }
        
        # Определяем тип контента
        content_lower = content_type.lower()
        if any(word in content_lower for word in ['collab', 'collaboration', 'partnership']):
            category = 'collaboration'
        elif any(word in content_lower for word in ['sneakers', 'shoes', 'footwear']):
            category = 'sneakers'
        elif any(word in content_lower for word in ['innovation', 'technology', 'sustainable']):
            category = 'innovation'
        else:
            category = 'collection'
        
        templates = comment_templates.get(category, comment_templates['collection'])
        return random.choice(templates)
    
    def enhance_content_style(self, text, brand):
        """Улучшает стиль контента с выделением ключевых моментов"""
        
        # Ключевые слова для выделения
        important_keywords = [
            'эксклюзивн', 'лимитирован', 'коллаборация', 'революцион',
            'инновацион', 'культов', 'дебют', 'премьер', 'анонс',
            'релиз', 'коллекция', 'капсула', 'архив', 'винтаж',
            'премиум', 'люкс', 'роскош', 'уникальн', 'особый'
        ]
        
        # Выделяем ключевые слова
        for keyword in important_keywords:
            if keyword in text.lower():
                # Находим все вхождения и выделяем их
                pattern = re.compile(re.escape(keyword), re.IGNORECASE)
                text = pattern.sub(styler.bold(r'\g<0>'), text)
        
        # Выделяем названия брендов
        if brand in text:
            text = text.replace(brand, styler.bold(brand))
        
        # Добавляем эмодзи в зависимости от содержания
        if any(word in text.lower() for word in ['кроссовки', 'sneakers']):
            text = "👟 " + text
        elif any(word in text.lower() for word in ['сумк', 'bag', 'handbag']):
            text = "👜 " + text
        elif any(word in text.lower() for word in ['одежд', 'collection']):
            text = "👗 " + text
        elif any(word in text.lower() for word in ['аксессуар', 'accessor']):
            text = "💎 " + text
        
        return text

# Инициализация улучшенного переводчика
translator = AdvancedAITranslator()

def is_high_quality_image(url):
    """Проверяет, является ли изображение качественным"""
    if not url.startswith(('http://', 'https://')):
        return False
    
    # Проверяем расширения
    valid_extensions = {'.jpg', '.jpeg', '.png', '.webp'}
    if not any(ext in url.lower() for ext in valid_extensions):
        return False
    
    # Исключаем иконки и маленькие изображения
    excluded_terms = ['icon', 'logo', 'thumbnail', 'small', 'avatar', 'sprite', 'pixel']
    if any(term in url.lower() for term in excluded_terms):
        return False
    
    return True

def rate_image_quality(url, element):
    """Оценивает качество изображения"""
    score = 0
    
    # Приоритет для мета-тегов
    if element.name == 'meta':
        score += 100
    
    # Размеры из атрибутов
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
    
    # Ключевые слова в URL
    quality_indicators = ['large', 'xlarge', 'xxlarge', 'original', 'full', 'main', 'hero', 'featured']
    for indicator in quality_indicators:
        if indicator in url.lower():
            score += 20
    
    return score

def extract_high_quality_image(url):
    """Агрессивный поиск качественных изображений"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Расширенный список селекторов для изображений
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
            
            # Преобразуем относительные URL в абсолютные
            if best_image.startswith('//'):
                best_image = 'https:' + best_image
            elif best_image.startswith('/'):
                best_image = urljoin(url, best_image)
            
            logger.info(f"✅ Found high-quality image: {best_image}")
            return best_image
            
    except Exception as e:
        logger.warning(f"Image extraction error: {e}")
    
    return None

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
        translated_content = translator.translate_text(content)
        
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
                additional_translated = translator.translate_text(additional_content)
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

def generate_creative_title(brand, content):
    """Генерирует креативные заголовки"""
    
    content_lower = content.lower()
    
    # Определяем тип контента для релевантного заголовка
    if any(word in content_lower for word in ['коллаборация', 'collaboration']):
        templates = [
            f"{brand} × [Новый Партнер]: Революционная Коллаборация",
            f"Взрывной Альянс: {brand} Объединяется с Творческим Гением",
            f"{brand} + [Бренд]: Союз, Который Изменит Все",
        ]
    elif any(word in content_lower for word in ['архив', 'vintage', 'ретро']):
        templates = [
            f"Архивное Сокровище: {brand} Возрождает Легенду",
            f"Из Глубин Истории: {brand} Воскрешает Культовые Модели",
            f"Ностальгия по Великому: {brand} Возвращает Классику",
        ]
    elif any(word in content_lower for word in ['устойчив', 'sustainable', 'экологич']):
        templates = [
            f"{brand} Переосмысливает Роскошь: Эра Устойчивой Моды",
            f"Зеленая Революция: {brand} Запускает Eco-Коллекцию",
            f"Мода Будущего: {brand} и Осознанное Потребление",
        ]
    else:
        templates = [
            f"{brand} Представляет: Революция в Дизайне",
            f"Новая Эра {brand}: Коллекция, Которая Изменит Все",
            f"Эксклюзив: {brand} Раскрывает Секреты Нового Сезона",
            f"{brand} Бросает Вызов: Авангардный Подход к Моде",
            f"Культовый Релиз: {brand} Задает Новые Стандарты",
            f"Творческий Прорыв: {brand} и Искусство Моды",
            f"Роскошь Переосмысленная: {brand} Определяет Будущее",
            f"Мода как Искусство: {brand} Представляет Шедевр",
        ]
    
    return random.choice(templates)

def create_attractive_post(brand, content, image_url=None):
    """Создает привлекательный пост с улучшенным форматированием"""
    
    emoji = BRAND_EMOJIS.get(brand, BRAND_EMOJIS['default'])
    
    # Генерация заголовка
    title = generate_creative_title(brand, content)
    
    # Улучшаем стиль контента
    styled_content = translator.enhance_content_style(content, brand)
    
    # Генерация экспертного комментария
    expert_comment = translator.generate_expert_comment(brand, content)
    
    # Создаем пост с улучшенным форматированием
    post = f"{emoji} {styler.create_header(title)}\n\n"
    post += f"📖 {styled_content}\n\n"
    post += f"💎 {expert_comment}\n\n"
    
    # Добавляем разделитель и призыв к действию
    post += "─" * 30 + "\n\n"
    post += f"💬 {styler.italic('Что вы думаете об этом релизе? Обсуждаем в комментариях!')}"
    
    return post

def send_telegram_post(post, image_url=None):
    """Отправляет пост в Telegram"""
    try:
        if image_url:
            # Проверяем, доступно ли изображение
            headers = {'User-Agent': 'Mozilla/5.0'}
            image_response = requests.get(image_url, headers=headers, timeout=10)
            
            if image_response.status_code == 200 and len(image_response.content) > 5000:  # Минимум 5KB
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
                else:
                    logger.warning("🔄 Image post failed, falling back to text")
        
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

def find_and_send_news_with_images():
    """Основная функция с приоритетом картинок"""
    
    random.shuffle(SOURCES)
    posts_sent = 0
    max_attempts = 50  # Увеличиваем количество попыток для поиска картинок
    
    logger.info("🔄 Starting aggressive image search...")
    
    for source in SOURCES:
        if posts_sent >= 3:  # Максимум 3 поста за запуск
            break
            
        try:
            logger.info(f"🔍 Checking {source['name']}...")
            feed = feedparser.parse(source['url'])
            
            if not feed.entries:
                continue
            
            # Проверяем больше записей для поиска картинок
            entries = feed.entries[:20]
            random.shuffle(entries)
            
            for entry in entries:
                if posts_sent >= 3:
                    break
                    
                title = getattr(entry, 'title', '')
                description = getattr(entry, 'description', '')
                link = getattr(entry, 'link', '')
                
                if not title:
                    continue
                
                # Ищем бренды в контенте
                full_content = f"{title} {description}".lower()
                
                for brand in BRANDS:
                    if brand.lower() in full_content:
                        logger.info(f"✅ Found news about {brand}")
                        
                        try:
                            # Агрессивный поиск картинки
                            logger.info(f"🖼️ Aggressive image search for {brand}...")
                            image_url = extract_high_quality_image(link)
                            
                            # Если картинка не найдена, пробуем еще раз с другими параметрами
                            if not image_url:
                                logger.info("🔄 Retrying image search...")
                                time.sleep(1)
                                image_url = extract_high_quality_image(link)
                            
                            # Обрабатываем контент
                            original_content = f"{title}. {description}"
                            translated_content = translator.translate_text(original_content)
                            
                            if len(translated_content) < 100:
                                continue
                            
                            # Создаем привлекательный пост
                            post = create_attractive_post(brand, translated_content, image_url)
                            
                            # Отправляем пост
                            if send_telegram_post(post, image_url):
                                logger.info(f"🎉 Successfully posted about {brand} with image: {image_url is not None}")
                                posts_sent += 1
                                
                                # Пауза между постами
                                time.sleep(10)
                                break
                            else:
                                logger.error(f"❌ Failed to send post about {brand}")
                                
                        except Exception as e:
                            logger.error(f"🔧 Error processing {brand}: {str(e)}")
                            continue
                
        except Exception as e:
            logger.error(f"❌ Error with source {source['name']}: {str(e)}")
            continue
    
    return posts_sent

def send_curated_post_with_image():
    """Курируемый пост с поиском картинки"""
    logger.info("🎨 Creating curated post with image...")
    
    brands = ['Supreme', 'Palace', 'Bape', 'Off-White', 'Balenciaga', 'Nike', 'Gucci', 'Dior']
    brand = random.choice(brands)
    
    # Пробуем найти картинку для бренда через Google Images (упрощенный вариант)
    image_url = find_brand_image(brand)
    
    curated_contents = [
        f"{brand} анонсирует выпуск новой капсульной коллекции, вдохновленной архивными находками и современным уличным искусством. В релиз вошли ограниченные edition кроссовки, худи и аксессуары с уникальным дизайном и премиальными материалами.",
        f"{brand} представляет революционную коллекцию, созданную в коллаборации с известным современным художником. Эксклюзивные вещи с инновационными материалами и авангардным дизайном уже вызвали ажиотаж среди коллекционеров.",
        f"Новый дроп от {brand} сочетает элементы уличного стиля и высокой моды. Коллекция предлагает свежий взгляд на современный гардероб, объединяя комфорт и роскошь в каждом изделии.",
    ]
    
    content = random.choice(curated_contents)
    post = create_attractive_post(brand, content, image_url)
    
    if send_telegram_post(post, image_url):
        logger.info("✅ Curated post sent successfully!")
        return True
    
    return False

def find_brand_image(brand):
    """Упрощенный поиск изображений бренда"""
    try:
        # Заглушка для поиска изображений бренда
        # В реальной реализации можно использовать Google Custom Search API
        return None
    except:
        return None

if __name__ == "__main__":
    logger.info("🚀 Starting Enhanced Fashion Bot with Image Priority")
    
    start_time = time.time()
    
    # Пробуем найти и отправить новости с картинками
    posts_sent = find_and_send_news_with_images()
    
    # Если не нашли постов с картинками, отправляем курируемый
    if posts_sent == 0:
        logger.info("📝 No image posts found, creating curated content...")
        send_curated_post_with_image()
    
    execution_time = time.time() - start_time
    logger.info(f"⏱️ Execution time: {execution_time:.2f} seconds")
    logger.info(f"📊 Posts sent: {posts_sent}")
    logger.info("✅ Bot finished!")
