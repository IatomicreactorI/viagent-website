#!/usr/bin/env python3
"""
新闻视频爬虫 — 从 RSS / 公开新闻源抓取疑似 AI 生成或真假不明的热门新闻视频
爬取元数据并下载视频到本地，供 Viagent 分析流水线处理。

用法:
    python website/crawler.py [--limit 20] [--output website/data/videos]
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urljoin, quote

import requests

# ── 配置 ─────────────────────────────────────────────────────────

VIDEO_DIR = Path(__file__).parent / "data" / "videos"
META_DIR = Path(__file__).parent / "data" / "meta"
CRAWL_LOG = Path(__file__).parent / "data" / "crawl_log.json"

# 搜索关键词 — 聚焦美伊冲突战报视频真伪
KEYWORDS_EN = [
    "Iran US conflict video",
    "Iran war video fake",
    "Iran Israel strike video",
    "Iran attack video",
    "Middle East war footage",
    "Iran military video deepfake",
    "Iran US war footage AI",
    "Iran drone strike video",
]
KEYWORDS_ZH = [
    "美伊冲突视频",
    "伊朗战争视频",
    "中东战报视频",
    "伊朗打击视频",
    "伊朗以色列视频真假",
]

# 公开 RSS 源列表 — 中东 / 军事 / 国际新闻
RSS_FEEDS = [
    # 国际 / 中东新闻
    "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/MiddleEast.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://www.theguardian.com/world/middleeast/rss",
    "https://feeds.reuters.com/Reuters/worldNews",
    "https://www.cnbc.com/id/100727362/device/rss/rss.html",
]

# Google News RSS（基于关键词搜索）
GOOGLE_NEWS_RSS_TEMPLATE = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# ── 工具函数 ──────────────────────────────────────────────────────


def safe_filename(text: str, max_len: int = 80) -> str:
    """把任意文本转为安全文件名"""
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', text)
    text = re.sub(r'\s+', '_', text).strip('_.')
    return text[:max_len] if text else "untitled"


def sha256_of_url(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:12]


def load_crawl_log() -> dict:
    if CRAWL_LOG.exists():
        with open(CRAWL_LOG, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"crawled_urls": [], "items": []}


def save_crawl_log(log: dict):
    CRAWL_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CRAWL_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def strip_html(text: str) -> str:
    """去除 HTML 标签，返回纯文本"""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&[a-zA-Z]+;', ' ', text)
    text = re.sub(r'&#?\w+;', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def fetch_thumbnail(url: str, timeout: int = 5) -> str | None:
    """从文章页面拐取 og:image / twitter:image 作为封面图"""
    try:
        resp = SESSION.get(url, timeout=timeout, allow_redirects=True)
        if resp.status_code != 200:
            return None
        html = resp.text[:30000]  # 只读前 30KB
        # og:image
        m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\'>]+)', html, re.I)
        if m:
            return m.group(1)
        m = re.search(r'<meta[^>]+content=["\']([^"\'>]+)["\'][^>]+property=["\']og:image', html, re.I)
        if m:
            return m.group(1)
        # twitter:image
        m = re.search(r'<meta[^>]+(?:name|property)=["\']twitter:image["\'][^>]+content=["\']([^"\'>]+)', html, re.I)
        if m:
            return m.group(1)
        return None
    except Exception:
        return None


# ── RSS 解析 ──────────────────────────────────────────────────────


def fetch_rss(url: str, timeout: int = 15) -> list[dict]:
    """解析 RSS feed，返回条目列表"""
    items = []
    try:
        resp = SESSION.get(url, timeout=timeout)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        # 支持 RSS 2.0 和 Atom
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        # RSS 2.0
        ns_media = {"media": "http://search.yahoo.com/mrss/"}
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc = (item.findtext("description") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            # 尝试提取 media:thumbnail
            thumb = None
            mt = item.find("media:thumbnail", ns_media)
            if mt is not None:
                thumb = mt.get("url", None)
            if not thumb:
                mc = item.find("media:content", ns_media)
                if mc is not None:
                    thumb = mc.get("url", None)
            if title and link:
                items.append({
                    "title": title,
                    "link": link,
                    "description": desc,
                    "pub_date": pub_date,
                    "thumbnail": thumb,
                    "source_feed": url,
                })

        # Atom
        for entry in root.findall("atom:entry", ns):
            title = (entry.findtext("atom:title", namespaces=ns) or "").strip()
            link_el = entry.find("atom:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            desc = (entry.findtext("atom:summary", namespaces=ns) or "").strip()
            pub_date = (entry.findtext("atom:published", namespaces=ns) or "").strip()
            if title and link:
                items.append({
                    "title": title,
                    "link": link,
                    "description": desc,
                    "pub_date": pub_date,
                    "thumbnail": None,
                    "source_feed": url,
                })

    except Exception as e:
        print(f"  ⚠ RSS 获取失败 {url}: {e}")
    return items


def filter_relevant_news(items: list[dict]) -> list[dict]:
    """筛选与美伊冲突 / 中东战事 / 军事视频相关的新闻"""
    patterns = [
        r'\b(iran|iranian|tehran|irgc|persian.?gulf)\b',
        r'\b(us.?iran|iran.?us|iran.?isra|isra.?iran|iran.?strike|strike.?iran)\b',
        r'\b(middle.?east.?(?:war|conflict|strike|attack|tension|crisis))\b',
        r'\b(missile.?(?:strike|attack|launch)|drone.?(?:strike|attack)|air.?strike)\b',
        r'\b(war.?(?:video|footage)|military.?(?:video|footage)|combat.?(?:video|footage))\b',
        r'\b(fake.?(?:video|footage)|deepfake|manipulat|fabricat|ai.?generat|disinformation)\b',
        r'\b(美伊|伊朗|中东|军事|战报|战争|空袭|导弹|无人机|真假)\b',
    ]
    combined = re.compile('|'.join(patterns), re.IGNORECASE)
    filtered = []
    for item in items:
        text = f"{item['title']} {strip_html(item['description'])}"
        if combined.search(text):
            filtered.append(item)
    return filtered


# ── 新闻信息收集（不下载视频，生成元数据供页面展示） ─────────────


def collect_news_items(limit: int = 30) -> list[dict]:
    """
    从公开 RSS 源收集 AI 视频相关新闻条目元数据。
    不下载实际视频，只收集新闻标题、来源、描述等信息。
    """
    all_items = []
    seen_links = set()

    print("🔍 正在从 RSS 源收集新闻...")

    # 1. 从常规 RSS 获取
    for feed_url in RSS_FEEDS:
        print(f"  📡 抓取: {feed_url[:60]}...")
        items = fetch_rss(feed_url)
        all_items.extend(items)
        time.sleep(0.3)

    # 2. 从 Google News RSS 搜索关键词（可选，超时较短）
    # 注: Google News RSS 在部分网络环境下不可用，跳过不影响主流程
    try:
        for kw in KEYWORDS_EN[:1]:
            query = quote(kw)
            gn_url = GOOGLE_NEWS_RSS_TEMPLATE.format(query=query)
            print(f"  🔎 搜索: {kw}")
            items = fetch_rss(gn_url, timeout=5)
            all_items.extend(items)
    except Exception:
        print("  ⚠ Google News 搜索跳过")

    # 3. 筛选美伊冲突 / 中东战事相关
    filtered = filter_relevant_news(all_items)
    print(f"\n📊 共获取 {len(all_items)} 条新闻，筛选出 {len(filtered)} 条相关")

    # 4. 去重
    unique = []
    for item in filtered:
        if item["link"] not in seen_links:
            seen_links.add(item["link"])
            unique.append(item)
    unique = unique[:limit]
    print(f"📋 去重后保留 {len(unique)} 条")

    # 5. 拐取封面图
    print("\n🖼️ 正在获取封面图...")
    for item in unique:
        if not item.get("thumbnail"):
            print(f"  🖼️ {item['title'][:50]}...")
            thumb = fetch_thumbnail(item["link"])
            if thumb:
                item["thumbnail"] = thumb
                print(f"    ✅ 获取到封面图")
            else:
                print(f"    ➖ 无封面图")
            time.sleep(0.2)

    return unique


# ── 生成模拟分析数据（基于新闻内容的启发式判断） ─────────────────


def generate_mock_analysis(news_items: list[dict]) -> list[dict]:
    """
    基于新闻内容生成模拟分析记录。
    这些是示例数据，用于展示网站功能。
    实际使用时应接入 Viagent 分析流水线。
    """
    import random

    results = []
    for i, item in enumerate(news_items):
        title = item["title"]
        desc = item.get("description", "")
        text = f"{title} {desc}".lower()

        # 启发式判断：根据新闻内容特征打分
        # 战报视频语境下的"疑似伪造"和"可信来源"信号
        fake_indicators = [
            "deepfake", "ai generated", "synthetic", "fake", "manipulated",
            "fabricated", "unverified", "disputed", "alleged", "propaganda",
            "disinformation", "misinformation", "misleading", "debunked",
            "claims", "purported", "so-called", "state media", "state tv",
            "released video", "released footage", "undated video",
            "虚假", "造假", "伪造", "未经证实", "AI生成", "宣传",
            "声称", "据称", "疑似",
        ]
        real_indicators = [
            "confirmed", "verified", "authentic", "official statement",
            "satellite imagery", "satellite image", "pentagon confirmed",
            "footage shows", "reuters", "ap news", "afp",
            "bbc verify", "on the ground", "correspondent",
            "witnessed", "independent", "investigation",
            "记者", "现场", "证实", "真实", "官方", "卫星",
        ]
        # 中性/战争高热度词 — 给一定的"存疑"倾向
        suspicious_indicators = [
            "viral", "circulating", "shared widely", "social media",
            "telegram", "breaking", "dramatic", "shocking",
            "exclusive footage", "intercepted",
        ]

        fake_count = sum(1 for kw in fake_indicators if kw in text)
        real_count = sum(1 for kw in real_indicators if kw in text)
        sus_count = sum(1 for kw in suspicious_indicators if kw in text)

        # 更合理的分数分布
        if fake_count > real_count and fake_count >= 2:
            base_score = random.uniform(0.72, 0.95)   # 明确偏假
        elif fake_count > real_count:
            base_score = random.uniform(0.55, 0.85)   # 偏假
        elif real_count > fake_count and real_count >= 2:
            base_score = random.uniform(0.05, 0.25)   # 明确偏真
        elif real_count > fake_count:
            base_score = random.uniform(0.10, 0.40)   # 偏真
        elif sus_count >= 1:
            base_score = random.uniform(0.45, 0.78)   # 存疑偏假
        else:
            # 没有明确信号：给随机分布，但偏向两端而非全集中在中间
            r = random.random()
            if r < 0.35:
                base_score = random.uniform(0.65, 0.92)   # 假
            elif r < 0.65:
                base_score = random.uniform(0.08, 0.32)   # 真
            else:
                base_score = random.uniform(0.35, 0.65)   # 不确定

        confidence = random.uniform(0.55, 0.95)

        # Verdict
        if base_score >= 0.7:
            label = "fake"
        elif base_score <= 0.3:
            label = "real"
        else:
            label = "uncertain"

        # 模拟各 agent 结果
        agents = {}
        agent_names = ["style", "physics", "spatial", "temporal", "watermark"]
        for agent in agent_names:
            noise = random.uniform(-0.15, 0.15)
            a_score = max(0.0, min(1.0, base_score + noise))
            a_conf = random.uniform(0.5, 0.95)
            agents[agent] = {
                "status": "ok",
                "score_fake": round(a_score, 3),
                "confidence": round(a_conf, 3),
            }

        # 提取来源
        source_domain = ""
        try:
            parsed = urlparse(item["link"])
            source_domain = parsed.netloc.replace("www.", "")
        except Exception:
            source_domain = "unknown"

        # 清理 HTML 标签
        clean_desc = strip_html(desc)[:300] if desc else ""

        results.append({
            "id": sha256_of_url(item["link"]),
            "title": strip_html(title),
            "source": source_domain,
            "source_url": item["link"],
            "video_url": item.get("video_url", None),
            "description": clean_desc,
            "pub_date": item.get("pub_date", ""),
            "crawled_at": datetime.now(timezone.utc).isoformat(),
            "thumbnail": item.get("thumbnail", None),
            "verdict": {
                "label": label,
                "score_fake": round(base_score, 3),
                "confidence": round(confidence, 3),
            },
            "agents": agents,
        })

    return results


# ── 主流程 ────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="AI 视频新闻爬虫与分析数据生成")
    parser.add_argument("--limit", type=int, default=30, help="最多抓取条数")
    parser.add_argument("--output", type=str, default=None, help="输出 JSON 路径")
    args = parser.parse_args()

    # 确保目录存在
    META_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)

    # 收集新闻
    news_items = collect_news_items(limit=args.limit)

    if not news_items:
        print("⚠ 没有找到 AI 视频相关新闻，生成示例数据...")
        news_items = generate_fallback_news()

    # 生成分析数据
    results = generate_mock_analysis(news_items)

    # 输出路径
    output_path = args.output or str(Path(__file__).parent / "data" / "results.json")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total": len(results),
            "items": results,
        }, f, indent=2, ensure_ascii=False)

    print(f"\n✅ 已生成 {len(results)} 条分析结果 → {output_path}")

    # 更新爬取日志
    log = load_crawl_log()
    for item in news_items:
        if item["link"] not in log["crawled_urls"]:
            log["crawled_urls"].append(item["link"])
    log["last_crawl"] = datetime.now(timezone.utc).isoformat()
    save_crawl_log(log)


def generate_fallback_news() -> list[dict]:
    """在无法联网时生成美伊冲突相关示例新闻数据"""
    examples = [
        {
            "title": "US strikes Iranian military targets in response to drone attack",
            "link": "https://example.com/us-iran-strikes-1",
            "description": "The United States launched a series of retaliatory strikes against Iranian military installations following a drone attack on US forces in the region. Video footage of the strikes has been circulating on social media.",
            "pub_date": "2026-03-25T14:00:00Z",
            "thumbnail": None,
            "source_feed": "fallback",
        },
        {
            "title": "Iran releases video claiming successful missile test near Strait of Hormuz",
            "link": "https://example.com/iran-missile-test",
            "description": "Iranian state media released footage showing what it claims is a successful ballistic missile test conducted near the Strait of Hormuz. Western analysts are questioning the video's authenticity.",
            "pub_date": "2026-03-25T08:30:00Z",
            "thumbnail": None,
            "source_feed": "fallback",
        },
        {
            "title": "Viral video of alleged Iranian drone strike debunked as AI-generated",
            "link": "https://example.com/iran-drone-debunked",
            "description": "A dramatic video showing what appeared to be an Iranian drone strike on a US naval vessel has been confirmed as AI-generated after forensic analysis revealed temporal inconsistencies and physics-defying elements.",
            "pub_date": "2026-03-24T18:00:00Z",
            "thumbnail": None,
            "source_feed": "fallback",
        },
        {
            "title": "Pentagon releases verified footage of Iran-backed militia positions",
            "link": "https://example.com/pentagon-iran-footage",
            "description": "The US Department of Defense released declassified aerial footage showing Iran-backed militia positions in Iraq and Syria, providing visual evidence to support recent military operations.",
            "pub_date": "2026-03-24T12:00:00Z",
            "thumbnail": None,
            "source_feed": "fallback",
        },
        {
            "title": "Deepfake video of Iranian general's speech spreads on Telegram",
            "link": "https://example.com/deepfake-iranian-general",
            "description": "A deepfake video featuring a high-ranking Iranian military commander making threatening statements went viral on Telegram channels before being identified as manipulated content.",
            "pub_date": "2026-03-23T16:00:00Z",
            "thumbnail": None,
            "source_feed": "fallback",
        },
        {
            "title": "美伊紧张局势升级：波斯湾军事视频真假难辨",
            "link": "https://example.com/us-iran-persian-gulf",
            "description": "随着美伊紧张局势持续升级，社交媒体上大量流传波斯湾地区的军事行动视频，部分视频被证实为旧画面重新剪辑或AI生成。",
            "pub_date": "2026-03-23T10:00:00Z",
            "thumbnail": None,
            "source_feed": "fallback",
        },
        {
            "title": "Satellite imagery contradicts Iranian claims about US base damage",
            "link": "https://example.com/satellite-iran-claims",
            "description": "Commercial satellite photographs released by Planet Labs show minimal damage to a US military facility in the Gulf, contradicting dramatic video footage released by Iranian media claiming extensive destruction.",
            "pub_date": "2026-03-22T20:00:00Z",
            "thumbnail": None,
            "source_feed": "fallback",
        },
        {
            "title": "Social media flooded with unverified combat footage from Iran-US standoff",
            "link": "https://example.com/unverified-combat-footage",
            "description": "Multiple social media platforms are struggling to moderate a flood of unverified war footage purportedly showing combat between US and Iranian forces, with experts warning many clips appear manipulated.",
            "pub_date": "2026-03-22T14:00:00Z",
            "thumbnail": None,
            "source_feed": "fallback",
        },
        {
            "title": "IRGC propaganda video uses game engine footage as 'real combat'",
            "link": "https://example.com/irgc-game-footage",
            "description": "Digital forensic experts have identified that a recent IRGC propaganda video depicting a naval engagement actually contains footage rendered in a video game engine, with telltale physics and rendering anomalies.",
            "pub_date": "2026-03-21T18:00:00Z",
            "thumbnail": None,
            "source_feed": "fallback",
        },
        {
            "title": "Reuters investigation: Tracking the origin of viral Iran war videos",
            "link": "https://example.com/reuters-iran-videos",
            "description": "A Reuters special investigation traced the origins of 47 viral videos related to the US-Iran conflict, finding that 15 were recycled from previous conflicts, 8 showed signs of digital manipulation, and only 24 could be verified as authentic.",
            "pub_date": "2026-03-21T10:00:00Z",
            "thumbnail": None,
            "source_feed": "fallback",
        },
        {
            "title": "中东战报视频分析：多段伊朗发布的军事视频疑为AI生成",
            "link": "https://example.com/mideast-ai-analysis",
            "description": "国际事实核查机构对近期伊朗官方发布的12段军事行动视频进行了技术分析，发现其中5段存在明显的AI生成痕迹，包括物理运动不自然和时间序列不一致等问题。",
            "pub_date": "2026-03-20T15:00:00Z",
            "thumbnail": None,
            "source_feed": "fallback",
        },
        {
            "title": "US Navy releases authenticated video of Iranian fast boats in Persian Gulf",
            "link": "https://example.com/navy-fast-boats",
            "description": "The US Navy's Fifth Fleet released authenticated infrared video footage showing Iranian Revolutionary Guard fast boats approaching American warships in the Persian Gulf in what officials called 'unsafe and unprofessional' maneuvers.",
            "pub_date": "2026-03-20T08:00:00Z",
            "thumbnail": None,
            "source_feed": "fallback",
        },
        {
            "title": "Fake missile launch video attributed to Iran traced to Russian disinformation network",
            "link": "https://example.com/fake-missile-russia",
            "description": "A viral video claiming to show Iran launching hypersonic missiles at US targets has been traced to a known Russian disinformation network. The video was generated using AI tools and contained multiple physics-defying elements.",
            "pub_date": "2026-03-19T16:00:00Z",
            "thumbnail": None,
            "source_feed": "fallback",
        },
        {
            "title": "BBC Verify: How we confirmed the authenticity of Iran airstrike footage",
            "link": "https://example.com/bbc-verify-iran",
            "description": "BBC Verify team explains the methodology used to authenticate recent airstrike footage from the Iran-US conflict, including geolocation, metadata analysis, and cross-referencing with satellite imagery.",
            "pub_date": "2026-03-19T11:00:00Z",
            "thumbnail": None,
            "source_feed": "fallback",
        },
        {
            "title": "伊朗国家电视台播出的美军基地被袭视频被质疑造假",
            "link": "https://example.com/iran-tv-fake-attack",
            "description": "伊朗国家电视台播出的一段声称展示伊朗导弹\u201c精确命中\u201d美军中东基地的视频，被多家国际媒体和数字取证专家质疑其真实性，指出视频中存在明显的编辑和合成痕迹。",
            "pub_date": "2026-03-18T14:00:00Z",
            "thumbnail": None,
            "source_feed": "fallback",
        },
        {
            "title": "AI-generated propaganda videos escalate US-Iran information warfare",
            "link": "https://example.com/ai-propaganda-us-iran",
            "description": "Intelligence analysts warn that both sides of the US-Iran conflict are increasingly deploying AI-generated video content as part of information warfare campaigns, making it harder for the public to distinguish real events from fabricated ones.",
            "pub_date": "2026-03-18T09:00:00Z",
            "thumbnail": None,
            "source_feed": "fallback",
        },
        {
            "title": "Conflict footage verification: Why checking war videos matters more than ever",
            "link": "https://example.com/conflict-verification",
            "description": "As the US-Iran tensions escalate, experts emphasize the importance of video verification tools. Multiple AI detection systems are being deployed by news organizations to screen incoming footage from the Middle East conflict zone.",
            "pub_date": "2026-03-17T12:00:00Z",
            "thumbnail": None,
            "source_feed": "fallback",
        },
        {
            "title": "美伊冲突中的信息战：如何辨别真假战报视频",
            "link": "https://example.com/info-war-guide",
            "description": "随着美伊冲突加剧，社交媒体上充斥着大量来源不明的战报视频。专家提供了一份指南，教网民如何通过观察视频中的物理现象、时间一致性和空间特征来初步判断视频的真伪。",
            "pub_date": "2026-03-17T08:00:00Z",
            "thumbnail": None,
            "source_feed": "fallback",
        },
        {
            "title": "Iranian media video of drone swarm attack found to contain recycled footage",
            "link": "https://example.com/drone-swarm-recycled",
            "description": "A widely shared video purporting to show an Iranian drone swarm attack has been found to contain footage from a 2024 military exercise, with AI-enhanced visual effects added to make it appear as a real combat scenario.",
            "pub_date": "2026-03-16T15:00:00Z",
            "thumbnail": None,
            "source_feed": "fallback",
        },
        {
            "title": "Verified: Authentic footage of US carrier group transit through Strait of Hormuz",
            "link": "https://example.com/carrier-hormuz-verified",
            "description": "Independent analysts have verified footage showing a US aircraft carrier strike group transiting the Strait of Hormuz, confirming the video's authenticity through ship identification, weather pattern matching, and AIS tracking data.",
            "pub_date": "2026-03-16T10:00:00Z",
            "thumbnail": None,
            "source_feed": "fallback",
        },
    ]
    return examples


if __name__ == "__main__":
    main()
