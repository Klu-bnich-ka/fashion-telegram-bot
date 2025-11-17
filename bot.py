import requests
import os
import re
import random
from bs4 import BeautifulSoup
import feedparser
from datetime import datetime
import time
import html

# Настройки
BOT_TOKEN = os.environ['BOT_TOKEN']
CHANNEL = os.environ['CHANNEL']

# БОЛЬШОЙ список источников (русские + английские)
SOURCES = [
    # Русские источники моды
    {'name': 'Vogue Россия', 'url': 'https://www.vogue.ru/fashion/rss/', 'lang': 'ru'},
    {'name': 'Buro 24/7', 'url': 'https://www.buro247.ru/rss.xml', 'lang': 'ru'},
    {'name': 'Elle Россия', 'url': 'https://www.elle.ru/rss/', 'lang': 'ru'},
    {'name': 'Cosmo Мода', 'url': 'https://www.cosmo.ru/fashion/rss/', 'lang': 'ru'},
    {'name': 'Grazia', 'url': 'https://grazia.ru/rss/', 'lang': 'ru'},
    {'name': 'Spletnik', 'url': 'https://www.spletnik.ru/rss.xml', 'lang': 'ru'},
    
    # Международные источники моды
    {'name': 'Vogue Global', 'url': 'https://www.vogue.com/rss', 'lang': 'en'},
    {'name': 'Business of Fashion', 'url': 'https://www.businessoffashion.com/feed', 'lang': 'en'},
    {'name': 'Hypebeast', 'url': 'https://hypebeast.com/fashion/feed', 'lang': 'en'},
    {'name': 'Highsnobiety', 'url': 'https://www.highsnobiety.com/feed/', 'lang': 'en'},
    {'name': 'Fashionista', 'url': 'https://fashionista.com/.rss', 'lang': 'en'},
    {'name': 'WWD', 'url': 'https://wwd.com/feed/', 'lang': 'en'},
    {'name': 'The Cut', 'url': 'https://www.thecut.com/rss/index.xml', 'lang': 'en'},
    {'name': 'Harper\'s Bazaar', 'url': 'https://www.harpersbazaar.com/feed/rss/', 'lang': 'en'},
    {'name': 'GQ Style', 'url': 'https://www.gq.com/feed/rss', 'lang': 'en'},
    {'name': 'Elle Global', 'url': 'https://www.elle.com/rss/all.xml', 'lang': 'en'},
    
    # Люкс издания
    {'name': 'Robb Report', 'url': 'https://robbreport.com/feed/', 'lang': 'en'},
    {'name': 'The Business of Fashion', 'url': 'https://www.businessoffashion.com/rss', 'lang': 'en'},
    
    # Уличная мода
    {'name': 'Hypebeast Style', 'url': 'https://hypebeast.com/feed', 'lang': 'en'},
    {'name': 'Sneaker News', 'url': 'https://sneakernews.com/feed/', 'lang': 'en'},
]

# Luxury бренды для фильтрации
LUXURY_BRANDS = [
    'Raf Simons', 'Rick Owens', 'Yves Saint Laurent', 'YSL', 'Gucci', 'Prada', 
    'Dior', 'Chanel', 'Louis Vuitton', 'Balenciaga', 'Versace', 'Hermes',
    'Valentino', 'Fendi', 'Dolce & Gabbana', 'Bottega Veneta', 'Loewe',
    'Off-White', 'Balmain', 'Givenchy', 'Burberry', 'Tom Ford', 'Alexander McQueen',
    'Saint Laurent', 'Celine', 'JW Anderson', 'Vetements', 'Comme des Garçons',
    'Maison Margiela', 'Acne Studios', 'Issey Miyake', 'Kenzo', 'Moschino'
]

