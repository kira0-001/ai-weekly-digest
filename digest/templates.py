from datetime import datetime
import html as html_mod
import pytz
import re

def esc(s: str) -> str:
    """Escape a string for safe HTML insertion."""
    return html_mod.escape(str(s)) if s else ""

def get_favicon(link):
    """Extract domain from a link and return a Google favicon URL."""
    try:
        domain = re.findall(r'https?://([^/]+)', link or "")[0]
        return f"https://www.google.com/s2/favicons?domain={domain}&sz=32"
    except Exception:
        return "https://www.google.com/s2/favicons?domain=github.com&sz=32"

def html_email(subject_date_str, sections, tool_of_week=None, hot_take=None):
    # Trust badge styles
    trust_styles = {
        "🟢 Official": ("background:#e8f5e9;color:#2e7d32;border:1px solid #c8e6c9;", "✅ Official"),
        "🔵 Academic": ("background:#e3f2fd;color:#1565c0;border:1px solid #bbdefb;", "🎓 Academic"),
        "🟡 Community": ("background:#fff8e1;color:#f57f17;border:1px solid #ffecb3;", "📰 News"),
    }

    def trust_badge(trust_str):
        style, label = trust_styles.get(trust_str, ("background:#f5f5f5;color:#666;border:1px solid #e0e0e0;", "Source"))
        return f'<span style="display:inline-block;padding:2px 10px;border-radius:20px;font-size:11px;font-weight:600;{style}">{label}</span>'

    # Section accent colors
    section_meta = {
        "🚀 Big Launches":        {"color": "#6C63FF", "icon": "🚀", "label": "Big Launches"},
        "🛠️ Builder's Toolbox":   {"color": "#FF6D00", "icon": "🛠️", "label": "Builder's Toolbox — Free Tools & Trials"},
        "🎯 Interview Edge":      {"color": "#00BFA5", "icon": "🎯", "label": "Interview Edge — Concepts to Master"},
        "⚖️ Responsible AI":      {"color": "#D500F9", "icon": "⚖️", "label": "Responsible AI — Ethics & Governance"},
        "🔮 On the Horizon":      {"color": "#FF1744", "icon": "🔮", "label": "On the Horizon — Breakthroughs"},
    }

    def render_items(items, accent):
        cards = []
        for it in items:
            title = esc(it.get("title", "").strip())
            link = esc(it.get("link", "#"))
            summary = esc(it.get("summary", "").strip())
            source = esc(it.get("source", "").strip())
            trust = it.get("trust", "")
            badge = trust_badge(trust)
            favicon = get_favicon(it.get("link", ""))

            cards.append(f"""
              <tr><td style="padding:0 0 12px 0;">
                <table width="100%" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:10px;border:1px solid #eee;border-left:4px solid {accent};">
                  <tr>
                    <td style="padding:16px 18px;">
                      <table width="100%" cellpadding="0" cellspacing="0">
                        <tr>
                          <td width="36" valign="top" style="padding-right:12px;">
                            <img src="{favicon}" width="28" height="28" style="border-radius:6px;border:1px solid #eee;" alt="{source}">
                          </td>
                          <td valign="top">
                            <a href="{link}" style="font-size:15px;font-weight:700;color:#1a1a2e;text-decoration:none;line-height:1.3;">{title}</a>
                            <p style="margin:6px 0 8px;font-size:13px;color:#555;line-height:1.5;">{summary}</p>
                            <table cellpadding="0" cellspacing="0"><tr>
                              <td style="padding-right:8px;font-size:11px;color:#999;">{source}</td>
                              <td>{badge}</td>
                            </tr></table>
                          </td>
                        </tr>
                      </table>
                    </td>
                  </tr>
                </table>
              </td></tr>
            """)
        return "\n".join(cards)

    blocks = []
    for heading, items in sections.items():
        if not items:
            continue
        meta = section_meta.get(heading, {"color": "#6C63FF", "icon": "📌", "label": heading.replace("**","").strip()})
        blocks.append(f"""
          <tr><td style="padding:24px 0 10px 0;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="font-size:20px;font-weight:800;color:#1a1a2e;padding-bottom:12px;border-bottom:3px solid {meta['color']};">
                  <span style="font-size:22px;">{meta['icon']}</span> {meta['label']}
                </td>
              </tr>
            </table>
          </td></tr>
          {render_items(items, meta['color'])}
        """)

    # Tool of the Day
    tool_block = ""
    if tool_of_week:
        tw_link = esc(tool_of_week.get('link', '#'))
        tw_title = esc(tool_of_week.get('title', ''))
        tw_summary = esc(tool_of_week.get('summary', ''))
        tw_favicon = get_favicon(tool_of_week.get('link', ''))
        tool_block = f"""
          <tr><td style="padding:20px 0;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background:linear-gradient(135deg,#667eea,#764ba2);border-radius:12px;">
              <tr><td style="padding:20px 24px;">
                <div style="font-size:11px;text-transform:uppercase;letter-spacing:2px;color:rgba(255,255,255,0.7);font-weight:700;margin-bottom:8px;">⭐ Tool of the Day</div>
                <table cellpadding="0" cellspacing="0"><tr>
                  <td width="36" valign="top" style="padding-right:12px;">
                    <img src="{tw_favicon}" width="28" height="28" style="border-radius:6px;border:2px solid rgba(255,255,255,0.3);" alt="">
                  </td>
                  <td>
                    <a href="{tw_link}" style="font-size:17px;font-weight:800;color:#fff;text-decoration:none;">{tw_title}</a>
                    <p style="margin:6px 0 0;font-size:13px;color:rgba(255,255,255,0.85);line-height:1.5;">{tw_summary}</p>
                  </td>
                </tr></table>
              </td></tr>
            </table>
          </td></tr>
        """

    # Hot Take
    hot_block = ""
    if hot_take:
        hot_block = f"""
          <tr><td style="padding:8px 0 16px;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background:#fff5f5;border-radius:10px;border:1px solid #fecaca;">
              <tr><td style="padding:16px 20px;">
                <div style="font-size:11px;text-transform:uppercase;letter-spacing:2px;color:#dc2626;font-weight:700;margin-bottom:6px;">🔥 Hot Take</div>
                <p style="margin:0;font-size:14px;color:#7f1d1d;line-height:1.5;font-style:italic;">{esc(hot_take)}</p>
              </td></tr>
            </table>
          </td></tr>
        """

    # Stats
    total_items = sum(len(items) for items in sections.values())
    num_sections = len([s for s in sections.values() if s])
    num_sources = len(set(it.get("source","") for items in sections.values() for it in items))

    return f"""<!doctype html>
<html>
  <head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
  <body style="margin:0;padding:0;background:#f0f2f5;font-family:'Segoe UI',system-ui,-apple-system,Roboto,Arial,sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f2f5;">
      <tr><td align="center" style="padding:20px 12px;">
        <table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;">

          <!-- Header -->
          <tr><td style="padding:0 0 20px;text-align:center;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background:linear-gradient(135deg,#6C63FF,#4facfe);border-radius:16px;">
              <tr><td style="padding:28px 24px;text-align:center;">
                <div style="font-size:32px;font-weight:900;color:#fff;letter-spacing:-0.5px;">AI Daily Digest</div>
                <div style="margin-top:6px;font-size:13px;color:rgba(255,255,255,0.8);">{subject_date_str}</div>
                <div style="margin-top:12px;font-size:12px;color:rgba(255,255,255,0.7);">Your daily dose of what matters in AI — curated by AI</div>
              </td></tr>
            </table>
          </td></tr>

          <!-- Stats Bar -->
          <tr><td style="padding:0 0 16px;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;border:1px solid #eee;">
              <tr>
                <td style="padding:14px;text-align:center;width:33%;">
                  <div style="font-size:24px;font-weight:800;color:#6C63FF;">{total_items}</div>
                  <div style="font-size:10px;color:#999;text-transform:uppercase;letter-spacing:1px;">Stories</div>
                </td>
                <td style="padding:14px;text-align:center;width:33%;border-left:1px solid #f0f0f0;border-right:1px solid #f0f0f0;">
                  <div style="font-size:24px;font-weight:800;color:#00BFA5;">{num_sections}</div>
                  <div style="font-size:10px;color:#999;text-transform:uppercase;letter-spacing:1px;">Categories</div>
                </td>
                <td style="padding:14px;text-align:center;width:33%;">
                  <div style="font-size:24px;font-weight:800;color:#FF6D00;">{num_sources}</div>
                  <div style="font-size:10px;color:#999;text-transform:uppercase;letter-spacing:1px;">Sources</div>
                </td>
              </tr>
            </table>
          </td></tr>

          <!-- Sections -->
          {''.join(blocks)}

          <!-- Tool of the Day -->
          {tool_block}

          <!-- Hot Take -->
          {hot_block}

          <!-- Footer -->
          <tr><td style="padding:20px 0;text-align:center;">
            <div style="font-size:11px;color:#999;line-height:1.7;">
              Curated by AI \u2022 Powered by Groq &amp; Llama 3<br>
              Every link goes to the original source \u2014 click to verify<br>
              <span style="color:#bbb;">Built with \u2764\ufe0f for staying ahead in AI</span>
            </div>
          </td></tr>

        </table>
      </td></tr>
    </table>
  </body>
</html>"""

def subject_line(dt, tz="Asia/Kolkata"):
    tzinfo = pytz.timezone(tz)
    return f"AI Daily Digest \u2014 {dt.astimezone(tzinfo).strftime('%b %d, %Y')}"
