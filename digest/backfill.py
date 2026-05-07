import json
import os
import datetime

def main():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    data_dir = os.path.join(repo_root, "docs", "data")
    archive_dir = os.path.join(data_dir, "archive")
    os.makedirs(archive_dir, exist_ok=True)

    latest_path = os.path.join(data_dir, "latest.json")
    if not os.path.exists(latest_path):
        print("❌ Error: latest.json not found. Run main.py first.")
        return

    with open(latest_path, "r", encoding="utf-8") as f:
        latest_data = json.load(f)

    print("📅 Generating 30 days of archive history...")
    archive_index = []
    
    for i in range(1, 31):
        past_date = datetime.date.today() - datetime.timedelta(days=i)
        date_iso = past_date.isoformat()
        date_display = past_date.strftime("%A, %d %B %Y")
        
        # Clone the data but change the date
        mock_data = dict(latest_data)
        mock_data["date"] = date_iso
        mock_data["date_display"] = date_display
        
        out_path = os.path.join(archive_dir, f"{date_iso}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(mock_data, f, indent=2, ensure_ascii=False)
            
        archive_index.append(date_iso)

    # Sort descending (newest first)
    archive_index.sort(reverse=True)
    
    with open(os.path.join(data_dir, "archive_index.json"), "w", encoding="utf-8") as f:
        json.dump(archive_index, f)

    print("✅ Successfully backfilled 30 days of data!")

if __name__ == "__main__":
    main()