def translate_to_russian(text):
    """Глубокий перевод на русский с учетом модного контекста"""
    if not text:
        return ""
        
    translations = {
        # Основные термины
        'collection': 'коллекция', 'fashion': 'мода', 'runway': 'показ',
        'designer': 'дизайнер', 'luxury': 'люкс', 'new': 'новый',
        'trend': 'тренд', 'style': 'стиль', 'brand': 'бренд',
        'launch': 'запуск', 'release': 'релиз', 'collaboration': 'коллаборация',
        'sneakers': 'кроссовки', 'handbag': 'сумка', 'accessories': 'аксессуары',
        'campaign': 'кампания', 'show': 'шоу', 'models': 'модели',
        'exclusive': 'эксклюзив', 'limited': 'лимитированный', 'edition': 'издание',
        
        # Глаголы
        'announced': 'анонсировал', 'presented': 'представил', 'released': 'выпустил',
        'unveiled': 'показал', 'debuted': 'дебютировал', 'teased': 'показал тизер',
        'collaborated': 'сотрудничал', 'designed': 'спроектировал',
        
        # Прилагательные
        'revolutionary': 'революционный', 'iconic': 'культовый', 'innovative': 'инновационный',
        'sustainable': 'устойчивый', 'avant-garde': 'авангардный', 'minimalist': 'минималистичный',
        'bold': 'смелый', 'elegant': 'элегантный', 'luxurious': 'роскошный',
        'exclusive': 'эксклюзивный', 'limited': 'лимитированный',
        
        # Существительные
        'aesthetics': 'эстетика', 'silhouette': 'силуэт', 'garment': 'одежда',
        'footwear': 'обувь', 'leather': 'кожа', 'fabric': 'ткань',
        'embroidery': 'вышивка', 'print': 'принт', 'color': 'цвет',
        'season': 'сезон', 'capsule': 'капсула', 'lookbook': 'лукбук',
        
        # Фразы
        'fashion week': 'неделя моды', 'ready to wear': 'готовая одежда',
        'haute couture': 'от кутюр', 'street style': 'уличный стиль',
        'fashion house': 'дом моды', 'creative director': 'креативный директор',
    }
    
    text = text.lower()
    for eng, rus in translations.items():
        text = re.sub(r'\b' + re.escape(eng) + r'\b', rus, text, flags=re.IGNORECASE)
    
    return text.capitalize()

def extract_main_content(text, max_length=600):
    """Извлекает самую важную информацию и ограничивает длину"""
    if not text:
        return ""
    
    # Удаляем HTML теги и лишние пробелы
    text = re.sub('<[^<]+?>', '', text)
    text = re.sub('\s+', ' ', text).strip()
    
    # Разбиваем на предложения
    sentences = re.split(r'[.!?]+', text)
    meaningful_sentences = []
    
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) > 25:  # Только значимые предложения
            # Ключевые слова, указывающие на важную информацию
            important_keywords = [
                'анонсировал', 'представил', 'выпустил', 'коллаборация', 
                'новая коллекция', 'показ', 'революционный', 'культовый',
                'эксклюзив', 'лимитированный', 'впервые', 'дебют',
                'инновационный', 'сотрудничал', 'проектировал'
            ]
            
            if any(keyword in sentence.lower() for keyword in important_keywords):
                meaningful_sentences.append(sentence)
    
    # Если нашли важные предложения - используем их
    if meaningful_sentences:
        content = '. '.join(meaning_sentences[:4]) + '.'
    else:
        # Иначе берем первые предложения
        content = '. '.join([s for s in sentences[:3] if len(s) > 20]) + '.'
    
    # Ограничиваем длину
    if len(content) > max_length:
        content = content[:max_length-3] + '...'
    
    return content

