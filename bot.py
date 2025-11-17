import feedparser
import requests
import random
import os
import re

# Настройки из переменных окружения
BOT_TOKEN = os.environ['BOT_TOKEN']
CHANNEL = os.environ['CHANNEL']

# Английские RSS-ленты которые РАБОТАЮТ и содержат luxury контент
RSS_FEEDS = [
    'https://www.vogue.com/rss',                          # Vogue Global
    'https://www.harpersbazaar.com/feed/rss/',           # Harper's Bazaar
    'https://wwd.com/feed/',                             # Women's Wear Daily
    'https://www.businessoffashion.com/feed',            # Business of Fashion
    'https://www.thecut.com/rss/index.xml'               # The Cut (NYMag)
]

# Ключевые слова luxury брендов на английском
LUXURY_BRANDS = [
    'Raf Simons', 'Yves Saint Laurent', 'YSL', 'Gucci', 'Prada', 'Dior', 
    'Chanel', 'Louis Vuitton', 'Balenciaga', 'Versace', 'Hermes', 'Cartier',
    'Valentino', 'Fendi', 'Dolce & Gabbana', 'Bottega Veneta', 'Loewe',
    'Off-White', 'Rick Owens', 'Balmain', 'Givenchy', 'Burberry', 'Tom Ford'
]

# Эмодзи для брендов
BRAND_EMOJIS = {
    'chanel': '👑', 'dior': '🌹', 'gucci': '🐍', 'prada': '🔺', 
    'louis vuitton': '🧳', 'balenciaga': '👟', 'versace': '🌞', 
    'yves saint laurent': '💄', 'raf simons': '🎨', 'off-white': '🟨',
    'hermes': '🟠', 'default': '👗'
}

# Простой перевод ключевых фраз (для заголовков)
TRANSLATIONS = {
    'collection': 'коллекция',
    'fashion': 'мода',
    'runway': 'показ',
    'designer': 'дизайнер',
    'luxury': 'люкс',
    'new': 'новый',
    'trend': 'тренд',
    'style': 'стиль'
}

def get_brand_emoji(text):
    """Возвращает эмодзи для бренда"""
    if not text:
        return BRAND_EMOJIS['default']
    
    text_lower = text.lower()
    for brand, emoji in BRAND_EMOJIS.items():
        if brand in text_lower:
            return emoji
    return BRAND_EMOJIS['default']

def contains_luxury_brand(text):
    """Проверяет содержит ли текст упоминание luxury бренда"""
    if not text:
        return False
    text_lower = text.lower()
    return any(brand.lower() in text_lower for brand in LUXURY_BRANDS)

def clean_html(text):
    """Очищает HTML теги из текста"""
    if not text:
        return ""
    return re.sub('<[^<]+?>', '', text)

def simple_translate(text):
    """Простой перевод ключевых слов в тексте"""
    if not text:
        return text
    
    result = text
    for eng, rus in TRANSLATIONS.items():
        result = re.sub(r'\b' + eng + r'\b', rus, result, flags=re.IGNORECASE)
    return result

def send_news():
    for rss_url in RSS_FEEDS:
        try:
            print(f"🔍 Проверяем: {rss_url}")
            
            feed = feedparser.parse(rss_url)
            
            if not feed.entries:
                print("❌ Нет новостей в этой ленте")
                continue
                
            # Ищем новости про luxury бренды
            luxury_entries = []
            for entry in feed.entries[:15]:  # Проверяем больше новостей
                title = getattr(entry, 'title', '')
                description = getattr(entry, 'description', '')
                
                if contains_luxury_brand(title) or contains_luxury_brand(description):
                    luxury_entries.append(entry)
            
            if luxury_entries:
                # Берем случайную новость про бренды
                entry = random.choice(luxury_entries)
                emoji = get_brand_emoji(entry.title + ' ' + getattr(entry, 'description', ''))
                
                # "Переводим" заголовок
                title = clean_html(entry.title)
                russian_title = simple_translate(title)
                
                message = f"{emoji} {russian_title}\n\n"
                
                if hasattr(entry, 'description'):
                    desc = clean_html(entry.description)
                    desc = desc[:200] + '...' if len(desc) > 200 else desc
                    message += f"{desc}\n\n"
                
                message += f"🔗 {entry.link}\n"
                message += "#мода #luxury #бренды #тренды"
                
                # Добавляем хештеги брендов
                title_lower = title.lower()
                brand_hashtags = {
                    'gucci': 'Gucci', 'dior': 'Dior', 'chanel': 'Chanel', 
                    'prada': 'Prada', 'balenciaga': 'Balenciaga', 'versace': 'Versace',
                    'ysl': 'YSL', 'raf simons': 'RafSimons'
                }
                
                for brand_key, brand_tag in brand_hashtags.items():
                    if brand_key in title_lower:
                        message += f" #{brand_tag}"
                
                # Отправляем в канал
                url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
                data = {'chat_id': CHANNEL, 'text': message, 'parse_mode': 'HTML'}
                
                response = requests.post(url, data=data)
                if response.status_code == 200:
                    print(f"✅ ОТПРАВЛЕНО: {title}")
                    return True
                else:
                    print(f"❌ Ошибка отправки: {response.text}")
            else:
                print(f"❌ Не найдено новостей про luxury бренды в {rss_url}")
                        
        except Exception as e:
            print(f"❌ Ошибка: {e}")
    
    # Резервный вариант - любая модная новость
    print("🔄 Пробуем резервный вариант...")
    for rss_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(rss_url)
            if feed.entries:
                entry = feed.entries[0]
                emoji = random.choice(['👗', '👠', '👜'])
                
                title = clean_html(entry.title)
                russian_title = simple_translate(title)
                
                message = f"{emoji} {russian_title}\n\n"
                message += f"🔗 {entry.link}\n"
                message += "#мода #новости #тренды"
                
                url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
                data = {'chat_id': CHANNEL, 'text': message, 'parse_mode': 'HTML'}
                
                response = requests.post(url, data=data)
                if response.status_code == 200:
                    print(f"✅ ОТПРАВЛЕНО (резерв): {title}")
                    return True
        except:
            continue
    
    print("❌ Не удалось отправить ни одну новость")
    return False

if __name__ == "__main__":
    send_news()
