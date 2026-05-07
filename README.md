# 🤖 AI Daily Digest

An automated, AI-powered daily news aggregation system that curates the most important AI news from 11+ sources, categorizes them using Groq AI (Llama 3), and delivers them via email and a beautiful glassmorphism website.

## ✨ Features

- **AI-Powered Curation** — Uses Groq/Llama 3 to analyze, filter, and categorize raw news
- **Career-Focused Categories** — Big Launches, Builder's Toolbox, Interview Edge, Responsible AI, On the Horizon
- **11+ RSS Sources** — OpenAI, Google AI, DeepMind, TechCrunch, The Verge, arXiv, HuggingFace, GitHub
- **Email Delivery** — Beautiful HTML emails sent daily via Gmail
- **Glassmorphism Website** — Stunning dark theme with animated backgrounds, glass cards, search, and 60-day archive
- **Fully Automated** — GitHub Actions runs daily at 10:00 AM IST

## 🔒 Security

- **Zero hardcoded secrets** — All API keys and passwords use environment variables / GitHub Secrets
- **XSS Protection** — All user-facing data is sanitized before rendering (both email and website)
- **URL Sanitization** — Only `http://` and `https://` URLs are allowed
- **HTML Escaping** — RSS data is escaped via `html.escape()` before email insertion
- **SSL/TLS** — Email sent over encrypted SMTP_SSL connection
- **Content Security** — `rel="noopener noreferrer"` on all external links

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Free [Groq API Key](https://console.groq.com/keys)
- Gmail App Password ([instructions](https://myaccount.google.com/apppasswords))

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export GROQ_API_KEY="your-groq-key"
export GMAIL_USER="your-email@gmail.com"
export GMAIL_APP_PASSWORD="your-16-char-app-password"

# Dry run (preview only, no email)
cd digest
python main.py --dry-run

# Full run (sends email)
python main.py
```

### GitHub Actions (Automated Daily)
Add these secrets in **Settings → Secrets → Actions**:

| Secret | Description |
|---|---|
| `GROQ_API_KEY` | Your Groq API key |
| `GMAIL_USER` | Your Gmail address |
| `GMAIL_APP_PASSWORD` | Gmail App Password (16 chars) |
| `RECIPIENT_EMAIL` | Comma-separated recipient emails |

## 📁 Project Structure

```
ai-weekly-digest-1/
├── .github/workflows/
│   └── ai-weekly-digest.yml   # Daily automation (10 AM IST)
├── digest/
│   ├── main.py                # Core pipeline: fetch → AI → email
│   ├── templates.py           # HTML email template
│   └── generate_site.py       # Website JSON generator
├── docs/
│   ├── index.html             # Glassmorphism website
│   └── data/
│       ├── latest.json        # Today's digest
│       ├── archive/           # 60-day rolling archive
│       └── archive_index.json # Archive date list
├── config.json                # Recipients and settings
├── requirements.txt           # Python dependencies
└── README.md
```

## 📡 News Sources

| Source | Type | Status |
|---|---|---|
| OpenAI Blog | 🟢 Official | ✅ Active |
| Google AI Blog | 🟢 Official | ✅ Active |
| DeepMind | 🟢 Official | ✅ Active |
| HuggingFace Blog | 🟢 Official | ✅ Active |
| TechCrunch AI | 📰 News | ✅ Active |
| The Verge AI | 📰 News | ✅ Active |
| arXiv cs.AI / cs.LG / cs.CL | 🎓 Academic | ✅ Active |
| HF Trending Models | 🟡 Community | ✅ Active |
| Google Research Blog | 🟢 Official | ✅ Active |
| GitHub Blog & Changelog | 🟢 Official | ✅ Active |

## 📄 License

MIT License — free to use, modify, and distribute.