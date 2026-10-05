"""全量备份 Supabase sku_data 到本地 db_backups/

为什么需要：Supabase 免费项目闲置 1 周会被暂停，且免费版没有自动备份。
本地留一份全量快照，云端出问题时不至于两个多月的改动全丢。

用法:
    python backup_db.py

产物: db_backups/full_dump_YYYYMMDD_HHMMSS.json   格式 {sku_name: data}
（与历史快照 sop_*.json 的结构一致，可直接比对）
"""
import json
import os
import sys
from datetime import datetime

try:
    from supabase import create_client
except ImportError:
    print("请先安装 supabase: pip install supabase")
    sys.exit(1)

SUPABASE_URL = "https://qdkcbsunyustkxkcrnvc.supabase.co"
SUPABASE_KEY = "sb_publishable_-IoU1wPbpDBXSny2Em6mmQ_zkMiz0Dd"

BACKUP_DIR = "db_backups"


def main():
    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    result = client.table("sku_data").select("*").execute()

    full_db = {}
    for row in result.data:
        data = row["data"]
        if isinstance(data, str):
            data = json.loads(data)
        full_db[row["sku_name"]] = data

    if not full_db:
        print("[ERROR] 查询到 0 条记录，不写空备份（避免覆盖可用快照）")
        sys.exit(1)

    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(BACKUP_DIR, f"full_dump_{ts}.json")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(full_db, f, ensure_ascii=False, indent=1)

    size_kb = os.path.getsize(path) / 1024
    print(f"[OK] 备份 {len(full_db)} 个 SKU -> {path} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
