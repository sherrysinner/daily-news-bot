"""每日新闻抓取、整理、企业微信推送与静态网页生成。"""
from __future__ import annotations

import html
import hashlib
from io import BytesIO
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import feedparser
import requests
from opencc import OpenCC
from PIL import Image
from lxml import html as lxml_html

try:
    from newspaper import Article
except ImportError:  # 允许在缺少可选正文库时保留 RSS 内容
    Article = None

RSS_SOURCES = {
    "国内外要闻": [("中新网国内", "https://www.chinanews.com.cn/rss/china.xml"), ("中新网国际", "https://www.chinanews.com.cn/rss/world.xml"), ("BBC中文", "https://feeds.bbci.co.uk/zhongwen/simp/rss.xml")],
    "科技": [("36氪", "https://36kr.com/feed")],
    "金融财经": [("中新网财经", "https://www.chinanews.com.cn/rss/finance.xml")],
    "娱乐体育": [("中新网文娱", "https://www.chinanews.com.cn/rss/culture.xml"), ("中新网体育", "https://www.chinanews.com.cn/rss/sports.xml")],
}
T2S_CONVERTER = OpenCC("t2s")
HOT_URLS = {"微博热搜": "https://tenapi.cn/v2/weibohot", "小红书热搜": "https://tenapi.cn/v2/xiaohongshuhot"}
SECTION_LIMITS = {"国内外要闻": 8, "科技": 4, "金融财经": 4, "娱乐体育": 4}
MAX_ITEMS_PER_SOURCE = 3
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
WALLSTREETCN_URL = "https://api-one.wallstcn.com/apiv1/content/lives?channel=global-channel&limit=30"
NEWSNOW_DEFAULT_BASE_URL = "https://newsnow.busiyi.world/api/s"
BEIJING_TIMEZONE = "Asia/Shanghai"


@dataclass
class NewsItem:
    title: str
    source: str
    url: str
    description: str
    content: str
    summary: str = ""
    article: str = ""
    section: str = ""
    image_url: str = ""
    image_urls: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class HotTopic:
    title: str
    url: str
    description: str


@dataclass(frozen=True)
class GeoBrief:
    """仅依据当日新闻生成的一条地缘政治观察。"""

    title: str
    event: str
    impact: str
    watch: str


@dataclass
class Config:
    deepseek_api_key: str
    webhook_url: str
    page_url: str


def load_config() -> Config | None:
    """读取必要配置；缺失时只记录错误并安全退出。"""
    values = {key: os.getenv(key, "").strip() for key in ("DEEPSEEK_API_KEY", "WECHAT_WEBHOOK_URL", "PAGE_URL")}
    missing = [key for key, value in values.items() if not value]
    if missing:
        logging.error("缺少环境变量：%s", "、".join(missing))
        return None
    return Config(values["DEEPSEEK_API_KEY"], values["WECHAT_WEBHOOK_URL"], values["PAGE_URL"].rstrip("/"))


def plain_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value or "")).strip()


def to_simplified(value: str) -> str:
    """将抓取到的繁体中文统一为简体，英文内容保持不变。"""
    return T2S_CONVERTER.convert(value or "")


def clean_editorial_title(value: str) -> str:
    """只接受 AI 给出的中文标题，避免英文标题直接进入日报。"""
    title = to_simplified(plain_text(value))
    return title if re.search(r"[\u4e00-\u9fff]", title) else ""


def canonical_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def fetch_rss_sources(session: requests.Session) -> list[NewsItem]:
    items, seen = [], set()
    for section, sources in RSS_SOURCES.items():
        for source, feed_url in sources:
            try:
                response = session.get(feed_url, timeout=20, headers={"User-Agent": "daily-news-bot/1.0"})
                response.raise_for_status()
                feed = feedparser.parse(response.content)
                for entry in feed.entries:
                    title, url = to_simplified(plain_text(entry.get("title", ""))), entry.get("link", "").strip()
                    key = (title, canonical_url(url))
                    if not title or not url or key in seen:
                        continue
                    seen.add(key)
                    media = entry.get("media_content", []) or entry.get("media_thumbnail", []) or entry.get("enclosures", [])
                    image_url = media[0].get("url", "") if media and isinstance(media[0], dict) else ""
                    items.append(NewsItem(title, source, url, to_simplified(plain_text(entry.get("summary", ""))), "", image_url=image_url, section=section))
                logging.info("RSS 成功：%s，共 %d 条", source, len(feed.entries))
            except Exception as exc:  # noqa: BLE001 - 网络源必须隔离错误
                logging.warning("RSS 抓取失败：%s，%s", source, exc)
    return items