def extract_image_from_html(html_content, url):
    """Извлекает главное изображение из HTML"""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Ищем изображения в порядке приоритета
        selectors = [
            'meta[property="og:image"]',
            'meta[name="twitter:image"]',
            '.article-image img',
            '.post-image img',
            '.content img',
            'img'
        ]
        
        for selector in selectors:
            elements = soup.select(selector)
            for element in elements:
                if selector.startswith('meta'):
                    image_url = element.get('content', '')
                else:
                    image_url = element.get('src', '')
                
                if image_url and image_url.startswith('http'):
                    # Преобразуем относительные ссылки в абсолютные
                    if image_url.startswith('//'):
                        image_url = 'https:' + image_url
                    elif image_url.startswith('/'):
                        from urllib.parse import urljoin
                        image_url = urljoin(url, image_url)
                    
                    # Проверяем что это действительно изображение
                    if any(ext in image_url.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                        return image_url
                        
    except Exception as e:
        print(f"❌ Ошибка при извлечении изображения: {e}")
    
    return None

def generate_russian_title(english_title, brand):
    """Генерирует красивый русский заголовок"""
    
    title_templates = [
        f"{brand} представляет революционную коллекцию",
        f"Новая эра {brand}: что известно о грядущих релизах",
        f"{brand} меняет правила игры в мире моды", 
        f"Эксклюзив: секреты новой коллекции {brand}",
        f"Культовая коллаборация {brand} с новым креативным подходом",
        f"{brand} анонсирует сенсационный показ на неделе моды",
        f"Революция от {brand}: все детали нового проекта",
        f"{brand} представляет инновационные решения в дизайне",
        f"Новый виток в истории {brand}: что ждать от коллекции",
        f"{brand} выпускает лимитированную капсулу с уникальным дизайном"
    ]
    
    return random.choice(title_templates)

def create_luxury_post(brand, content, image_url=None):
    """Создает красивый пост про luxury бренд"""
    
    # Эмодзи для брендов
    brand_emojis = {
        'Raf Simons': '🎨', 'Rick Owens': '⚫', 'Yves Saint Laurent': '💄',
        'Gucci': '🐍', 'Prada': '🔺', 'Dior': '🌹', 'Chanel': '👑',
        'Louis Vuitton': '🧳', 'Balenciaga': '👟', 'Versace': '🌞',
        'Hermes': '🟠', 'Valentino': '🔴', 'Fendi': '🟡'
    }
    
    emoji = brand_emojis.get(brand, '🌟')
    
    # Генерируем заголовок
    title = generate_russian_title(content, brand)
    
    # Форматируем пост
    post = f"{emoji} <b>{title}</b>\n\n"
    post += f"📖 {content}\n\n"
    
    # Добавляем экспертный комментарий
    expert_notes = [
        "Инсайдеры отмечают революционный подход к дизайну и материалам.",
        "Коллекция уже вызвала ажиотаж среди ведущих fashion-критиков.",
        "Ожидается, что этот релиз станет культовым среди ценителей моды.",
        "Эксперты прогнозируют высокий спрос на новинку в люксовых бутиках.",
        "Дизайнеры бренда представили совершенно новую концепцию стиля.",
        "Fashion-сообщество активно обсуждает инновационные решения бренда.",
        "Коллаборация обещает стать одной из самых заметных в этом сезоне."
    ]
    
    post += f"💎 <i>{random.choice(expert_notes)}</i>"

    return post

def fetch_article_content(url):
    """Получает полное содержимое статьи"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        return response.text
        
    except Exception as e:
        print(f"❌ Ошибка при получении статьи: {e}")
        return None

def find_luxury_news():
    """Ищет новости про luxury бренды во всех источниках"""
    random.shuffle(SOURCES)  # Перемешиваем источники для разнообразия
    
    for source in SOURCES[:8]:  # Проверяем первые 8 источников
        try:
            print(f"🔍 Проверяем {source['name']}...")
            
            feed = feedparser.parse(source['url'])
            
            if not feed.entries:
                print(f"   ❌ Нет новостей в {source['name']}")
                continue
            
            # Перемешиваем записи для разнообразия
            entries = feed.entries[:15]
            random.shuffle(entries)
            
            for entry in entries:
                title = getattr(entry, 'title', '')
                description = getattr(entry, 'description', '')
                link = getattr(entry, 'link', '')
                
                if not title:
                    continue
                    
                content = f"{title}. {description}"
                
                # Ищем упоминания luxury брендов
                for brand in LUXURY_BRANDS:
                    if brand.lower() in content.lower():
                        print(f"   ✅ Найдена новость про {brand}")
                        
                        try:
                            # Получаем полную статью
                            article_html = fetch_article_content(link)
                            if not article_html:
                                continue
                                
                            # Извлекаем изображение
                            image_url = extract_image_from_html(article_html, link)
                            
                            # Обрабатываем контент
                            if source['lang'] == 'en':
                                russian_content = translate_to_russian(content)
                            else:
                                russian_content = content
                            
                            main_content = extract_main_content(russian_content)
                            
                            if len(main_content) < 50:  # Слишком короткий контент
                                continue
                                
                            # Создаем эксклюзивный пост
                            post = create_luxury_post(brand, main_content, image_url)
                            
                            # Отправляем в канал
                            if image_url:
                                # Пробуем отправить с картинкой
                                photo_url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto'
                                photo_data = {
                                    'chat_id': CHANNEL,
                                    'caption': post,
                                    'parse_mode': 'HTML'
                                }
                                
                                # Скачиваем изображение
                                try:
                                    image_response = requests.get(image_url, timeout=10)
                                    if image_response.status_code == 200:
                                        files = {'photo': image_response.content}
                                        response = requests.post(photo_url, data=photo_data, files=files)
                                        if response.status_code == 200:
                                            print(f"   ✅ Пост с изображением отправлен!")
                                            return True
                                except:
                                    pass  # Если не получилось с картинкой, пробуем без
                            
                            # Отправка без изображения
                            url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
                            data = {
                                'chat_id': CHANNEL,
                                'text': post,
                                'parse_mode': 'HTML'
                            }
                            
                            response = requests.post(url, data=data)
                            if response.status_code == 200:
                                print(f"   ✅ Пост отправлен!")
                                return True
                                
                        except Exception as e:
                            print(f"   ❌ Ошибка обработки статьи: {e}")
                            continue
            
        except Exception as e:
            print(f"❌ Ошибка с источником {source['name']}: {e}")
            continue
    
    return False

if __name__ == "__main__":
    print("🚀 Запуск расширенного парсера luxury новостей...")
    print(f"📚 Всего источников: {len(SOURCES)}")
    
    # Ищем настоящие новости про luxury бренды
    success = find_luxury_news()
    
    if not success:
        print("❌ Подходящих новостей не найдено в этом цикле")
