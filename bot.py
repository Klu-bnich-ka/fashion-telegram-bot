#!/usr/bin/env python3
# coding: utf-8
"""
Fashion News Bot — версия для GitHub Actions (HTML-aware + RSS + repo-state commit).
Запускается по cron (например, каждые 30 минут).
Secrets: BOT_TOKEN, CHANNEL (или CHAT_ID). Опционально: DEEPL_KEY.
"""

import os
import json
import time
import hashlib
import logging
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
import feedparser

# --------- Настройка логирования ---------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("fashion-bot")

# --------- Конфигурация ---------
BOT_TOKEN = os.getenv("BOT_TOKEN")  # required
CHANNEL = os.getenv("CHANNEL")      # required (chat_id or @channelusername)
DEEPL_KEY = os.getenv("DEEPL_KEY")  # optional

# Максимум новостей за запуск
MAX_SEND = 3

# Источники: RSS + листинговые страницы (парсер умеет работать и по RSS и по HTML)
SOURCES = [
    {
        "name": "Hypebeast",
        "rss": "https://hypebeast.com/fashion/feed",
        "list_url": "https://hypebeast.com/fashion",
        "base_url": "https://hypebeast.com",
    },
    {
        "name": "Highsnobiety",
        "rss": "https://www.highsnobiety.com/feed/",
        "list_url": "https://www.highsnobiety.com/page/1/",
        "base_url": "https://www.highsnobiety.com",
    },
    {
        "name": "SneakerNews",
        "rss": "https://sneakernews.com/feed/",
        "list_url": "https://sneakernews.com/",
        "base_url": "https://sneakernews.com",
    },
    # Можно легко добавить дополнительные источники здесь
]

# Ключевые слова для ранжирования (стиль 1)
PRIORITY_KEYWORDS = [
    "collaboration", "release", "limited", "exclusive", "new", "collection", "drop",
    "launch", "announce", "available", "first", "special", "edition", "capsule",
    "sneaker", "runway", "fashion week", "fw", "ss", "show", "creative director",
]

# Файл со списком отправленных хэшей (будет в репозитории и коммитится обратно)
SENT_FILE = "sent.json"

# HTTP сессия
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; FashionNewsBot/1.0; +https://github.com/)"
})


# --------- Утилиты ---------
def load_sent():
    try:
        if os.path.exists(SENT_FILE):
            with open(SENT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "sent" in data:
                    return set(data["sent"])
        return set()
    except Exception as e:
        logger.warning("Failed load sent.json: %s", e)
        return set()


def save_sent(sent_set):
    try:
        data = {"sent": sorted(list(sent_set))}
        with open(SENT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("Failed to write sent.json: %s", e)


def hash_url(url):
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def short_text(text, limit=600):
    if not text:
        return ""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "..."


# --------- Парсинг: RSS и HTML list pages ---------
def fetch_rss_items(rss_url, source_name, max_items=10):
    items = []
    try:
        feed = feedparser.parse(rss_url)
        for entry in feed.entries[:max_items]:
            title = getattr(entry, "title", "")
            link = getattr(entry, "link", "")
            summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
            published = getattr(entry, "published", "") or getattr(entry, "updated", "")
            if link:
                items.append({
                    "title": title,
                    "url": link,
                    "summary": summary,
                    "source": source_name,
                    "published": published
                })
    except Exception as e:
        logger.debug("RSS fetch failed for %s: %s", rss_url, e)
    return items


def fetch_html_list(list_url, base_url, source_name, max_items=12):
    """Делает лёгкий парсинг страницы-списка статей, берёт ссылки и заголовки.
       Делаем общий алгоритм: берем все <a> с href, фильтруем на внутренние ссылки и возвращаем уникальные.
    """
    items = []
    try:
        r = SESSION.get(list_url, timeout=12)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "html.parser")
        anchors = soup.find_all("a", href=True)
        seen = set()
        for a in anchors:
            href = a["href"]
            # Нормализуем
            if href.startswith("/"):
                href = urljoin(base_url, href)
            if not href.startswith("http"):
                continue
            # Ограничение: только внутри домена base_url
            if urlparse(href).netloc not in (urlparse(base_url).netloc,):
                continue
            if href in seen:
                continue
            seen.add(href)
            title = (a.get_text() or "").strip()
            if not title:
                # иногда заголовок в img alt
                img = a.find("img", alt=True)
                title = img["alt"].strip() if img else ""
            if not title:
                continue
            items.append({
                "title": title,
                "url": href,
                "summary": "",
                "source": source_name,
                "published": ""
            })
            if len(items) >= max_items:
                break
    except Exception as e:
        logger.debug("HTML list fetch failed for %s: %s", list_url, e)
    return items


# --------- Извлечение содержания конкретной статьи (умеренный HTML-парсинг) ---------
def extract_article_content(url, base_url):
    try:
        r = SESSION.get(url, timeout=12)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "html.parser")

        # Удаляем лишнее
        for tag in soup(["script", "style", "nav", "footer", "aside", "form", "noscript"]):
            tag.decompose()

        # Попытки найти основной блок: несколько распространённых селекторов
        selectors = [
            "article",
            ".post-content",
            ".entry-content",
            ".article-content",
            ".post-body",
            ".content"
        ]
        main = None
        for sel in selectors:
            main = soup.select_one(sel)
            if main and len(main.get_text(strip=True)) > 150:
                break
        if not main:
            main = soup.find("body")

        text = short_text(main.get_text(separator=" ", strip=True), limit=800)

        # Картинки: ищем большие изображения в статье
        images = []
        # приоритетные селекторы
        img_selectors = [
            "figure img",
            "img.featured",
            ".featured-image img",
            ".article-image img",
            ".post-image img",
            ".hero img",
            "img"
        ]
        for sel in img_selectors:
            for img in main.select(sel):
                src = img.get("data-src") or img.get("src") or img.get("data-lazy-src")
                if not src:
                    continue
                if src.startswith("//"):
                    src = "https:" + src
                if src.startswith("/"):
                    src = urljoin(base_url, src)
                if any(x in src.lower() for x in ("logo", "icon", "sprite", "thumb")):
                    continue
                if src not in images:
                    images.append(src)
                if len(images) >= 3:
                    break
            if images:
                break

        return text, images[:3]
    except Exception as e:
        logger.debug("Failed to extract article %s: %s", url, e)
        return "", []


