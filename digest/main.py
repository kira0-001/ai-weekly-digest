import os, re, html, ssl, smtplib, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dateutil import parser
import pytz
import feedparser
from bs4 import BeautifulSoup
from templates import html_email, subject_line

# -----------------------
# CONFIG
# -----------------------
TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")
NOW = datetime.datetime.now(pytz.timezone(TIMEZONE))
DAYS_BACK = 7
CUTOFF = NOW - datetime.timedelta(days=DAYS_BACK)

# Curated sources (reliable, low-friction RSS)
SOURCES = {
    "🚀 **Big Launches**": [
        ("OpenAI Blog", "https://openai.com/blog/rss.xml"),
        ("Google AI Blog", "https://ai.googleblog.com/feeds/posts/default?alt=rss"),
        ("DeepMind", "https://deepmind.google/discover/rss/"),
        ("Meta AI", "https://ai.meta.com/blog/rss/"),
        ("Anthropic", "https://www.anthropic.com/news/rss.xml"),
        ("Hugging Face Blog", "https://huggingface.co/blog/feed.xml"),
    ],
    "📄 **Viral Papers / Research**": [
        ("arXiv cs.AI", "http://export.arxiv.org/rss/cs.AI"),
        ("arXiv cs.LG", "http://export.arxiv.org/rss/cs.LG"),
        ("Papers with Code — Trending", "https://paperswithcode.com/trending?mod=rss"),
    ],
    "🧪 **Cool Experiments & Demos**": [
        ("Hugging Face Spaces Daily", "https://huggingface.co/spaces?sort=trending&layout=card&category=ml&format=rss"),
        ("Google AI Studio / Experiments", "https://experiments.withgoogle.com/feed.atom"),
    ],
    "🛠️ **New AI Tools**": [
        ("Hugging Face Releases", "https://huggingface.co/releases/feed.xml"),
        ("GitHub Blog AI", "https://github.blog/changelog/label/ai/feed/"),
        ("PyPI Trending (unofficial)", "https://hugovk.github.io/top-pypi-packages/top-pypi-packages-30-days.rss"),
    ],
}

MAX_ITEMS_PER_SECTION = 5  # keep concise

# -----------------------
# HELPERS
# -----------------------
def clean_text(s: str) -> str:
    if not s:
        return ""
    s = html.unescape(s)
    s = BeautifulSoup(s, "lxml").get_text(" ", strip=True)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def entry_datetime(e):
    for key in ("published", "updated", "created"):
        if key in e:
            try:
                return parser.parse(getattr(e, key) if hasattr(e, key) else e[key])
            except Exception:
                pass
    # Fallback: epoch now
    return datetime.datetime.now(datetime.timezone.utc)

def summarize(text, max_words=40):
    text = clean_text(text)
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "…"

def within_window(dt):
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt >= CUTOFF.astimezone(dt.tzinfo)

def fetch_section_items(name, url):
    try:
        feed = feedparser.parse(url)
    except Exception:
        return []
    items = []
    for e in feed.entries[:20]:
        dt = entry_datetime(e)
        if not within_window(dt):
            continue
        title = clean_text(getattr(e, "title", "Untitled"))
        link = getattr(e, "link", "#")
        summary_raw = getattr(e, "summary", "") or getattr(e, "description", "")
        summary = summarize(summary_raw or title)
        items.append({
            "title": title,
            "link": link,
            "summary": summary,
            "source": name,
            "date": dt
        })
    # Sort newest first
    items.sort(key=lambda x: x["date"], reverse=True)
    return items[:MAX_ITEMS_PER_SECTION]

def pick_tool_of_week(items):
    # heuristic: prefer items from "Hugging Face" or "GitHub"
    for it in items:
        if any(k in it["source"].lower() for k in ["hugging face", "github"]):
            return {"title": it["title"], "link": it["link"], "summary": it["summary"]}
    if items:
        it = items[0]
        return {"title": it["title"], "link": it["link"], "summary": it["summary"]}
    return None

def make_hot_take(sections):
    counts = {k: len(v) for k, v in sections.items()}
    if counts.get("📄 **Viral Papers / Research**", 0) > counts.get("🚀 **Big Launches**", 0):
        return "**Research velocity** beat product launches this week; expect more **evals** and **benchmarks** shaping discourse."
    if counts.get("🚀 **Big Launches**", 0) >= 3:
        return "More **productization** than papers this week—platforms race to ship features while models stabilize."
    return "Steady drumbeat: **incremental launches**, a few **noteworthy papers**, and creative **demos** hinting at near-term use cases."

# -----------------------
# BUILD DIGEST
# -----------------------
sections = {}
flat_tools = []

for heading, feeds in SOURCES.items():
    section_items = []
    for (src_name, feed_url) in feeds:
        section_items.extend(fetch_section_items(src_name, feed_url))
    # Deduplicate by link/title
    seen = set()
    deduped = []
    for it in section_items:
        key = (it["link"] or "")[:200]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)
    sections[heading] = deduped[:MAX_ITEMS_PER_SECTION]
    if "Tools" in heading:
        flat_tools = deduped

tool_of_week = pick_tool_of_week(flat_tools)
hot_take = make_hot_take(sections)

# -----------------------
# EMAIL
# -----------------------
GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL", GMAIL_USER)
SENDER_NAME = os.environ.get("SENDER_NAME", "AI Weekly Digest Bot")

subject = subject_line(NOW, tz=TIMEZONE)
html_body = html_email(NOW.strftime("%A, %d %B %Y (%I:%M %p %Z)"), sections, tool_of_week, hot_take)

msg = MIMEMultipart("alternative")
msg["Subject"] = subject
msg["From"] = f"{SENDER_NAME} <{GMAIL_USER}>"
msg["To"] = RECIPIENT_EMAIL
msg.attach(MIMEText(html_body, "html"))

context = ssl.create_default_context()
with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
    server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
    server.sendmail(GMAIL_USER, [RECIPIENT_EMAIL], msg.as_string())
