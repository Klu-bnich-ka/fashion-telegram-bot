import feedparser
import requests
import random
import os

# Настройки из переменных окружения
BOT_TOKEN = os.environ['BOT_TOKEN']
CHANNEL = os.environ['CHANNEL']

# АЛЬТЕРНАТИВНЫЕ RSS-ленты которые точно работают
RSS_FEEDS = [
    'https://rss.news.yahoo.com/rss/fashion',  # Yahoo Fashion
    'https://www.vogue.com/rss',               # Vogue Global
    'https://www.harpersbazaar.com/feed/rss/', # Harper's Bazaar
    'https://www.elle.com/rss/all.xml',        # Elle Global
    'https://www.gq.com/feed/rss'              # GQ Fashion
]

EMOJIS = ['👗', '👠', '👜', '💄', '👒', '🕶️', '💍', '👛']
FASHION_WORDS = ['fashion', 'style', 'trend', 'model', 'designer', 'collection', 'runway']

def contains_fashion_words(text):
    """Проверяет содержит ли текст слова связанные с модой"""
    if not text:
        return False
    text_lower = text.lower()
    return any(word in text_lower for word in FASHION_WORDS)

def send_news():
    for rss_url in RSS_FEEDS:
        try:
            print(f"🔍 Проверяем: {rss_url}")
            feed = feedparser.parse(rss_url)
            
            if not feed.entries:
                print("❌ Нет новостей в этой ленте")
                continue
                
            # Ищем новость про моду
            for entry in feed.entries[:5]:
                title = getattr(entry, 'title', '')
                
                if contains_fashion_words(title):
                    emoji = random.choice(EMOJIS)
                    
                    message = f"{emoji} {title}\n\n"
                    
                    if hasattr(entry, 'description'):
                        # Чистим HTML теги
                        import re
                        desc = re.sub('<[^<]+?>', '', entry.description)
                        desc = desc[:200] + '...' if len(desc) > 200 else desc
                        message += f"{desc}\n\n"
                    
                    message += f"🔗 {entry.link}\n"
                    message += "#fashion #style #trends #luxury"
                    
                    # Отправляем в канал
                    url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
                    data = {'chat_id': CHANNEL, 'text': message, 'parse_mode': 'HTML'}
                    
                    response = requests.post(url, data=data)
                    if response.status_code == 200:
                        print(f"✅ ОТПРАВЛЕНО: {title}")
                        return True
                    else:
                        print(f"❌ Ошибка отправки: {response.text}")
                        
        except Exception as e:
            print(f"❌ Ошибка: {e}")
    
    print("❌ Не найдено новостей про моду")
    return False

if __name__ == "__main__":
    send_news()