# --------- Ранжирование и фильтрация (стиль 1) ---------
def score_item(item):
    title = (item.get("title") or "").lower()
    summary = (item.get("summary") or "").lower()
    text = f"{title} {summary}"

    score = 0
    # Ключевые слова повышают оценку
    for kw in PRIORITY_KEYWORDS:
        if kw in text:
            score += 5
    # короткие заголовки часто важнее
    if len(title.split()) <= 8:
        score += 1
    # слова "exclusive" / "limited" дают бонус
    if "exclusive" in text or "limited" in text:
        score += 3
    # бренды (примерный набор)
    for brand in ("nike", "adidas", "gucci", "supreme", "jordan", "balenciaga", "prada"):
        if brand in text:
            score += 2
    return score


# --------- Перевод (опционально через DeepL) ---------
def deepl_translate(text, target_lang="RU"):
    if not DEEPL_KEY:
        return text
    try:
        resp = requests.post(
            "https://api-free.deepl.com/v2/translate",
            data={"auth_key": DEEPL_KEY, "text": text, "target_lang": target_lang}
        )
        resp.raise_for_status()
        j = resp.json()
        if "translations" in j and len(j["translations"]) > 0:
            return j["translations"][0].get("text", text)
    except Exception as e:
        logger.warning("DeepL translation failed: %s", e)
    return text


# --------- Telegram publish ---------
class TelegramPublisher:
    def __init__(self, token, channel):
        self.token = token
        self.channel = channel
        self.base = f"https://api.telegram.org/bot{self.token}"

    def send_message(self, text, disable_preview=False):
        url = f"{self.base}/sendMessage"
        payload = {
            "chat_id": self.channel,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": disable_preview
        }
        try:
            r = requests.post(url, json=payload, timeout=25)
            r.raise_for_status()
            return True
        except Exception as e:
            logger.error("Telegram send_message failed: %s", e)
            return False

    def send_photos_group(self, caption, photos):
        # Если нет фото, отправляем как текст
        if not photos:
            return self.send_message(caption, disable_preview=False)

        # Отправляем первую фото с подписью
        first = photos[0]
        try:
            resp = requests.get(first, timeout=15)
            resp.raise_for_status()
            files = {"photo": ("image.jpg", resp.content, "image/jpeg")}
            data = {"chat_id": self.channel, "caption": caption, "parse_mode": "HTML"}
            send_url = f"{self.base}/sendPhoto"
            r = requests.post(send_url, files=files, data=data, timeout=30)
            r.raise_for_status()
            # Отправляем остальные маленькими фото (если есть)
            for p in photos[1:3]:
                try:
                    r2 = requests.get(p, timeout=12)
                    r2.raise_for_status()
                    files = {"photo": ("image.jpg", r2.content, "image/jpeg")}
                    data = {"chat_id": self.channel}
                    requests.post(send_url, files=files, data=data, timeout=25)
                    time.sleep(1)
                except Exception:
                    continue
            return True
        except Exception as e:
            logger.error("Failed to send photos: %s", e)
            return self.send_message(caption)


