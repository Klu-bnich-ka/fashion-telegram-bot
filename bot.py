import requests
import os
import re
import random
from bs4 import BeautifulSoup
import feedparser
from datetime import datetime

# Настройки
BOT_TOKEN = os.environ['BOT_TOKEN']
CHANNEL = os.environ['CHANNEL']

# Русские СМИ для парсинга
SOURCES = [
    {'name': 'РБК', 'url': 'https://www.rbc.ru/rbcfreenews/', 'category': 'style'},
    {'name': 'Коммерсант', 'url': 'https://www.kommersant.ru/RSS/news.xml', 'category': 'lifestyle'},
    {'name': 'Forbes', 'url': 'https://www.forbes.ru/newrss.xml', 'category': 'lifestyle'},
    {'name': 'Buro 24/7', 'url': 'https://www.buro247.ru/news/fashion/', 'category': 'fashion'}
]

def translate_keywords(text):
    """Перевод ключевых модных терминов"""
    translations = {
        'fashion': 'мода', 'style': 'стиль', 'trend': 'тренд', 'collection': 'коллекция',
        'designer': 'дизайнер', 'luxury': 'люкс', 'runway': 'показ', 'model': 'модель',
        'brand': 'бренд', 'new': 'новый', 'exclusive': 'эксклюзив'
    }
    for eng, rus in translations.items():
        text = re.sub(r'\b' + eng + r'\b', rus, text, flags=re.IGNORECASE)
    return text

def extract_article_content(url):
    """Парсит полный текст статьи с картинкой"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Извлекаем заголовок
        title = soup.find('h1')
        title = title.get_text().strip() if title else "Без названия"
        
        # Извлекаем картинку
        image = soup.find('meta', property='og:image')
        image_url = image['content'] if image else None
        
        # Извлекаем основной текст (первые 2 абзаца)
        content = ""
        paragraphs = soup.find_all('p')[:3]
        for p in paragraphs:
            text = p.get_text().strip()
            if len(text) > 50:  # Только значимые абзацы
                content += text + "\n\n"
        
        return {
            'title': title,
            'content': content[:500] + '...' if len(content) > 500 else content,
            'image': image_url,
            'url': url
        }
    except Exception as e:
        print(f"❌ Ошибка парсинга: {e}")
        return None

def create_beautiful_post(article, source_name):
    """Создает красивый пост в стиле 'Топор'"""
    
    # Эмодзи для разных категорий
    emojis = {
        'fashion': '👗', 'style': '💎', 'business': '📈', 
        'lifestyle': '🌟', 'news': '📰'
    }
    
    emoji = emojis.get('fashion', '📌')
    
    # Перевод заголовка
    title = translate_keywords(article['title'])
    
    # Форматируем пост
    post = f"{emoji} <b>{title}</b>\n\n"
    
    if article['content']:
        post += f"📖 {article['content']}\n\n"
    
    # Добавляем источник и время
    post += f"📰 <i>{source_name}</i>\n"
    post += f"🕒 {datetime.now().strftime('%H:%M')}\n\n"
    
    # Хештеги
    post += "#мода #тренды #новости #стиль"
    
    # Добавляем брендовые хештеги если есть в тексте
    brands = ['gucci', 'dior', 'chanel', 'prada', 'balenciaga', 'versace']
    title_lower = title.lower()
    for brand in brands:
        if brand in title_lower:
            post += f" #{brand}"
    
    return post, article['image']

def send_telegram_post(text, image_url=None):
    """Отправляет пост в Telegram"""
    if image_url:
        # Пробуем отправить с картинкой
        url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto'
        data = {
            'chat_id': CHANNEL,
            'caption': text,
            'parse_mode': 'HTML'
        }
        files = {'photo': requests.get(image_url).content}
        response = requests.post(url, data=data, files=files)
    else:
        # Без картинки
        url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
        data = {
            'chat_id': CHANNEL,
            'text': text,
            'parse_mode': 'HTML'
        }
        response = requests.post(url, data=data)
    
    return response.status_code == 200

def find_fashion_news():
    """Ищет модные новости в RSS лентах"""
    for source in SOURCES:
        try:
            print(f"🔍 Проверяем {source['name']}...")
            
            # Парсим RSS
            feed = feedparser.parse(source['url'])
            
            if not feed.entries:
                continue
            
            # Ищем подходящие статьи
            for entry in feed.entries[:5]:
                title = getattr(entry, 'title', '')
                link = getattr(entry, 'link', '')
                
                # Ключевые слова для фильтрации
                keywords = ['мода', 'стиль', 'дизайнер', 'коллекция', 'показ', 
                           'Gucci', 'Dior', 'Chanel', 'Prada', 'бренд']
                
                if any(keyword.lower() in title.lower() for keyword in keywords):
                    print(f"✅ Найдена подходящая новость: {title}")
                    
                    # Парсим полную статью
                    article = extract_article_content(link)
                    if article and article['content']:
                        # Создаем красивый пост
                        post_text, image_url = create_beautiful_post(article, source['name'])
                        
                        # Отправляем в канал
                        if send_telegram_post(post_text, image_url):
                            print(f"✅ Пост отправлен: {title}")
                            return True
            
        except Exception as e:
            print(f"❌ Ошибка с {source['name']}: {e}")
    
    return False

def send_backup_news():
    """Резервный вариант - любая интересная новость"""
    backup_feeds = [
        'https://lenta.ru/rss/news',
        'https://www.vedomosti.ru/rss/news',
        'https://www.rbc.ru/rbcfreenews/'
    ]
    
    for feed_url in backup_feeds:
        try:
            feed = feedparser.parse(feed_url)
            if feed.entries:
                entry = feed.entries[0]
                
                # Создаем простой пост
                title = translate_keywords(entry.title)
                post = f"📌 <b>{title}</b>\n\n"
                post += f"🔗 {entry.link}\n\n"
                post += "#новости #тренды #актуальное"
                
                if send_telegram_post(post):
                    print(f"✅ Резервный пост отправлен: {title}")
                    return True
        except:
            continue
    
    return False

if __name__ == "__main__":
    print("🚀 Запуск парсера модных новостей...")
    
    # Пробуем найти модные новости
    if not find_fashion_news():
        print("❌ Модные новости не найдены, пробуем резерв...")
        send_backup_news()
