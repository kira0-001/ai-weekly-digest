import argparse
import datetime
import html
import logging
import os
import re
import ssl
import smtplib
import time
import urllib.parse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

from dateutil import parser
import pytz
import feedparser
from bs4 import BeautifulSoup
from templates import html_email, subject_line
from generate_site import save_digest_json
from groq import Groq
import warnings
import json

# Suppress BS4 filename/markup warnings
warnings.filterwarnings("ignore", category=UserWarning, module='bs4')
try:
    from bs4 import MarkupResemblesLocatorWarning
    warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)
except ImportError:
    pass

# Set a browser-like User-Agent to bypass basic feed blocks
feedparser.USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# -----------------------
# LOGGING
# -----------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("ai-digest")

# -----------------------
# CONFIG
# -----------------------
TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")
DAYS_BACK = int(os.getenv("DAYS_BACK", "1"))  # 1 = daily, 7 = weekly

# Source trust levels — so readers know where data comes from
# 🟢 Official = direct from the company's own blog/feed
# 🟡 Community = third-party aggregator (accurate but unofficial)
# 🔵 Academic = peer-reviewed / university-hosted
TRUST_LEVELS = {
    "OpenAI Blog":         "🟢 Official",
    "Google AI Blog":      "🟢 Official",
    "DeepMind":            "🟢 Official",
    "Meta AI":             "🟢 Official",
    "Anthropic":           "🟢 Official",
    "Hugging Face Blog":   "🟢 Official",
    "TechCrunch AI":       "🟡 Community",
    "The Verge AI":        "🟡 Community",
    "r/MachineLearning":   "🟡 Community",
    "r/artificial":        "🟡 Community",
    "MIT Tech Review AI":  "🟡 Community",
    "arXiv cs.AI":         "🔵 Academic",
    "arXiv cs.LG":         "🔵 Academic",
    "arXiv cs.CL":         "🔵 Academic",
    "HF Trending Models":  "🟡 Community",
    "Google Research Blog": "🟢 Official",
    "GitHub AI & ML Blog": "🟢 Official",
    "GitHub Changelog":    "🟢 Official",
}

# Curated sources (reliable, low-friction RSS)
SOURCES = {
    "🚀 **Big Launches**": [
        ("OpenAI Blog", "https://openai.com/blog/rss.xml"),
        ("Google AI Blog", "https://blog.google/technology/ai/rss/"),
        ("DeepMind", "https://deepmind.google/discover/rss/"),
        # Anthropic has no public RSS — covered via TechCrunch & The Verge
        ("Hugging Face Blog", "https://huggingface.co/blog/feed.xml"),
        ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
        ("The Verge AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ],
    "📄 **Viral Papers / Research**": [
        ("arXiv cs.AI", "http://export.arxiv.org/rss/cs.AI"),
        ("arXiv cs.LG", "http://export.arxiv.org/rss/cs.LG"),
        ("arXiv cs.CL", "http://export.arxiv.org/rss/cs.CL"),
    ],
    "🧪 **Cool Experiments & Demos**": [
        ("HF Trending Models", "https://zernel.github.io/huggingface-trending-feed/feed.xml"),
        ("Google Research Blog", "https://research.google/blog/rss/"),
    ],
    "🛠️ **New AI Tools**": [
        ("GitHub AI & ML Blog", "https://github.blog/ai-and-ml/feed/"),
        ("GitHub Changelog", "https://github.blog/changelog/feed/"),
    ],
    "💬 **Community & Discussions**": [
        ("r/MachineLearning", "https://www.reddit.com/r/MachineLearning/.rss"),
        ("r/artificial", "https://www.reddit.com/r/artificial/.rss"),
        ("MIT Tech Review AI", "https://www.technologyreview.com/topic/artificial-intelligence/feed"),
    ],
}

MAX_ITEMS_PER_SECTION = 10  # more items for daily (fewer per day)
MAX_RETRIES = 2  # retry once on failure

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

def summarize(text, max_words=50):
    # Pass 50 words instead of 200 to keep the input token count small enough for Groq's free tier
    text = clean_text(text)
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "…"

def within_window(dt, cutoff):
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt >= cutoff.astimezone(dt.tzinfo)

def fetch_section_items(name, url, cutoff):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    feed = None
    for attempt in range(1, MAX_RETRIES + 2):  # 1, 2, 3
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
            if feed.entries or not feed.bozo:
                break  # success
        except Exception as exc:
            log.warning("  ⚠ %s — attempt %d failed: %s", name, attempt, exc)
        if attempt <= MAX_RETRIES:
            wait = 2 ** attempt  # 2s, 4s
            log.info("  ↻ %s — retrying in %ds...", name, wait)
            time.sleep(wait)

    if feed is None or (feed.bozo and not feed.entries):
        log.warning("  ✗ %s — all attempts failed (URL may be invalid or blocked)", name)
        return []

    items = []
    for e in feed.entries[:20]:
        dt = entry_datetime(e)
        if not within_window(dt, cutoff):
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
            "trust": TRUST_LEVELS.get(name, "⚪ Unknown"),
            "date": dt
        })
    # Sort newest first
    items.sort(key=lambda x: x["date"], reverse=True)
    result = items[:MAX_ITEMS_PER_SECTION]
    log.info("  ✓ %s — %d items (from %d entries)", name, len(result), len(feed.entries))
    return result

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
        return "**Research velocity** beat product launches today; expect more **evals** and **benchmarks** shaping discourse."
    if counts.get("🚀 **Big Launches**", 0) >= 3:
        return "More **productization** than papers today—platforms race to ship features while models stabilize."
    return "Steady drumbeat: **incremental launches**, a few **noteworthy papers**, and creative **demos** hinting at near-term use cases."

