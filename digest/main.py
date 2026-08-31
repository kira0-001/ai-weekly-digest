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
# 2-day rolling window covers weekends and time-zone delays for max story depth
DAYS_BACK = int(os.getenv("DAYS_BACK", "2"))

# Source trust levels — so readers know where data comes from
# 🟢 Official = direct from company blog/feed
# 🔵 Academic = peer-reviewed / research lab
# 🟡 Industry News = verified tech media / aggregator
TRUST_LEVELS = {
    "OpenAI Blog":         "🟢 Official",
    "Google AI Blog":      "🟢 Official",
    "DeepMind":            "🟢 Official",
    "Meta AI Blog":        "🟢 Official",
    "Microsoft AI Blog":   "🟢 Official",
    "AWS ML Blog":         "🟢 Official",
    "NVIDIA Tech Blog":    "🟢 Official",
    "Hugging Face Blog":   "🟢 Official",
    "GitHub AI & ML Blog": "🟢 Official",
    "GitHub Changelog":    "🟢 Official",
    "Google Research Blog":"🟢 Official",
    "arXiv cs.AI":         "🔵 Academic",
    "arXiv cs.LG":         "🔵 Academic",
    "arXiv cs.CL":         "🔵 Academic",
    "BAIR Blog (Berkeley)": "🔵 Academic",
    "TechCrunch AI":       "🟡 News",
    "The Verge AI":        "🟡 News",
    "MIT Tech Review AI":  "🟡 News",
    "Simon Willison AI":   "🟡 News",
    "MarkTechPost AI":     "🟡 News",
    "HF Trending Models":  "🟡 News",
    "r/MachineLearning":   "🟡 Community",
}

