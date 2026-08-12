"""
Data migration script: import local file data into Supabase
"""
import json
import os
import sys
from datetime import datetime

try:
    from supabase import create_client
except ImportError:
    print("Please install supabase: pip install supabase")
    sys.exit(1)

SUPABASE_URL = "https://qdkcbsunyustkxkcrnvc.supabase.co"
SUPABASE_KEY = "sb_publishable_-IoU1wPbpDBXSny2Em6mmQ_zkMiz0Dd"


def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("[ERROR] Please set SUPABASE_URL and SUPABASE_KEY")
        return

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("[OK] Supabase connected")

    # 1. Migrate SKU data
    db_files = ["sop_v11_db.json", "sop_v9_db.json", "sop_v6_pro_db.json"]
    full_db = {}
    for f in db_files:
        if os.path.exists(f):
            try:
                with open(f, 'r', encoding='utf-8') as fp:
                    full_db.update(json.load(fp))
                print(f"  [LOAD] {f}")
            except Exception as e:
                print(f"  [WARN] Failed to load {f}: {e}")

    if full_db:
        rows = []
        for sku_name, data in full_db.items():
            rows.append({
                "sku_name": sku_name,
                "data": json.dumps(data, ensure_ascii=False),
                "updated_at": datetime.now().isoformat()
            })
        batch_size = 50
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            supabase.table("sku_data").upsert(batch).execute()
        print(f"  [OK] Imported {len(rows)} SKUs")

    # 2. Migrate operation logs
    log_file = "operation_log.csv"
    if os.path.exists(log_file):
        import csv
        rows = []
        with open(log_file, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append({
                    "timestamp": row.get("时间", datetime.now().isoformat()),
                    "user": row.get("用户", "unknown"),
                    "sku": row.get("SKU", ""),
                    "action": row.get("操作内容", "")
                })
        if rows:
            batch_size = 100
            for i in range(0, len(rows), batch_size):
                batch = rows[i:i + batch_size]
                supabase.table("operation_logs").insert(batch).execute()
            print(f"  [OK] Imported {len(rows)} log entries")

    # 3. Migrate AI reports
    report_dir = "ai_reports"
    if os.path.exists(report_dir):
        count = 0
        for fname in os.listdir(report_dir):
            if fname.endswith('.txt'):
                sku_name = fname.replace('.txt', '')
                with open(os.path.join(report_dir, fname), 'r', encoding='utf-8') as f:
                    content = f.read()
                supabase.table("ai_reports").upsert({
                    "sku_name": sku_name,
                    "content": content,
                    "updated_at": datetime.now().isoformat()
                }).execute()
                count += 1
        if count:
            print(f"  [OK] Imported {count} AI reports")

    # 4. Migrate AI tasks
    tasks_dir = "ai_tasks"
    if os.path.exists(tasks_dir):
        count = 0
        for fname in os.listdir(tasks_dir):
            if fname.endswith('_tasks.json'):
                sku_name = fname.replace('_tasks.json', '')
                with open(os.path.join(tasks_dir, fname), 'r', encoding='utf-8') as f:
                    tasks = json.load(f)
                supabase.table("ai_tasks").upsert({
                    "sku_name": sku_name,
                    "tasks": json.dumps(tasks, ensure_ascii=False),
                    "updated_at": datetime.now().isoformat()
                }).execute()
                count += 1
        if count:
            print(f"  [OK] Imported {count} task lists")

    # 5. Migrate AI memory
    memory_file = "ai_memory.txt"
    if os.path.exists(memory_file):
        with open(memory_file, 'r', encoding='utf-8') as f:
            content = f.read()
        if content.strip():
            supabase.table("ai_memory").upsert({
                "id": 1,
                "content": content,
                "updated_at": datetime.now().isoformat()
            }).execute()
            print(f"  [OK] Imported AI memory")

    print("\n[DONE] Migration complete!")


if __name__ == "__main__":
    main()
