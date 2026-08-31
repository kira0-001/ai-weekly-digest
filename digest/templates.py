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

def html_email(subject_date_str, sections, tool_of_week=None, hot_take=None, executive_summary=None):
    # Trust badge styles
    trust_styles = {
        "🟢 Official": ("background:#ecfdf5;color:#047857;border:1px solid #a7f3d0;", "✅ Official"),
        "🔵 Academic": ("background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;", "🎓 Academic"),
        "🟡 News":     ("background:#fffbeb;color:#b45309;border:1px solid #fde68a;", "📰 News"),
        "🟡 Community":("background:#faf5ff;color:#6b21a8;border:1px solid #e9d5ff;", "💬 Community"),
    }

    def trust_badge(trust_str):
        style, label = trust_styles.get(trust_str, ("background:#f8fafc;color:#475569;border:1px solid #e2e8f0;", "Source"))
        return f'<span style="display:inline-block;padding:2px 8px;border-radius:12px;font-size:10px;font-weight:700;letter-spacing:0.3px;{style}">{label}</span>'

    # Section accent colors & branding
    section_meta = {
        "🚀 Big Launches":        {"color": "#4f46e5", "bg": "#eef2ff", "icon": "🚀", "label": "Big Launches & Milestones"},
        "🛠️ Builder's Toolbox":   {"color": "#d97706", "bg": "#fffbeb", "icon": "🛠️", "label": "Builder's Toolbox — Tools & Releases"},
        "🎯 Interview Edge":      {"color": "#059669", "bg": "#ecfdf5", "icon": "🎯", "label": "Interview Edge — Concepts to Master"},
        "⚖️ Responsible AI":      {"color": "#7c3aed", "bg": "#f5f3ff", "icon": "⚖️", "label": "Responsible AI & Governance"},
        "🔮 On the Horizon":      {"color": "#e11d48", "bg": "#fff1f2", "icon": "🔮", "label": "On the Horizon — Frontier Research"},
    }

    def render_items(items, accent):
        cards = []
        for it in items:
            title = esc(it.get("title", "").strip())
            link = esc(it.get("link", "#"))
            summary = esc(it.get("summary", "").strip())
            why_it_matters = esc(it.get("why_it_matters", "").strip())
            takeaway = esc(it.get("takeaway", "").strip())
            tag = esc(it.get("tag", "").strip())
            source = esc(it.get("source", "").strip())
            trust = it.get("trust", "")
            badge = trust_badge(trust)
            favicon = get_favicon(it.get("link", ""))

            # Build structured sub-points if available
            insights_html = []
            if why_it_matters:
                insights_html.append(f"""
                  <div style="margin-top:6px;font-size:12px;line-height:1.5;color:#334155;">
                    <strong style="color:#0f172a;">⚡ Why it matters:</strong> {why_it_matters}
                  </div>
                """)
            if takeaway:
                insights_html.append(f"""
                  <div style="margin-top:5px;font-size:12px;line-height:1.5;color:#334155;">
                    <strong style="color:#0f172a;">🧠 Takeaway:</strong> {takeaway}
                  </div>
                """)

            tag_pill = f'<span style="display:inline-block;padding:2px 8px;border-radius:12px;font-size:10px;font-weight:600;background:#f1f5f9;color:#475569;margin-right:6px;">#{tag}</span>' if tag else ""

            cards.append(f"""
              <tr><td style="padding:0 0 14px 0;">
                <table width="100%" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;border:1px solid #e2e8f0;border-left:4px solid {accent};box-shadow:0 1px 3px rgba(0,0,0,0.04);">
                  <tr>
                    <td style="padding:16px 18px;">
                      <table width="100%" cellpadding="0" cellspacing="0">
                        <tr>
                          <td width="36" valign="top" style="padding-right:12px;">
                            <img src="{favicon}" width="26" height="26" style="border-radius:6px;border:1px solid #e2e8f0;display:block;" alt="">
                          </td>
                          <td valign="top">
                            <div style="margin-bottom:4px;">
                              {tag_pill}
                              <span style="font-size:11px;color:#64748b;font-weight:600;">{source}</span>
                              <span style="margin-left:6px;">{badge}</span>
                            </div>
                            <a href="{link}" style="font-size:15px;font-weight:700;color:#0f172a;text-decoration:none;line-height:1.35;display:inline-block;">{title}</a>
                            <p style="margin:6px 0 0;font-size:13px;color:#475569;line-height:1.5;">{summary}</p>
                            {''.join(insights_html)}
                            <div style="margin-top:8px;">
                              <a href="{link}" style="font-size:11px;font-weight:700;color:{accent};text-decoration:none;letter-spacing:0.3px;">Read Source &rarr;</a>
                            </div>
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
        meta = section_meta.get(heading, {"color": "#4f46e5", "bg": "#eef2ff", "icon": "📌", "label": heading.replace("**","").strip()})
        blocks.append(f"""
          <tr><td style="padding:22px 0 10px 0;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="font-size:17px;font-weight:800;color:#0f172a;padding-bottom:10px;border-bottom:2px solid {meta['color']};">
                  <span style="font-size:18px;">{meta['icon']}</span> {meta['label']}
                </td>
              </tr>
            </table>
          </td></tr>
          {render_items(items, meta['color'])}
        """)

    # Executive TL;DR Snapshot
    exec_block = ""
    if executive_summary and isinstance(executive_summary, list) and len(executive_summary) > 0:
        bullets = "".join([f'<li style="margin-bottom:6px;">{esc(b)}</li>' for b in executive_summary])
        exec_block = f"""
          <tr><td style="padding:0 0 18px 0;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;border-radius:12px;border:1px solid #cbd5e1;border-left:4px solid #0f172a;">
              <tr><td style="padding:16px 20px;">
                <div style="font-size:11px;text-transform:uppercase;letter-spacing:1.5px;color:#0f172a;font-weight:800;margin-bottom:8px;">⚡ Executive TL;DR &bull; Today\'s Snapshot</div>
                <ul style="margin:0;padding-left:18px;font-size:13px;color:#334155;line-height:1.6;">
                  {bullets}
                </ul>
              </td></tr>
            </table>
          </td></tr>
        """

    # Tool of the Day
    tool_block = ""
    if tool_of_week:
        tw_link = esc(tool_of_week.get('link', '#'))
        tw_title = esc(tool_of_week.get('title', ''))
        tw_summary = esc(tool_of_week.get('summary', ''))
        tw_pricing = esc(tool_of_week.get('pricing', '100% Free / Open Source'))
        tw_use_case = esc(tool_of_week.get('use_case', 'Prototyping & Demos'))
        tw_favicon = get_favicon(tool_of_week.get('link', ''))
        tool_block = f"""
          <tr><td style="padding:16px 0 12px 0;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background:linear-gradient(135deg,#1e1b4b,#312e81);border-radius:14px;box-shadow:0 4px 12px rgba(49,46,129,0.15);">
              <tr><td style="padding:22px 24px;">
                <table width="100%" cellpadding="0" cellspacing="0">
                  <tr>
                    <td>
                      <span style="font-size:10px;text-transform:uppercase;letter-spacing:1.5px;color:#a5b4fc;font-weight:800;">⭐ Spotlight &bull; Tool of the Day</span>
                    </td>
                    <td align="right">
                      <span style="font-size:10px;padding:2px 8px;border-radius:10px;background:rgba(255,255,255,0.15);color:#ffffff;font-weight:700;">{tw_pricing}</span>
                    </td>
                  </tr>
                </table>
                <table cellpadding="0" cellspacing="0" style="margin-top:12px;"><tr>
                  <td width="36" valign="top" style="padding-right:12px;">
                    <img src="{tw_favicon}" width="28" height="28" style="border-radius:6px;border:1px solid rgba(255,255,255,0.2);" alt="">
                  </td>
                  <td>
                    <a href="{tw_link}" style="font-size:16px;font-weight:800;color:#ffffff;text-decoration:none;">{tw_title}</a>
                    <p style="margin:4px 0 6px;font-size:13px;color:#e0e7ff;line-height:1.5;">{tw_summary}</p>
                    <div style="font-size:11px;color:#c7d2fe;">
                      <strong style="color:#ffffff;">Best For:</strong> {tw_use_case} &bull; 
                      <a href="{tw_link}" style="color:#93c5fd;text-decoration:underline;font-weight:700;">Get Started &rarr;</a>
                    </div>
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
            <table width="100%" cellpadding="0" cellspacing="0" style="background:#fff1f2;border-radius:12px;border:1px solid #fecdd3;border-left:4px solid #e11d48;">
              <tr><td style="padding:16px 20px;">
                <div style="font-size:11px;text-transform:uppercase;letter-spacing:1.5px;color:#be123c;font-weight:800;margin-bottom:6px;">🔥 Strategic Hot Take</div>
                <p style="margin:0;font-size:13px;color:#881337;line-height:1.5;font-weight:500;">{esc(hot_take)}</p>
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
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1.0">
    <title>AI Daily Digest</title>
  </head>
  <body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;">
      <tr><td align="center" style="padding:24px 12px;">
        <table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;">

          <!-- Executive Header -->
          <tr><td style="padding:0 0 16px;text-align:center;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background:#0f172a;border-radius:14px;box-shadow:0 4px 14px rgba(15,23,42,0.15);">
              <tr><td style="padding:24px 24px;text-align:center;">
                <div style="font-size:10px;font-weight:800;letter-spacing:2px;text-transform:uppercase;color:#94a3b8;margin-bottom:6px;">EXECUTIVE INTELLIGENCE REPORT</div>
                <div style="font-size:28px;font-weight:900;color:#ffffff;letter-spacing:-0.5px;">AI Daily Digest</div>
                <div style="margin-top:6px;font-size:12px;color:#cbd5e1;">{subject_date_str} &bull; <span style="color:#38bdf8;font-weight:700;">⚡ 3 min read</span></div>
              </td></tr>
            </table>
          </td></tr>

          <!-- Stats Bar -->
          <tr><td style="padding:0 0 14px;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:10px;border:1px solid #e2e8f0;">
              <tr>
                <td style="padding:10px;text-align:center;width:33%;">
                  <div style="font-size:20px;font-weight:800;color:#4f46e5;">{total_items}</div>
                  <div style="font-size:9px;color:#64748b;text-transform:uppercase;letter-spacing:1px;font-weight:700;">Top Stories</div>
                </td>
                <td style="padding:10px;text-align:center;width:33%;border-left:1px solid #f1f5f9;border-right:1px solid #f1f5f9;">
                  <div style="font-size:20px;font-weight:800;color:#059669;">{num_sections}</div>
                  <div style="font-size:9px;color:#64748b;text-transform:uppercase;letter-spacing:1px;font-weight:700;">Categories</div>
                </td>
                <td style="padding:10px;text-align:center;width:33%;">
                  <div style="font-size:20px;font-weight:800;color:#d97706;">{num_sources}</div>
                  <div style="font-size:9px;color:#64748b;text-transform:uppercase;letter-spacing:1px;font-weight:700;">Verified Sources</div>
                </td>
              </tr>
            </table>
          </td></tr>

          <!-- Executive TL;DR -->
          {exec_block}

          <!-- Story Sections -->
          {''.join(blocks)}

          <!-- Tool of the Day -->
          {tool_block}

          <!-- Hot Take -->
          {hot_block}

          <!-- Footer -->
          <tr><td style="padding:20px 0;text-align:center;">
            <div style="font-size:11px;color:#64748b;line-height:1.7;">
              Curated by AI &bull; Powered by Groq &amp; Open Models<br>
              Every link goes directly to original primary source &bull; Click to verify<br>
              <span style="color:#94a3b8;">Built with &hearts; for staying ahead in AI</span>
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
