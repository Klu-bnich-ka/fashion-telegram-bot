import feedparser
import requests
import random
import os
import re

# Настройки из переменных окружения
BOT_TOKEN = os.environ['BOT_TOKEN']
CHANNEL = os.environ['CHANNEL']

# Русские RSS-ленты моды (попробуем с User-Agent)
RSS_FEEDS = [
    'https://www.vogue.ru/fashion/rss/',
    'https://www.buro247.ru/rss.xml',
    'https://www.elle.ru/rss/',
    'https://www.cosmo.ru/fashion/rss/',
    'https://graziadaily.ru/feed/'
]

# Ключевые слова luxury брендов
LUXURY_BRANDS = [
    'Raf Simons', 'Раф Симонс', 'Yves Saint Laurent', 'Ив Сен Лоран', 'YSL',
    'Gucci', 'Гуччи', 'Prada', 'Прада', 'Dior', 'Диор', 'Chanel', 'Шанель',
    'Louis Vuitton', 'Луи Виттон', 'LV', 'Balenciaga', 'Баленсиага',
    'Versace', 'Версаче', 'Hermes', 'Эрмес', 'Cartier', 'Картье',
    'Valentino', 'Валентино', 'Fendi', 'Фенди', 'Dolce & Gabbana', 'Дольче',
    'Bottega Veneta', 'Боттега', 'Loewe', 'Лоэв', 'Off-White', 'Офф-Уайт',
    'Rick Owens', 'Рик Оуэнс', 'Balmain', 'Бальмен', 'Givenchy', 'Живанши',
    'Burberry', 'Бербери', 'Tom Ford', 'Том Форд'
]

# Эмодзи для брендов
BRAND_EMOJIS = {
    'chanel': '👑', 'dior': '🌹', 'gucci': '🐍', 'prada': '🔺', 'louis vuitton': '🧳',
    'balenciaga': '👟', 'versace': '🌞', 'yves saint laurent': '💄', 
    'raf simons': '🎨', 'off-white': '🟨', 'hermes': '🟠', 'default': '👗'
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

def send_news():
    for rss_url in RSS_FEEDS:
        try:
            print(f"🔍 Проверяем: {rss_url}")
            
            # Пробуем с User-Agent чтобы обойти блокировку
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            feed = feedparser.parse(rss_url)
            
            if not feed.entries:
                print("❌ Нет новостей в этой ленте")
                continue
                
            # Ищем новости про luxury бренды
            luxury_entries = []
            for entry in feed.entries[:10]:
                title = getattr(entry, 'title', '')
                description = getattr(entry, 'description', '')
                
                if contains_luxury_brand(title) or contains_luxury_brand(description):
                    luxury_entries.append(entry)
            
            if luxury_entries:
                # Берем случайную новость про бренды
                entry = random.choice(luxury_entries)
                emoji = get_brand_emoji(entry.title + ' ' + getattr(entry, 'description', ''))
                
                title = clean_html(entry.title)
                message = f"{emoji} {title}\n\n"
                
                if hasattr(entry, 'description'):
                    desc = clean_html(entry.description)
                    desc = desc[:250] + '...' if len(desc) > 250 else desc
                    message += f"{desc}\n\n"
                
                message += f"🔗 {entry.link}\n"
                message += "#мода #luxury #бренды #тренды"
                
                # Добавляем хештеги брендов
                title_lower = title.lower()
                for brand in ['gucci', 'dior', 'chanel', 'prada', 'balenciaga', 'versace']:
                    if brand in title_lower:
                        message += f" #{brand}"
                
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
    
    print("❌ Не найдено новостей про luxury бренды ни в одной ленте")
    return False

if __name__ == "__main__":
    send_news()
