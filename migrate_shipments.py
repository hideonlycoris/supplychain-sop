"""
发货数据迁移脚本
将单一发货数值按各部门计划占比自动分配到各部门
"""
import json
import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

DEPTS = ["一部", "四部", "五部", "珍组", "琪组", "tt"]


def migrate_shipments():
    """迁移发货数据到分部门结构"""
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    # 获取所有SKU数据
    result = supabase.table("sku_data").select("*").execute()

    for row in result.data:
        sku_name = row.get("sku_name", "")
        data = row.get("data", {})

        dept_plans = data.get("dept_plans", {})
        shipments = data.get("shipments", {})

        # 检查是否需要迁移（旧格式是单一数值）
        needs_migration = False
        for month, value in shipments.items():
            if isinstance(value, (int, float)):
                needs_migration = True
                break

        if not needs_migration:
            print(f"[SKIP] {sku_name} 已经是新格式")
            continue

        print(f"[MIGRATE] {sku_name} 开始迁移...")

        # 按比例分配发货数据
        new_shipments = {}
        for month, total_shipment in shipments.items():
            if not isinstance(total_shipment, (int, float)):
                # 已经是新格式，跳过
                new_shipments[month] = total_shipment
                continue

            # 获取该月各部门计划总量
            month_plans = dept_plans.get(month, {})
            total_plan = sum(month_plans.values())

            if total_plan == 0:
                # 没有计划数据，平均分配
                per_dept = total_shipment / len(DEPTS) if len(DEPTS) > 0 else 0
                new_shipments[month] = {dept: int(per_dept) for dept in DEPTS}
            else:
                # 按计划占比分配
                new_shipments[month] = {}
                for dept in DEPTS:
                    dept_plan = month_plans.get(dept, 0)
                    ratio = dept_plan / total_plan if total_plan > 0 else 0
                    new_shipments[month][dept] = int(total_shipment * ratio)

            print(f"  {month}: {total_shipment} -> {new_shipments[month]}")

        # 更新数据
        data["shipments"] = new_shipments
        supabase.table("sku_data").update({"data": data}).eq("sku_name", sku_name).execute()
        print(f"[DONE] {sku_name} 迁移完成")

    print("\n迁移完成！")


if __name__ == "__main__":
    migrate_shipments()