def build_plain_text(sections, tool_of_week, hot_take, date_str):
    """Build a plain-text version of the digest for email fallback."""
    lines = ["AI DAILY DIGEST", date_str, "=" * 40, ""]
    lines.append("Trust: 🟢 Official | 🔵 Academic | 🟡 Community")
    lines.append("")
    for heading, items in sections.items():
        if not items:
            continue
        # Strip markdown bold markers for plain text
        clean_heading = heading.replace("**", "")
        lines.append(clean_heading)
        lines.append("-" * len(clean_heading))
        for it in items:
            trust = it.get('trust', '')
            lines.append(f"  • {it['title']}")
            lines.append(f"    {it['summary']}")
            lines.append(f"    Source: {it['source']} | {trust}")
            lines.append(f"    {it['link']}")
            lines.append("")
    if tool_of_week:
        lines.append("🛠️ TOOL OF THE DAY")
        lines.append(f"  {tool_of_week['title']}")
        lines.append(f"  {tool_of_week.get('summary', '')}")
        lines.append(f"  {tool_of_week['link']}")
        lines.append("")
    if hot_take:
        lines.append("🔥 HOT TAKE")
        lines.append(f"  {hot_take.replace('**', '')}")
        lines.append("")
    lines.append("—")
    lines.append("Auto-generated by AI Daily Digest Bot.")
    lines.append("All items link to their original sources — click to verify.")
    return "\n".join(lines)

def build_whatsapp_summary(sections, tool_of_week, date_str):
    """Build a compact WhatsApp-friendly summary."""
    lines = [f"🤖 *AI Daily Digest*", f"📅 {date_str}", ""]
    for heading, items in sections.items():
        if not items:
            continue
        clean_heading = heading.replace("**", "*")
        lines.append(clean_heading)
        for it in items[:3]:  # top 3 per section for WhatsApp brevity
            lines.append(f"  • {it['title']}")
        lines.append("")
    if tool_of_week:
        lines.append(f"🛠️ *Tool of the Day:* {tool_of_week['title']}")
    lines.append("\n📬 Full digest sent to your email!")
    return "\n".join(lines)

