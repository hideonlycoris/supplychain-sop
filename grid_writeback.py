"""AgGrid 编辑结果写回 working_db

计划录入表里的列名形如 `一部_发货` / `一部_预测` / `一部_实绩`，
分别落到 working_db 的 shipments / dept_plans / actual_sales。

这个函数是纯函数（不碰数据库、不碰 Streamlit），方便单独测试 ——
之前就是因为在保存分支里漏了 预测/实绩/备注，导致「计划录入改了
实绩、供需分析图还是 0」这种静默数据丢失。
"""
import pandas as pd

# 列后缀 -> working_db 中的存储位置
COL_BUCKETS = {"发货": "shipments", "预测": "dept_plans", "实绩": "actual_sales"}


def _to_int(raw):
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return 0


def apply_grid_edits(working_db: dict, edited_df, is_admin: bool, current_user: str) -> int:
    """把 AgGrid 返回的编辑结果写进 working_db，返回被写入的单元格数。

    权限规则：
      - 发货(shipments)   仅管理员
      - 预测/实绩          管理员或本部门
      - 备注(notes)        按月共享，所有角色可写（值未变时等同于原样写回）
    """
    if edited_df is None or len(edited_df) == 0:
        return 0

    written = 0
    for _, row in edited_df.iterrows():
        m = row["月份"]
        for col in edited_df.columns:
            if col in ("月份", "备注") or "_" not in col:
                continue
            dept, _sep, kind = col.partition("_")
            bucket = COL_BUCKETS.get(kind)
            if bucket is None:
                continue
            # 权限：发货仅管理员可改；预测/实绩 允许管理员或本部门
            if kind == "发货" and not is_admin:
                continue
            if not is_admin and dept != current_user:
                continue
            working_db.setdefault(bucket, {}).setdefault(m, {})[dept] = _to_int(row[col])
            written += 1

        if "备注" in edited_df.columns:
            note = row.get("备注", "")
            working_db.setdefault("notes", {})[m] = "" if pd.isna(note) else str(note)
            written += 1

    return written
