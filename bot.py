import feedparser
import requests
import random
import os

# Настройки из переменных окружения
BOT_TOKEN = os.environ['BOT_TOKEN']
CHANNEL = os.environ['CHANNEL']

# Русские RSS-ленты моды
RSS_FEEDS = [
    'https://www.vogue.ru/fashion/rss/',
    'https://www.elle.ru/rss/',
    'https://www.buro247.ru/rss.xml',
    'https://www.cosmo.ru/fashion/rss/',
    'https://grazia.ru/rss/'
]

# Ключевые слова модных брендов
FASHION_KEYWORDS = [
    'raf simons', 'раф симонс', 'yves saint laurent', 'ив сен лоран',
    'balenciaga', 'баленсиага', 'gucci', 'гуччи', 'prada', 'прада',
    'dior', 'диор', 'chanel', 'шанель', 'louis vuitton', 'луи витон'
]

EMOJIS = ['👗', '👠', '👜', '💄', '👒', '🕶️', '💍', '👛']

def contains_fashion_keywords(text):
    """Проверяет содержит ли текст ключевые слова моды"""
    if not text:
        return False
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in FASHION_KEYWORDS)

def send_news():
    for rss_url in RSS_FEEDS:
        try:
            print(f"🔍 Проверяем: {rss_url}")
            feed = feedparser.parse(rss_url)
            
            if not feed.entries:
                continue
                
            # Ищем новость про модные бренды
            for entry in feed.entries[:5]:
                title = getattr(entry, 'title', '')
                if contains_fashion_keywords(title):
                    emoji = random.choice(EMOJIS)
                    
                    message = f"{emoji} {title}\n\n"
                    if hasattr(entry, 'description'):
                        desc = entry.description[:200] + '...' if len(entry.description) > 200 else entry.description
                        message += f"{desc}\n\n"
                    
                    message += f"🔗 {entry.link}\n"
                    message += "#мода #тренды #бренды #luxury"
                    
                    # Отправляем в канал
                    url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
                    data = {'chat_id': CHANNEL, 'text': message, 'parse_mode': 'HTML'}
                    
                    response = requests.post(url, data=data)
                    if response.status_code == 200:
                        print(f"✅ Отправлено: {title}")
                        return True
                        
        except Exception as e:
            print(f"❌ Ошибка: {e}")
    
    print("❌ Не найдено подходящих новостей")
    return False

if __name__ == "__main__":
    send_news()
