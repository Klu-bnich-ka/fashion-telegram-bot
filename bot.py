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

EMOJIS = ['👗', '👠', '👜', '💄', '👒', '🕶️', '💍', '👛']

def send_news():
    for rss_url in RSS_FEEDS:
        try:
            print(f"🔍 Проверяем: {rss_url}")
            feed = feedparser.parse(rss_url)
            
            if not feed.entries:
                print("❌ Нет новостей в этой ленте")
                continue
                
            # Берем первую новость (без фильтрации)
            entry = feed.entries[0]
            emoji = random.choice(EMOJIS)
            
            message = f"{emoji} {entry.title}\n\n"
            
            if hasattr(entry, 'description'):
                # Чистим HTML теги
                import re
                desc = re.sub('<[^<]+?>', '', entry.description)
                desc = desc[:200] + '...' if len(desc) > 200 else desc
                message += f"{desc}\n\n"
            
            message += f"🔗 {entry.link}\n"
            message += "#мода #тренды #новости #стиль"
            
            # Отправляем в канал
            url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
            data = {'chat_id': CHANNEL, 'text': message, 'parse_mode': 'HTML'}
            
            response = requests.post(url, data=data)
            if response.status_code == 200:
                print(f"✅ ОТПРАВЛЕНО: {entry.title}")
                return True
            else:
                print(f"❌ Ошибка отправки: {response.text}")
                
        except Exception as e:
            print(f"❌ Ошибка: {e}")
    
    print("❌ Не удалось отправить ни одну новость")
    return False

if __name__ == "__main__":
    send_news()