def fetch_wallstreetcn(session: requests.Session) -> list[NewsItem]:
    """抓取华尔街见闻公开实时财经流。"""
    try:
        rows = session.get(WALLSTREETCN_URL, timeout=20, headers={"User-Agent": "Mozilla/5.0"}).json()["data"]["items"]
        return [NewsItem(to_simplified(plain_text(row.get("title", ""))), "华尔街见闻", row.get("uri", "https://wallstreetcn.com"), to_simplified(plain_text(row.get("content_text", ""))), to_simplified(plain_text(row.get("content_text", ""))), section="金融财经") for row in rows if row.get("title")][:20]
    except Exception as exc:  # noqa: BLE001
        logging.warning("华尔街见闻抓取失败：%s", exc)
        return []


def newsnow_base_url() -> str:
    """读取可选的自建 NewsNow 地址，未配置时使用公开实例。"""
    return os.getenv("NEWSNOW_BASE_URL", NEWSNOW_DEFAULT_BASE_URL).strip().rstrip("/") or NEWSNOW_DEFAULT_BASE_URL


def fetch_newsnow_payload(session: requests.Session, platform_id: str) -> list[dict[str, Any]]:
    response = session.get(
        newsnow_base_url(),
        params={"id": platform_id, "latest": ""},
        timeout=20,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("status") not in {"success", "cache"}:
        raise ValueError(f"NewsNow 返回状态异常：{payload.get('status') if isinstance(payload, dict) else '无效响应'}")
    items = payload.get("items", [])
    return items if isinstance(items, list) else []


def is_expected_url(url: str, expected_domain: str) -> bool:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    domain = expected_domain.lower()
    return parsed.scheme == "https" and (host == domain or host.endswith(f".{domain}"))


def beijing_today(now: datetime | None = None) -> str:
    """使用北京时间命名日报，避免 GitHub 运行器的 UTC 日期跨日。"""
    from zoneinfo import ZoneInfo

    zone = ZoneInfo(BEIJING_TIMEZONE)
    return (now.astimezone(zone) if now else datetime.now(zone)).date().isoformat()


def fetch_newsnow_platform(
    session: requests.Session,
    platform_id: str,
    source: str,
    expected_domain: str,
    section: str,
) -> list[NewsItem]:
    """读取 NewsNow 单个平台数据，并阻止非预期域名链接进入日报。"""
    try:
        items = []
        for row in fetch_newsnow_payload(session, platform_id):
            title = to_simplified(plain_text(str(row.get("title", "")))) if isinstance(row, dict) else ""
            url = str(row.get("mobileUrl") or row.get("url") or "").strip() if isinstance(row, dict) else ""
            if title and is_expected_url(url, expected_domain):
                items.append(NewsItem(title, source, url, title, title, section=section))
        logging.info("NewsNow 成功：%s，共 %d 条", source, len(items))
        return items
    except Exception as exc:  # noqa: BLE001 - 单个平台失败不能中断日报
        logging.warning("NewsNow 抓取失败：%s，%s", source, exc)
        return []


def fetch_newsnow_hot_words(session: requests.Session, platform_id: str) -> list[str]:
    """从 NewsNow 读取微博等热榜标题，最多保留五条。"""
    return [item.title for item in fetch_newsnow_platform(session, platform_id, "微博", "weibo.com", "")[:5]]


def fetch_newsnow_hot_topics(
    session: requests.Session,
    platform_id: str,
    expected_domain: str = "weibo.com",
    description: str = "点击查看微博实时讨论",
) -> list[HotTopic]:
    """保留热词搜索链接；公开源没有正文时不凭关键词编造梗概。"""
    try:
        topics = []
        for row in fetch_newsnow_payload(session, platform_id):
            if not isinstance(row, dict):
                continue
            title = to_simplified(plain_text(str(row.get("title", ""))))
            url = str(row.get("mobileUrl") or row.get("url") or "").strip()
            if title and is_expected_url(url, expected_domain):
                topics.append(HotTopic(title, url, description))
            if len(topics) == 5:
                break
        return topics
    except Exception as exc:  # noqa: BLE001
        logging.warning("微博热搜详情抓取失败：%s", exc)
        return []


def extract_body_image_urls(page_html: str, page_url: str) -> list[str]:
    """按正文中的出现顺序取图，不从页头、页尾或推荐区取图。"""
    if not page_html:
        return []
    try:
        document = lxml_html.fromstring(page_html)
        containers = document.xpath("//article | //main")
        if not containers:
            containers = document.xpath(
                "//*[contains(translate(concat(' ', normalize-space(@class), ' ', normalize-space(@id), ' '), "
                "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'article') or "
                "contains(translate(concat(' ', normalize-space(@class), ' ', normalize-space(@id), ' '), "
                "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'content') or "
                "contains(translate(concat(' ', normalize-space(@class), ' ', normalize-space(@id), ' '), "
                "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'detail')]"
            )
        images = containers[0].xpath(".//img") if containers else []
        result: list[str] = []
        rejected = ("logo", "icon", "avatar", "qrcode", "advert", "ad-", "banner", "sponsor", "footer", "header")
        for image in images:
            value = next((image.get(name, "").strip() for name in ("data-src", "data-original", "data-lazy-src", "src") if image.get(name)), "")
            url = urljoin(page_url, value)
            label = " ".join((url, image.get("alt", ""), image.get("class", ""))).lower()
            if not url.startswith(("http://", "https://")) or any(word in label for word in rejected):
                continue
            if url not in result:
                result.append(url)
        return result[:3]
    except Exception as exc:  # noqa: BLE001 - 页面结构异常时宁可不展示错误图片
        logging.info("正文图片候选提取失败：%s", exc)
        return []


def extract_article(item: NewsItem) -> NewsItem:
    # 中新网 RSS 的 media 图经常是频道通用图，与具体报道无关，宁可不显示也不误导读者。
    if item.source.startswith("中新网"):
        item.image_url = ""
        item.image_urls = []
    if Article is None or item.source == "华尔街日报":
        return item
    try:
        article = Article(item.url, language="zh")
        article.download()
        article.parse()
        item.content = to_simplified(plain_text(article.text))
        if item.content and not item.source.startswith("中新网"):
            candidates = extract_body_image_urls(article.html, item.url)
            if not candidates and article.top_image:
                candidates = [article.top_image]
            item.image_urls = list(dict.fromkeys(url for url in candidates if url))[:2]
            item.image_url = item.image_urls[0] if item.image_urls else item.image_url
    except Exception as exc:  # noqa: BLE001
        logging.warning("正文提取失败：%s，%s", item.title, exc)
    return item


def is_displayable_image(url: str, seen_images: set[str]) -> bool:
    """通用站点占位图容易重复或与新闻无关，重复图片不再展示。"""
    return url.startswith(("http://", "https://", "images/")) and url not in seen_images


def cache_one_image(session: requests.Session, item: NewsItem, image_dir: Path, image_url: str) -> str:
    """下载并压缩一张配图，图片仅存在于本次日报静态产物中。"""
    if item.source.startswith("中新网") or not image_url.startswith(("http://", "https://")):
        return ""
    try:
        response = session.get(
            image_url,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0", "Referer": item.url},
        )
        response.raise_for_status()
        content = response.content
        if not content or len(content) > 5 * 1024 * 1024:
            raise ValueError("不是可保存的新闻图片")
        if any(word in image_url.lower() for word in ("logo", "icon", "avatar", "qrcode", "advert")):
            raise ValueError("非正文配图")
        image = Image.open(BytesIO(content)).convert("RGB")
        if min(image.size) < 160 or max(image.size) / min(image.size) > 4:
            raise ValueError("图片尺寸不适合作为新闻配图")
        image.thumbnail((1200, 900))
        output = BytesIO()
        for quality in (82, 74, 66, 58):
            output.seek(0)
            output.truncate(0)
            image.save(output, format="JPEG", quality=quality, optimize=True)
            if output.tell() <= 300 * 1024:
                break
        content = output.getvalue()
        image_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{hashlib.sha256(content).hexdigest()}.jpg"
        path = image_dir / filename
        if not path.exists():
            path.write_bytes(content)
        return f"images/{filename}"
    except Exception as exc:  # noqa: BLE001 - 图片失败不能影响新闻正文
        logging.info("配图未采用：%s，%s", item.title, exc)
        return ""


def cache_article_image(session: requests.Session, item: NewsItem, image_dir: Path) -> None:
    """兼容单图调用。"""
    item.image_url = cache_one_image(session, item, image_dir, item.image_url)
    item.image_urls = [item.image_url] if item.image_url else []


def cache_article_images(session: requests.Session, item: NewsItem, image_dir: Path) -> None:
    candidates = item.image_urls or ([item.image_url] if item.image_url else [])
    cached = [cache_one_image(session, item, image_dir, url) for url in candidates[:2]]
    item.image_urls = [url for url in cached if url]
    item.image_url = item.image_urls[0] if item.image_urls else ""


def fetch_hot_words(session: requests.Session, url: str) -> list[str]:
    try:
        data = session.get(url, timeout=15, headers={"User-Agent": "daily-news-bot/1.0"}).json()
        candidates = data.get("data", data) if isinstance(data, dict) else data
        if isinstance(candidates, dict):
            candidates = candidates.get("list", candidates.get("data", []))
        result = []
        for row in candidates if isinstance(candidates, list) else []:
            word = row if isinstance(row, str) else row.get("name") or row.get("title") or row.get("word") or ""
            word = plain_text(str(word))
            if word and word not in result:
                result.append(word)
            if len(result) == 5:
                break
        return result
    except Exception as exc:  # noqa: BLE001
        logging.warning("热搜抓取失败：%s，%s", url, exc)
        return []


def apply_source_limits(sections: dict[str, list[NewsItem]]) -> dict[str, list[NewsItem]]:
    """避免一个来源占满同一板块，优先保留先被筛选出的候选。"""
    limited = {name: [] for name in SECTION_LIMITS}
    for section, items in sections.items():
        if section not in limited:
            continue
        counts: dict[str, int] = {}
        for item in items:
            if len(limited[section]) >= SECTION_LIMITS[section] or counts.get(item.source, 0) >= MAX_ITEMS_PER_SOURCE:
                continue
            limited[section].append(item)
            counts[item.source] = counts.get(item.source, 0) + 1
    return limited


def fill_section_gaps(
    selected: dict[str, list[NewsItem]], candidates_by_section: dict[str, list[NewsItem]],
) -> dict[str, list[NewsItem]]:
    """AI 第一轮少选时，以原始候选补足板块，不突破来源上限。"""
    completed = apply_source_limits(selected)
    for section, limit in SECTION_LIMITS.items():
        seen_urls = {item.url for item in completed[section]}
        source_counts: dict[str, int] = {}
        for item in completed[section]:
            source_counts[item.source] = source_counts.get(item.source, 0) + 1
        for item in candidates_by_section.get(section, []):
            if len(completed[section]) >= limit:
                break
            if item.url in seen_urls or source_counts.get(item.source, 0) >= MAX_ITEMS_PER_SOURCE:
                continue
            item.section = section
            completed[section].append(item)
            seen_urls.add(item.url)
            source_counts[item.source] = source_counts.get(item.source, 0) + 1
    return completed


def fallback_select(items: list[NewsItem]) -> dict[str, list[NewsItem]]:
    result = {name: [] for name in SECTION_LIMITS}
    for item in items:
        if item.section in result and len(result[item.section]) < SECTION_LIMITS[item.section]:
            result[item.section].append(item)
    return apply_source_limits(result)


def parse_json_object(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text.strip().removeprefix("```json").removesuffix("```").strip())
        return value if isinstance(value, dict) else None
    except (json.JSONDecodeError, AttributeError):
        return None


def call_deepseek(session: requests.Session, messages: list[dict[str, str]], api_key: str) -> dict[str, Any] | None:
    try:
        response = session.post(DEEPSEEK_URL, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json={"model": "deepseek-chat", "messages": messages, "temperature": 0.2, "response_format": {"type": "json_object"}}, timeout=90)
        response.raise_for_status()
        return parse_json_object(response.json()["choices"][0]["message"]["content"])
    except Exception as exc:  # noqa: BLE001
        logging.warning("DeepSeek 调用失败：%s", exc)
        return None


def ai_select(items: list[NewsItem], session: requests.Session, api_key: str) -> dict[str, list[NewsItem]]:
    index = {item.url: item for item in items}
    candidates_by_section = {section: [item for item in items if item.section == section] for section in SECTION_LIMITS}
    catalogue = [{"title": i.title, "source": i.source, "url": i.url, "description": i.description, "suggested_section": i.section} for i in items]
    prompt = """你是严谨的中文报纸编辑。按国内外要闻、科技、金融财经、娱乐体育筛选新闻；过滤标题党、无实质内容和传播健康焦虑的信息。只根据输入，不得编造。返回 JSON 对象，键为四个板块，值为输入中 url 组成的数组。国内外要闻最多8条，其余最多4条。"""
    result = call_deepseek(session, [{"role": "system", "content": prompt}, {"role": "user", "content": json.dumps(catalogue, ensure_ascii=False)}], api_key)
    if not result:
        return fill_section_gaps(fallback_select(items), candidates_by_section)
    selected = {name: [] for name in SECTION_LIMITS}
    for section, limit in SECTION_LIMITS.items():
        urls = result.get(section, [])
        if not isinstance(urls, list):
            continue
        for url in urls:
            item = index.get(url)
            if item and item not in selected[section] and len(selected[section]) < limit:
                item.section = section
                selected[section].append(item)
    return fill_section_gaps(selected, candidates_by_section) if any(selected.values()) else fallback_select(items)


def build_hot_words(weibo_words: list[str], xiaohongshu_words: list[str]) -> dict[str, list[str]]:
    """为不可用热搜来源保留清晰说明，避免页面无故留白。"""
    return {
        "微博热搜": weibo_words[:5] or ["今日未获取到微博热搜"],
        "小红书热搜": xiaohongshu_words[:5] or ["今日未获取到小红书热搜"],
    }


def build_hot_topics(weibo_topics: list[HotTopic], xiaohongshu_words: list[str]) -> dict[str, list[HotTopic | str]]:
    return {
        "微博热搜": weibo_topics or ["今日未获取到微博热搜"],
        "B站热搜": xiaohongshu_words[:5] or ["今日未获取到B站热搜"],
    }


def normalize_article_paragraphs(value: str) -> str:
    """保留段落边界，避免网页把整篇整理文本挤成一行。"""
    paragraphs = [re.sub(r"\s+", " ", part).strip() for part in re.split(r"\n\s*\n", value or "")]
    paragraphs = [part for part in paragraphs if part]
    return "\n\n".join(paragraphs)


def paragraphize_article(value: str) -> str:
    """AI 忘记换段时，按完整句平均分为三段，保留原有事实顺序。"""
    normalized = normalize_article_paragraphs(value)
    if len(normalized.split("\n\n")) >= 3:
        return normalized
    sentences = [part.strip() for part in re.split(r"(?<=[。！？])", plain_text(value)) if part.strip()]
    if len(sentences) < 3:
        return normalized
    paragraph_count = min(5, max(3, min(len(sentences), 3)))
    base_size, remainder = divmod(len(sentences), paragraph_count)
    paragraphs, cursor = [], 0
    for index in range(paragraph_count):
        size = base_size + (1 if index < remainder else 0)
        paragraphs.append("".join(sentences[cursor : cursor + size]))
        cursor += size
    return "\n\n".join(paragraphs)


def is_valid_summary(value: str) -> bool:
    text = plain_text(value)
    return 50 <= len(text) <= 80 and text.endswith(("。", "！", "？"))


def is_usable_summary(value: str) -> bool:
    """AI 临时波动时，完整的短句比通用占位提示更适合妈妈阅读。"""
    text = plain_text(value)
    return len(text) >= 12 and text.endswith(("。", "！", "？"))


def first_complete_sentence(value: str) -> str:
    text = plain_text(value)
    match = re.match(r".+?[。！？]", text)
    return match.group(0) if match else ""


def is_valid_article(value: str) -> bool:
    article = normalize_article_paragraphs(value)
    paragraphs = article.split("\n\n") if article else []
    return 300 <= len("".join(paragraphs)) <= 500 and 3 <= len(paragraphs) <= 5


def editorial_fields(result: dict[str, Any] | None) -> tuple[str, str, str]:
    if not result:
        return "", "", ""
    return (
        clean_editorial_title(str(result.get("title", ""))),
        plain_text(str(result.get("summary", ""))),
        paragraphize_article(str(result.get("article", ""))),
    )


def fallback_text(item: NewsItem) -> tuple[str, str]:
    """AI 连续失败时保留来源事实，不用截断文本伪装成完整摘要。"""
    raw = plain_text(item.description or item.content or item.title)
    summary = first_complete_sentence(item.description) or first_complete_sentence(item.content)
    if not is_usable_summary(summary):
        title = plain_text(item.title)
        summary = f"{title}，详情请阅读原文。" if title else "详情请阅读原文。"
    article = normalize_article_paragraphs(raw)
    return summary, article


def ai_enrich(sections: dict[str, list[NewsItem]], session: requests.Session, api_key: str) -> None:
    instruction = """你是严谨的中文报纸编辑。仅依据输入事实输出 JSON 对象，包含 title、summary、article。
summary 必须是50至80个汉字左右的独立完整事实句，说明谁、发生了什么以及必要影响，以句号、问号或感叹号结束；绝不能复制原文开头、使用省略号或写成不完整短语。
article 必须为300至500个汉字、3至5个自然段；各段之间用两个换行符（\\n\\n）分隔。只保留可核实事实，删除广告和无关内容，不编造，不使用网络用语。"""
    repair_summary_instruction = "只输出 JSON 对象中的 summary 字段。请依据输入事实重写为50至80字的独立完整中文摘要，须说明主体和事件，并以句号、问号或感叹号结束；不写省略号，不补充输入没有的事实。"
    for items in sections.values():
        for item in items:
            payload = {"title": item.title, "source": item.source, "description": item.description, "content": item.content or item.description}
            messages = [{"role": "system", "content": instruction}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]
            title, summary, article = editorial_fields(call_deepseek(session, messages, api_key))
            if not is_valid_summary(summary):
                repair_messages = [
                    {"role": "system", "content": repair_summary_instruction},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ]
                repaired_title, repaired_summary, _ = editorial_fields(call_deepseek(session, repair_messages, api_key))
                if repaired_title:
                    title = repaired_title
                if is_valid_summary(repaired_summary):
                    summary = repaired_summary
            if title:
                item.title = title
            fallback_summary, fallback_article = fallback_text(item)
            item.summary = summary if is_usable_summary(summary) else fallback_summary
            item.article = article or fallback_article
            if is_valid_summary(summary):
                if is_valid_article(article):
                    logging.info("AI 整理成功：%s", item.title)
                else:
                    logging.info("AI 整理完成：%s，正文未达建议长度但已保留并分段", item.title)
            elif is_usable_summary(summary):
                logging.info("AI 摘要采用完整短句：%s", item.title)
            else:
                logging.warning("AI 摘要降级：%s，改用来源完整句", item.title)


def parse_geo_briefs(result: dict[str, Any] | None) -> list[GeoBrief]:
    """只接收恰好三条、字段完整的 AI 输出，避免把不完整内容放进日报。"""
    rows = result.get("briefs", []) if isinstance(result, dict) else []
    if not isinstance(rows, list) or len(rows) != 3:
        return []
    briefs = []
    for row in rows:
        if not isinstance(row, dict):
            return []
        fields = [plain_text(str(row.get(key, ""))) for key in ("title", "event", "impact", "watch")]
        if not all(fields):
            return []
        briefs.append(GeoBrief(*fields))
    return briefs


def fallback_geo_briefs(sections: dict[str, list[NewsItem]]) -> list[GeoBrief]:
    """AI 临时不可用时仍固定三条，但只转述已入选报道，不补充推断。"""
    candidates = sections.get("国内外要闻", []) + sections.get("金融财经", [])
    if not candidates:
        candidates = [item for items in sections.values() for item in items]
    briefs = []
    for item in candidates[:3]:
        event = plain_text(item.summary or item.description or item.title)
        briefs.append(GeoBrief(item.title, event, "影响需结合后续官方信息和市场反应判断。", "关注报道后续进展。"))
    while len(briefs) < 3:
        briefs.append(GeoBrief("今日观察", "今日可核实的相关报道有限。", "暂不作超出报道的信息推断。", "关注后续权威发布。"))
    return briefs


def ai_geopolitical_brief(sections: dict[str, list[NewsItem]], session: requests.Session, api_key: str) -> list[GeoBrief]:
    """根据当天入选新闻提炼固定三条地缘政治简报。"""
    candidates = sections.get("国内外要闻", []) + sections.get("金融财经", [])
    payload = [
        {"title": item.title, "source": item.source, "summary": item.summary, "article": item.article or item.description}
        for item in candidates[:12]
    ]
    instruction = """你是严谨的中文国际新闻编辑。仅依据输入新闻，输出 JSON 对象：
{"briefs":[{"title":"不超过22字的主题","event":"发生了什么","impact":"对地区关系、贸易、能源或市场的已知影响","watch":"下一步关注点"}]}。
必须恰好三条。优先外交、冲突、关税贸易、能源与国际政策；如材料不足，可用“信息有限、持续关注”说明，绝不补充输入中没有的事实。语言平实、适合中年读者。"""
    try:
        result = call_deepseek(session, [{"role": "system", "content": instruction}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}], api_key)
        briefs = parse_geo_briefs(result)
        if briefs:
            logging.info("地缘政治简报生成成功，共 3 条")
            return briefs
    except Exception as exc:  # noqa: BLE001
        logging.warning("地缘政治简报生成失败：%s", exc)
    logging.warning("地缘政治简报降级为原文事实提示")
    return fallback_geo_briefs(sections)