# --------- Основной поток ---------
def collect_candidates():
    candidates = []
    for src in SOURCES:
        name = src["name"]
        # Сначала пробуем RSS
        if src.get("rss"):
            ritems = fetch_rss_items(src["rss"], name, max_items=12)
            if ritems:
                for it in ritems:
                    it["base_url"] = src.get("base_url")
                candidates.extend(ritems)
                continue  # RSS дал список — используем его
        # RSS пуст или отсутствует — парсим листинг
        lit = fetch_html_list(src["list_url"], src["base_url"], name, max_items=12)
        candidates.extend(lit)
    return candidates


def pick_best(candidates, sent_set, max_count=MAX_SEND):
    # Оцениваем и сортируем по score и по source priority (порядок в SOURCES)
    source_priority = {s["name"]: i for i, s in enumerate(SOURCES)}
    for c in candidates:
        c["_score"] = score_item(c)
        c["_priority"] = source_priority.get(c.get("source"), 99)
    # Сортируем: 1) по score desc, 2) по приоритет источника asc, 3) по свежести (если есть)
    candidates.sort(key=lambda x: (-x["_score"], x["_priority"]))
    selected = []
    used_event_signatures = set()  # для предотвращения пересечений схожих заголовков
    for c in candidates:
        if len(selected) >= max_count:
            break
        url = c.get("url")
        if not url:
            continue
        h = hash_url(url)
        if h in sent_set:
            continue
        # event signature: нормализованный заголовок + первые 20 символов URL path
        title_sig = (c.get("title") or "").lower().strip()
        path = urlparse(url).path
        sig = title_sig[:80] + "|" + path[:40]
        if any(title_sig in s or s in title_sig for s in used_event_signatures):
            # похожая новость уже выбрана — пропускаем, чтобы избежать дубля
            continue
        used_event_signatures.add(title_sig)
        selected.append(c)
    return selected


def build_post(item):
    title = item.get("title") or ""
    source = item.get("source") or ""
    url = item.get("url") or ""
    base_url = item.get("base_url") or urlparse(url).scheme + "://" + urlparse(url).netloc
    # Извлекаем контент и картинки (умеренно)
    content, images = extract_article_content(url, base_url)
    if not content:
        content = item.get("summary") or ""

    # Перевод (если есть ключ)
    if DEEPL_KEY:
        title_ru = deepl_translate(title, target_lang="RU")
        content_ru = deepl_translate(content, target_lang="RU")
    else:
        title_ru = title
        content_ru = content

    # Создаём HTML-подпись
    excerpt = short_text(content_ru or content, limit=600)
    post = f"<b>{title_ru}</b>\n\n{excerpt}\n\n📰 Источник: {source}\n🔗 {url}"

    return post, images


def commit_sent_file_if_changed():
    """Этот скрипт не коммитит — коммит делается в workflow после выполнения.
       Но оставляем функцию как заглушку (можно расширить)."""
    pass


def main():
    if not BOT_TOKEN or not CHANNEL:
        logger.error("BOT_TOKEN and CHANNEL environment variables must be set.")
        return

    logger.info("Starting collector")
    sent = load_sent()
    candidates = collect_candidates()
    logger.info("Candidates collected: %d", len(candidates))

    selected = pick_best(candidates, sent, max_count=MAX_SEND)
    logger.info("Selected to send: %d", len(selected))

    publisher = TelegramPublisher(BOT_TOKEN, CHANNEL)
    sent_now = set()

    for item in selected:
        try:
            post, images = build_post(item)
            ok = publisher.send_photos_group(post, images)
            if ok:
                logger.info("Published: %s", item.get("title"))
                sent_now.add(hash_url(item.get("url")))
                # небольшая пауза между публикациями
                time.sleep(2)
            else:
                logger.error("Failed publishing: %s", item.get("title"))
        except Exception as e:
            logger.exception("Error processing item: %s", e)

    if sent_now:
        logger.info("Saving sent list (%d new)", len(sent_now))
        sent.update(sent_now)
        save_sent(sent)
    else:
        logger.info("No new items sent")

    logger.info("Done.")


if __name__ == "__main__":
    main()