# Tiered & Categorized feeds
SOURCES = {
    "🚀 **Big Launches**": [
        ("OpenAI Blog", "https://openai.com/blog/rss.xml"),
        ("Google AI Blog", "https://blog.google/technology/ai/rss/"),
        ("DeepMind", "https://deepmind.google/discover/rss/"),
        ("Microsoft Source", "https://blogs.microsoft.com/feed/"),
        ("AWS ML Blog", "https://aws.amazon.com/blogs/machine-learning/feed/"),
        ("NVIDIA Tech Blog", "https://developer.nvidia.com/blog/category/data-science/feed/"),
        ("Hugging Face Blog", "https://huggingface.co/blog/feed.xml"),
        ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
        ("The Verge AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ],
    "📄 **Viral Papers / Research**": [
        ("arXiv cs.AI", "http://export.arxiv.org/rss/cs.AI"),
        ("arXiv cs.LG", "http://export.arxiv.org/rss/cs.LG"),
        ("arXiv cs.CL", "http://export.arxiv.org/rss/cs.CL"),
        ("Google Research Blog", "https://research.google/blog/rss/"),
    ],
    "🧪 **Cool Experiments & Demos**": [
        ("HF Trending Models", "https://zernel.github.io/huggingface-trending-feed/feed.xml"),
        ("Simon Willison AI", "https://simonwillison.net/atom/everything/"),
    ],
    "🛠️ **New AI Tools**": [
        ("GitHub AI & ML Blog", "https://github.blog/ai-and-ml/feed/"),
        ("GitHub Changelog", "https://github.blog/changelog/feed/"),
    ],
    "💬 **Industry Insights & Community**": [
        ("MarkTechPost AI", "https://www.marktechpost.com/feed/"),
        ("MIT Tech Review AI", "https://www.technologyreview.com/topic/artificial-intelligence/feed"),
        ("r/MachineLearning", "https://www.reddit.com/r/MachineLearning/.rss"),
    ],
}

MAX_ITEMS_PER_SECTION = 10
MAX_RETRIES = 1  # fast 1-retry fallback

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

def summarize(text, max_words=25):
    # Truncate to 25 words to keep payload small for Groq context limit
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
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    feed = None
    for attempt in range(1, MAX_RETRIES + 2):  # 1, 2
        try:
            resp = requests.get(url, headers=headers, timeout=8)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
            if feed.entries or not feed.bozo:
                break  # success
        except Exception as exc:
            log.warning("  ⚠ %s — attempt %d failed: %s", name, attempt, exc)
        if attempt <= MAX_RETRIES:
            time.sleep(1)

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

def get_best_groq_model(api_key):
    """Auto-detect the best available Groq model from a priority list.
    This prevents breakage when Groq retires models."""
    # Priority order: best quality first, fallbacks after
    PREFERRED = [
        "qwen/qwen3.6-27b",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "groq/compound",
        "groq/compound-mini",
    ]
    try:
        resp = requests.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {api_key}", "User-Agent": "Mozilla/5.0"},
            timeout=10
        )
        if resp.status_code == 200:
            available = {m["id"] for m in resp.json().get("data", [])}
            for model in PREFERRED:
                if model in available:
                    log.info("🤖 Auto-selected Groq model: %s", model)
                    return model
    except Exception as e:
        log.warning("⚠ Could not auto-detect model, using fallback: %s", e)
    # Hard fallback
    return "groq/compound"

def analyze_with_ai(raw_items, api_key):
    client = Groq(api_key=api_key)
    
    # Auto-detect best available model — never breaks when Groq retires models
    model_name = get_best_groq_model(api_key)
    
    system_prompt = """
    You are an Executive AI Research Lead and Senior Technical Mentor. You receive raw news items from the last 24 hours.
    
    Your audience: Elite AI engineers, Tech Leads, and Data Science graduates who need actionable intelligence, strategic insight, and interview mastery.
    
    Your job:
    1. Curate a rich, comprehensive digest by selecting 6 to 10 of the best, most impactful stories from the raw items across different categories.
    2. Write an "executive_summary" with 3 high-impact bullet points summarizing today's key AI meta-shifts.
    3. Categorize stories into EXACTLY these 5 sections (aim to populate every section that has relevant items):
       - "🚀 Big Launches" — Major product releases, model launches, company announcements
       - "🛠️ Builder's Toolbox" — Open-source repositories, developer tools, free tiers, dev SDKs, new weights
       - "🎯 Interview Edge" — Technical deep-dives, architectural trade-offs (e.g. KV Cache, LoRA, MoE, Quantization, Agentic Tool Use)
       - "⚖️ Responsible AI" — Governance, EU AI Act, security, guardrails, tech sovereignty, compliance
       - "🔮 On the Horizon" — Frontier research papers, novel architectures, multimodal breakthroughs
    4. For each story provide thorough details:
       - "title": Clean, professional headline
       - "summary": 2 clear sentences explaining what was built or discovered
       - "why_it_matters": 1-2 sentences explaining strategic, developer, or commercial impact
       - "takeaway": 1 punchy architectural or interview-relevant technical concept
       - "tag": 1 short category tag (e.g. "LLMs", "Infra", "Open Source", "Vision", "Robotics", "Research")
    5. ALWAYS select or curate ONE standout "tool_of_day":
       - "title": Tool or Model name + short tagline
       - "link": Primary URL
       - "summary": What it does and how developers can use it
       - "pricing": e.g. "100% Free / Open Source" or "Free Tier Available"
       - "use_case": Best use case (e.g. "Local LLM inference & prototyping")
    6. Write an insightful 1-2 sentence "hot_take" on career/market direction.
    
    Return ONLY valid JSON matching this schema:
    {
      "executive_summary": [
        "First key industry shift or release today...",
        "Second major technical or open-source milestone...",
        "Third high-level infrastructure or research breakthrough..."
      ],
      "sections": {
        "🚀 Big Launches": [
          {
            "title": "...",
            "link": "...",
            "summary": "...",
            "why_it_matters": "...",
            "takeaway": "...",
            "tag": "LLMs",
            "source": "...",
            "trust": "🟢 Official"
          }
        ],
        "🛠️ Builder's Toolbox": [],
        "🎯 Interview Edge": [],
        "⚖️ Responsible AI": [],
        "🔮 On the Horizon": []
      },
      "tool_of_day": {
        "title": "...",
        "link": "...",
        "summary": "...",
        "pricing": "100% Open Source",
        "use_case": "..."
      },
      "hot_take": "..."
    }
    
    Trust field rules:
    - Company blogs (OpenAI, Google, Meta, Microsoft, AWS, NVIDIA, GitHub, Hugging Face) = "🟢 Official"
    - arXiv, Universities, Research Labs = "🔵 Academic"
    - News sites & Media = "🟡 News"
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
    
    # Model cascade: try best model first, fall back on token/rate errors
    MODEL_CASCADE = [
        model_name,
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "groq/compound",
        "groq/compound-mini",
    ]
    # Remove duplicates preserving order
    seen_models = set()
    deduped_cascade = []
    for m in MODEL_CASCADE:
        if m not in seen_models:
            seen_models.add(m)
            deduped_cascade.append(m)

    response_data = None
    last_error = None
    succeeded = False

    for current_model in deduped_cascade:
        log.info("🤖 Trying model: %s", current_model)
        for attempt in range(2):  # 2 attempts per model
            try:
                # Ample max_tokens so output is never truncated
                chat_completion = client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    model=current_model,
                    temperature=0.2,
                    max_tokens=2500,
                    timeout=45.0,
                )
                raw = ""
                if chat_completion.choices:
                    raw = (chat_completion.choices[0].message.content or "").strip()

                log.info("📝 Raw response from %s (%d chars): %s...",
                         current_model, len(raw), raw[:120])

                if not raw:
                    log.warning("⚠ %s returned empty response. Retrying...", current_model)
                    continue

                clean_raw = raw
                # Strip reasoning blocks emitted by Qwen and reasoning models (<think>...</think>)
                clean_raw = re.sub(r'<think>[\s\S]*?</think>', '', clean_raw).strip()
                if clean_raw.startswith("```json"):
                    clean_raw = clean_raw[7:]
                if clean_raw.endswith("```"):
                    clean_raw = clean_raw[:-3]
                clean_raw = clean_raw.strip()
                
                # Validate JSON parsing immediately
                try:
                    data = json.loads(clean_raw)
                except json.JSONDecodeError:
                    match = re.search(r'\{[\s\S]*\}', clean_raw)
                    if match:
                        try:
                            data = json.loads(match.group())
                        except json.JSONDecodeError as e:
                            log.warning("⚠ %s returned invalid JSON: %s. Retrying...", current_model, e)
                            continue
                    else:
                        log.warning("⚠ %s returned no valid JSON. Retrying...", current_model)
                        continue

                response_data = data
                succeeded = True
                break
            except Exception as e:
                err = str(e)
                last_error = e
                if "429" in err:
                    log.warning("⚠ Rate limit hit on %s. Waiting 15s for TPM limit to reset...", current_model)
                    time.sleep(15)
                    break
                elif "413" in err:
                    log.warning("⚠ Payload too large for %s. Switching model...", current_model)
                    break
                elif "404" in err or "400" in err or "decommissioned" in err:
                    log.warning("⚠ Model %s unavailable: %s. Switching...", current_model, err[:80])
                    break
                else:
                    log.warning("⚠ Unexpected error on %s: %s", current_model, err[:80])
                    time.sleep(5)
        if succeeded:
            break

    if not succeeded or not response_data:
        raise RuntimeError(f"All models in cascade failed to return valid JSON. Last error: {last_error}")
        
    return (
        response_data.get("sections", {}),
        response_data.get("tool_of_day"),
        response_data.get("hot_take"),
        response_data.get("executive_summary", [])
    )

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
    # --- Fetch Raw Data per category ---
    categorized_raw = {}
    total_raw_count = 0
    seen_links = set()
    seen_slugs = set()

    for heading, feeds in SOURCES.items():
        log.info("Fetching raw section: %s (%d feeds)", heading, len(feeds))
        section_items = []
        for (src_name, feed_url) in feeds:
            items = fetch_section_items(src_name, feed_url, CUTOFF)
            for it in items:
                key = (it["link"] or "")[:200]
                slug = re.sub(r'[^a-z0-9]', '', (it.get("title") or "").lower())[:50]
                if key in seen_links or (slug and slug in seen_slugs):
                    continue
                seen_links.add(key)
                if slug:
                    seen_slugs.add(slug)
                section_items.append(it)
        categorized_raw[heading] = section_items
        total_raw_count += len(section_items)

    log.info("Collected %d unique raw items across all categories.", total_raw_count)

    # Balanced sampling: pick top 2-3 highest-signal items from EACH category
    # to guarantee diversity across Launches, Tools, Research, Demos, and Community
    selected_items = []
    for heading, items in categorized_raw.items():
        # Pick top 2 items from each category
        selected_items.extend(items[:2])
    
    # If still small, fill up to 10 items from remaining pool
    if len(selected_items) < 10:
        for heading, items in categorized_raw.items():
            for it in items[2:]:
                if it not in selected_items:
                    selected_items.append(it)
                if len(selected_items) >= 10:
                    break
            if len(selected_items) >= 10:
                break

    log.info("Sending %d diverse items across all categories to AI for rich curation.", len(selected_items))

    # --- AI Analysis ---
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
    if not GROQ_API_KEY:
        log.error("❌ GROQ_API_KEY environment variable is required for the Smart AI Curator.")
        log.error("   Get a free key from https://console.groq.com/keys and set it.")
        raise SystemExit(1)
        
    log.info("🧠 Sending data to Groq AI for executive analysis and categorization...")
    try:
        sections, tool_of_week, hot_take, exec_summary = analyze_with_ai(selected_items, GROQ_API_KEY)
        total_items = sum(len(items) for items in sections.values())
        log.info("✅ Groq returned %d curated items across %d sections.", total_items, len([s for s in sections.values() if s]))
    except Exception as e:
        log.error("❌ AI Analysis failed: %s", e)
        raise SystemExit(1)

    # Fallback for Tool of the Day if AI omitted it
    if not tool_of_week:
        tool_of_week = pick_tool_of_week(selected_items)
        if tool_of_week:
            tool_of_week["pricing"] = "100% Free / Open Source"
            tool_of_week["use_case"] = "Developer productivity & AI prototyping"

    if total_items == 0:
        log.warning("⚠ No items found in any section — digest will be empty!")

    if tool_of_week:
        log.info("Tool of the Day: %s", tool_of_week.get("title", "Unknown"))
    else:
        log.warning("No Tool of the Day selected.")

    date_str = NOW.strftime("%A, %d %B %Y (%I:%M %p %Z)")

    # --- Compose email ---
    subject = subject_line(NOW, tz=TIMEZONE)
    html_body = html_email(date_str, sections, tool_of_week, hot_take, exec_summary)
    plain_body = build_plain_text(sections, tool_of_week, hot_take, date_str)
    log.info("Email composed — Subject: %s", subject)

    # --- Generate website data ---
    try:
        save_digest_json(sections, tool_of_week, hot_take, date_str, executive_summary=exec_summary)
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