def render_hot_topic(topic: HotTopic | str) -> str:
    if isinstance(topic, HotTopic):
        return f'<li><a href="{html.escape(topic.url, quote=True)}" target="_blank" rel="noopener">{html.escape(topic.title)}</a></li>'
    return f"<li>{html.escape(topic)}</li>"


def hot_topic_note(name: str) -> str:
    return "点击标题查看微博实时讨论" if name == "微博热搜" else "点击标题查看B站实时讨论"


def render_html(date_text: str, sections: dict[str, list[NewsItem]], hot_words: dict[str, list[HotTopic | str]], page_url: str, geo_briefs: list[GeoBrief] | None = None) -> str:
    blocks, number, seen_images = [], 0, set()
    for section in SECTION_LIMITS:
        cards = []
        for item in sections.get(section, []):
            number += 1
            images = []
            for image_url in (item.image_urls or [item.image_url]):
                if is_displayable_image(image_url, seen_images):
                    seen_images.add(image_url)
                    images.append(f'<img class="news-image" src="{html.escape(image_url, quote=True)}" alt="新闻正文配图" loading="lazy">')
            paragraph_parts = [f"<p>{html.escape(part)}</p>" for part in normalize_article_paragraphs(item.article).split("\n\n") if part.strip()]
            cover = images[0] if images else ""
            gallery = f'<div class="article-gallery">{"".join(images[1:])}</div>' if len(images) > 1 else ""
            cards.append(f'<article id="news-{number}"><h3>{html.escape(item.title)}</h3><p class="meta">来源：{html.escape(item.source)}</p><p>{html.escape(item.summary)}</p>{cover}<details><summary>点击展开新闻整理</summary>{"".join(paragraph_parts)}{gallery}<p><a href="{html.escape(item.url, quote=True)}" target="_blank" rel="noopener">阅读原文</a></p></details></article>')
        blocks.append(f"<section><h2>{section}</h2>{''.join(cards) or '<p>今日暂未获取到合适新闻。</p>'}</section>")
    hot = "".join(
        f"<h3>{html.escape(name)}</h3><ol class=\"hot-list\">"
        f"{''.join(render_hot_topic(topic) for topic in words) or '<li>暂无数据</li>'}</ol><p class=\"hot-note\">{hot_topic_note(name)}</p>"
        for name, words in hot_words.items()
    )
    geo = "".join(
        f'<article class="geo-item"><h3>{index}. {html.escape(brief.title)}</h3>'
        f'<ul class="geo-points"><li><b>事件概述：</b>{html.escape(brief.event)}</li>'
        f'<li><b>影响分析：</b>{html.escape(brief.impact)}</li>'
        f'<li><b>后续关注：</b>{html.escape(brief.watch)}</li></ul></article>'
        for index, brief in enumerate(geo_briefs or [], 1)
    )
    geo_section = f'<section id="geopolitics"><h2>地缘政治简报</h2>{geo}</section>' if geo else ""
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>今日新闻杂志 {date_text}</title><style>body{{margin:0;background:#f6f5f1;color:#272727;font:17px/1.75 system-ui,"Microsoft YaHei",sans-serif}}main{{max-width:760px;margin:auto;padding:18px}}header,section,footer{{background:#fff;border-radius:12px;padding:18px;margin:14px 0;box-shadow:0 1px 4px #ddd}}h1{{font-size:27px;margin:0}}h2{{font-size:22px;border-left:5px solid #a6412e;padding-left:10px}}h3{{font-size:19px;margin-bottom:4px}}article{{border-top:1px solid #e8e4dc;padding:12px 0}}.news-image{{width:100%;max-height:280px;object-fit:cover;border-radius:8px;margin:8px 0;object-fit:cover}}.article-gallery{{margin-top:14px}}.article-gallery .news-image{{display:block}}.meta{{color:#666;font-size:15px}}summary{{color:#8b3828;font-weight:600;cursor:pointer}}a{{color:#8b3828}}details p{{white-space:pre-wrap}}.hot-list{{margin:0;padding-left:1.6em}}.hot-list li{{padding:4px 0}}.hot-note{{font-size:15px;color:#666;margin:4px 0 16px}}.geo-item{{padding:20px 0}}.geo-item h3{{font-size:21px;margin:0 0 12px}}.geo-points{{margin:0;padding-left:1.35em}}.geo-points li{{padding:4px 0 4px 8px}}.geo-points b{{font-weight:750}}footer{{font-size:15px;color:#555}}</style><main><header><h1>今日新闻杂志</h1><p>{html.escape(date_text)}</p></header>{geo_section}{''.join(blocks)}<section><h2>今日热搜</h2>{hot}</section><footer>新闻内容由公开 RSS 与原文整理而成，供阅读参考；请以原始报道为准。网页版入口：{html.escape(page_url)}</footer></main></html>'''


def split_markdown(text: str, limit: int = 4096) -> list[str]:
    chunks, current = [], ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if current and len(current) + len(line) > limit:
            chunks.append(current)
            current = ""
        current += line
    if current:
        chunks.append(current)
    return chunks or [""]


def build_wechat_messages(date_text: str, sections: dict[str, list[NewsItem]], hot_words: dict[str, list[HotTopic | str]], page_url: str, geo_briefs: list[GeoBrief] | None = None) -> list[str]:
    messages, number = [], 0
    if geo_briefs:
        geo_lines = [f"## 地缘政治简报｜{date_text}"]
        for index, brief in enumerate(geo_briefs, 1):
            geo_lines.extend([f"**{index}. {brief.title}**", f"• **事件概述：**{brief.event}", f"• **影响分析：**{brief.impact}", f"• **后续关注：**{brief.watch}", ""])
        geo_lines.append(f"[打开网页版简报]({page_url}/news/{date_text}.html#geopolitics)")
        messages.extend(split_markdown("\n".join(geo_lines)))
    for section in SECTION_LIMITS:
        lines = [f"## {section}｜{date_text}"]
        for item in sections.get(section, []):
            number += 1
            lines.extend([f"**{item.title}**", item.summary, f"[阅读全文]({page_url}/news/{date_text}.html#news-{number})", ""])
        messages.extend(split_markdown("\n".join(lines)))
    hot_lines = [f"## 今日热搜｜{date_text}"]
    for name, words in hot_words.items():
        hot_lines.append(f"**{name}**")
        for index, topic in enumerate(words, start=1):
            if isinstance(topic, HotTopic):
                hot_lines.append(f"{index}. [{topic.title}]({topic.url})")
            else:
                hot_lines.append(f"{index}. {topic}")
        hot_lines.append(hot_topic_note(name))
    hot = "\n".join(hot_lines)
    messages.extend(split_markdown(hot))
    messages.extend(split_markdown(f"## 来源与网页版\n新闻来自新华社、BBC中文、36氪、新浪财经和新浪娱乐等公开 RSS；内容经整理，原文链接可核对。\n[打开今日新闻杂志]({page_url}/news/{date_text}.html)"))
    return messages


def send_wechat_messages(session: requests.Session, webhook_url: str, messages: list[str]) -> None:
    for message in messages:
        try:
            response = session.post(webhook_url, json={"msgtype": "markdown", "markdown": {"content": message}}, timeout=20)
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            logging.warning("企业微信推送失败：%s", exc)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = load_config()
    if not config:
        return
    session = requests.Session()
    today = beijing_today()
    rss_items = [extract_article(item) for item in fetch_rss_sources(session)]
    finance_items = fetch_newsnow_platform(session, "wallstreetcn-hot", "华尔街见闻", "wallstreetcn.com", "金融财经")
    finance_items += fetch_newsnow_platform(session, "cls-hot", "财联社", "cls.cn", "金融财经")
    items = rss_items + finance_items
    sections = ai_select(items, session, config.deepseek_api_key)
    ai_enrich(sections, session, config.deepseek_api_key)
    geo_briefs = ai_geopolitical_brief(sections, session, config.deepseek_api_key)
    hot_words = build_hot_topics(
        fetch_newsnow_hot_topics(session, "weibo"),
        fetch_newsnow_hot_topics(session, "bilibili-hot-search", "bilibili.com", "点击查看B站实时讨论"),
    )
    output = Path(__file__).resolve().parent / "news"
    output.mkdir(exist_ok=True)
    image_dir = output / "images"
    for items in sections.values():
        for item in items:
            cache_article_images(session, item, image_dir)
    (output / f"{today}.html").write_text(render_html(today, sections, hot_words, config.page_url, geo_briefs), encoding="utf-8")
    send_wechat_messages(session, config.webhook_url, build_wechat_messages(today, sections, hot_words, config.page_url, geo_briefs))
    logging.info("日报完成：%s，入选 %d 条", today, sum(len(value) for value in sections.values()))


if __name__ == "__main__":
    main()
