"""Generate a beautiful static website from digest data."""
import json
import os
import datetime

# Resolve repo root (parent of the 'digest' directory where this file lives)
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def save_digest_json(sections, tool_of_week, hot_take, date_str, output_dir=None):
    """Save today's digest as JSON for the website."""
    if output_dir is None:
        output_dir = os.path.join(_REPO_ROOT, "docs", "data")
    os.makedirs(output_dir, exist_ok=True)

    today = datetime.date.today().isoformat()

    data = {
        "date": today,
        "date_display": date_str,
        "sections": {},
        "tool_of_day": tool_of_week,
        "hot_take": hot_take,
    }

    for heading, items in sections.items():
        clean_items = []
        for it in items:
            # AI-curated items may not have a 'date' field; default to today
            item_date = it.get("date", today)
            if hasattr(item_date, "isoformat"):
                item_date = item_date.isoformat()
            clean_items.append({
                "title": it.get("title", "Untitled"),
                "link": it.get("link", "#"),
                "summary": it.get("summary", ""),
                "source": it.get("source", "Unknown"),
                "trust": it.get("trust", ""),
                "date": str(item_date),
            })
        data["sections"][heading] = clean_items

    # Save as latest
    with open(os.path.join(output_dir, "latest.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Save to archive
    archive_dir = os.path.join(output_dir, "archive")
    os.makedirs(archive_dir, exist_ok=True)
    with open(os.path.join(archive_dir, f"{today}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Build archive index
    archive_files = sorted(
        [f for f in os.listdir(archive_dir) if f.endswith(".json")],
        reverse=True
    )
    archive_index = [f.replace(".json", "") for f in archive_files[:60]]

    with open(os.path.join(output_dir, "archive_index.json"), "w", encoding="utf-8") as f:
        json.dump(archive_index, f)

    # Cleanup: remove files older than 60 days
    cutoff = (datetime.date.today() - datetime.timedelta(days=60)).isoformat()
    for fname in archive_files:
        date_part = fname.replace(".json", "")
        if date_part < cutoff:
            os.remove(os.path.join(archive_dir, fname))

    return data