def send_whatsapp(message, phone, api_key):
    """Send a WhatsApp message via CallMeBot free API."""
    url = "https://api.callmebot.com/whatsapp.php"
    params = {
        "phone": phone,
        "text": message,
        "apikey": api_key,
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code == 200:
            log.info("✅ WhatsApp message sent to %s", phone)
        else:
            log.warning("⚠ WhatsApp send failed (HTTP %d): %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        log.warning("⚠ WhatsApp send error: %s", exc)

def analyze_with_ai(raw_items, api_key):
    client = Groq(api_key=api_key)
    
    # Using Llama 3.1 8B via Groq because the 70B model has a strict 12k TPM limit on the free tier
    model_name = "llama-3.1-8b-instant"
    
    system_prompt = """
    You are a Senior AI Research Lead and Career Mentor. You receive raw news items from the last 24 hours.
    
    Your audience: A B.Tech AI & Data Science graduate who wants to stay interview-ready and professionally aware.
    
    Your job:
    1. Discard noise. Keep only important, useful, and actionable items.
    2. Categorize items into EXACTLY these 5 sections:
       - "🚀 Big Launches" — Major product releases, model launches, company announcements
       - "🛠️ Builder's Toolbox" — Free tools, libraries, student trials, open-source releases. Highlight anything FREE
       - "🎯 Interview Edge" — Technical trends relevant to interviews: Agentic AI, MLOps, RAG, Edge AI, Multimodal models. Connect news to interview concepts
       - "⚖️ Responsible AI" — Ethics, EU AI Act, bias, explainability, tech sovereignty, regulation news
       - "🔮 On the Horizon" — Research breakthroughs, new architectures, quantum AI, novel techniques
    3. For each item, write a 1-2 sentence summary that is easy to understand. Add a "Why it matters" angle where possible
    4. Select ONE best "Tool of the Day" (preferably something free/useful for students)
    5. Write a 1-sentence "Hot Take" connecting today's news to career/industry trends
    
    Return ONLY pure valid JSON. No markdown blocks. No ```json wrapping.
    
    JSON schema:
    {
      "sections": {
        "🚀 Big Launches": [
          {"title": "...", "link": "...", "summary": "...", "source": "...", "trust": "🟢 Official"}
        ],
        "🛠️ Builder's Toolbox": [...],
        "🎯 Interview Edge": [...],
        "⚖️ Responsible AI": [...],
        "🔮 On the Horizon": [...]
      },
      "tool_of_day": {"title": "...", "link": "...", "summary": "..."},
      "hot_take": "..."
    }
    
    Trust field rules:
    - Company blog (OpenAI, Google, Meta, GitHub, Anthropic, HuggingFace) = "🟢 Official"
    - arXiv or university = "🔵 Academic"
    - News site or community = "🟡 Community"
    
    IMPORTANT: If a section has no relevant items, use an empty array []. Always include all 5 section keys.
    """
    
    clean_items = []
    for it in raw_items:
        clean_items.append({
            "title": it["title"],
            "source": it["source"],
            "summary": it["summary"],
            "link": it["link"]
        })
    
    user_prompt = "Raw Items:\n" + json.dumps(clean_items, indent=2)
    
    max_retries = 3
    response_text = ""
    for attempt in range(max_retries):
        try:
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                model=model_name,
                temperature=0.2,
                max_tokens=2000,
            )
            response_text = chat_completion.choices[0].message.content.strip()
            break
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                log.warning("⚠ Groq API rate limit hit. Waiting 20 seconds before retrying...")
                time.sleep(20)
            else:
                raise
    
    if response_text.startswith("```json"):
        response_text = response_text[7:]
    if response_text.endswith("```"):
        response_text = response_text[:-3]
        
    # Try to extract JSON even if wrapped in extra text
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        # Try to find JSON object in the response
        match = re.search(r'\{[\s\S]*\}', response_text)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError as e:
                log.error("Failed to parse AI JSON response: %s", e)
                log.error("Raw response (first 500 chars): %s", response_text[:500])
                raise
        else:
            log.error("No JSON found in AI response. Raw (first 500 chars): %s", response_text[:500])
            raise ValueError("AI returned no valid JSON")
        
    return data.get("sections", {}), data.get("tool_of_day"), data.get("hot_take")

# -----------------------
# MAIN
# -----------------------
def main(dry_run=False):
    log.info("=== AI Weekly Digest ===")
    if dry_run:
        log.info("🧪 DRY-RUN mode — will save HTML locally, not send email")

    # --- Validate credentials (skip in dry-run) ---
    GMAIL_USER = os.environ.get("GMAIL_USER")
    GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
    if not dry_run and (not GMAIL_USER or not GMAIL_APP_PASSWORD):
        log.error("❌ GMAIL_USER and GMAIL_APP_PASSWORD environment variables are required.")
        log.error('   Set them: export GMAIL_USER="you@gmail.com"')
        log.error("   Or use --dry-run to preview without sending.")
        raise SystemExit(1)

    # --- Load config.json if available (easy recipient management) ---
    config = {}
    config_path = os.path.join(os.path.dirname(__file__), "..", "config.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        log.info("📋 Loaded config.json")

    # --- Recipients: config.json → env vars → fallback ---
    recipients = config.get("email_recipients", [])
    if not recipients:
        RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL", GMAIL_USER or "preview@localhost")
        recipients = [e.strip() for e in RECIPIENT_EMAIL.split(",") if e.strip()]
    SENDER_NAME = config.get("sender_name", os.environ.get("SENDER_NAME", "AI Daily Digest Bot"))
    log.info("Recipients (%d): %s", len(recipients), ", ".join(recipients))

    # WhatsApp config: config.json → env vars
    wa_recipients = config.get("whatsapp_recipients", [])
    if wa_recipients:
        # config.json format: [{"phone": "+91...", "api_key": "123"}]
        wa_phones = [r["phone"] for r in wa_recipients if r.get("phone")]
        wa_keys = [r["api_key"] for r in wa_recipients if r.get("api_key")]
    else:
        wa_phone_raw = os.environ.get("WHATSAPP_PHONE", "")
        wa_key_raw = os.environ.get("WHATSAPP_API_KEY", "")
        wa_phones = [p.strip() for p in wa_phone_raw.split(",") if p.strip()]
        wa_keys = [k.strip() for k in wa_key_raw.split(",") if k.strip()]

    # --- Time window ---
    NOW = datetime.datetime.now(pytz.timezone(TIMEZONE))
    CUTOFF = NOW - datetime.timedelta(days=DAYS_BACK)
    log.info("Time window: %s → %s", CUTOFF.strftime("%b %d"), NOW.strftime("%b %d, %Y"))

    # --- Fetch Raw Data ---
    all_raw_items = []

    for heading, feeds in SOURCES.items():
        log.info("Fetching raw section: %s (%d feeds)", heading, len(feeds))
        for (src_name, feed_url) in feeds:
            all_raw_items.extend(fetch_section_items(src_name, feed_url, CUTOFF))

    # Deduplicate early by link
    seen_links = set()
    unique_items = []
    for it in all_raw_items:
        key = (it["link"] or "")[:200]
        if key in seen_links: continue
        seen_links.add(key)
        unique_items.append(it)
        
    log.info("Collected %d unique raw items.", len(unique_items))
    
    # Cap to top 20 items to fit within Groq's strict 6k TPM free limit
    unique_items = unique_items[:20]
    log.info("Sending top %d items to AI to respect token limits.", len(unique_items))

    # --- AI Analysis ---
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
    if not GROQ_API_KEY:
        log.error("❌ GROQ_API_KEY environment variable is required for the Smart AI Curator.")
        log.error("   Get a free key from https://console.groq.com/keys and set it.")
        raise SystemExit(1)
        
    log.info("🧠 Sending data to Groq AI (Llama 3) for analysis and categorization...")
    try:
        sections, tool_of_week, hot_take = analyze_with_ai(unique_items, GROQ_API_KEY)
        total_items = sum(len(items) for items in sections.values())
        log.info("✅ Groq returned %d curated items.", total_items)
    except Exception as e:
        log.error("❌ AI Analysis failed: %s", e)
        raise SystemExit(1)
    log.info("Total items across all sections: %d", total_items)

    if total_items == 0:
        log.warning("⚠ No items found in any section — digest will be empty!")

    if tool_of_week:
        log.info("Tool of the Day: %s", tool_of_week.get("title", "Unknown"))
    else:
        log.warning("No Tool of the Day selected.")

    date_str = NOW.strftime("%A, %d %B %Y (%I:%M %p %Z)")

    # --- Compose email ---
    subject = subject_line(NOW, tz=TIMEZONE)
    html_body = html_email(date_str, sections, tool_of_week, hot_take)
    plain_body = build_plain_text(sections, tool_of_week, hot_take, date_str)
    log.info("Email composed — Subject: %s", subject)

    # --- Generate website data ---
    try:
        save_digest_json(sections, tool_of_week, hot_take, date_str)
        log.info("🌐 Website data saved to docs/data/")
    except Exception as exc:
        log.warning("⚠ Website data generation failed: %s", exc)

    # --- Dry-run: save to file ---
    if dry_run:
        out_file = "digest_preview.html"
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(html_body)
        out_txt = "digest_preview.txt"
        with open(out_txt, "w", encoding="utf-8") as f:
            f.write(plain_body)
        log.info("✅ Preview saved: %s (HTML) + %s (plain text)", out_file, out_txt)
        return

    # --- Send email to all recipients ---
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{SENDER_NAME} <{GMAIL_USER}>"
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(plain_body, "plain", "utf-8"))  # fallback first
    msg.attach(MIMEText(html_body, "html", "utf-8"))    # preferred second

    log.info("Connecting to smtp.gmail.com...")
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, recipients, msg.as_string())

    log.info("✅ Digest email sent to %d recipient(s): %s", len(recipients), ", ".join(recipients))

    # --- Send WhatsApp notification (optional) ---
    if wa_phones and wa_keys:
        if len(wa_phones) != len(wa_keys):
            log.warning("⚠ WhatsApp: %d phone(s) but %d API key(s) — they must match! (skipping)",
                        len(wa_phones), len(wa_keys))
        else:
            wa_msg = build_whatsapp_summary(sections, tool_of_week, date_str)
            for phone, key in zip(wa_phones, wa_keys):
                log.info("Sending WhatsApp to %s...", phone)
                send_whatsapp(wa_msg, phone, key)
    elif wa_phones or wa_keys:
        log.warning("⚠ WhatsApp: both WHATSAPP_PHONE and WHATSAPP_API_KEY are needed (skipping)")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description="AI Weekly Digest — curated AI news via email & WhatsApp")
    cli.add_argument("--dry-run", action="store_true",
                     help="Fetch feeds and save HTML preview locally (no email sent)")
    args = cli.parse_args()
    main(dry_run=args.dry_run)
