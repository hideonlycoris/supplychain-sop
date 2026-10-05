"""grid_writeback.apply_grid_edits 的回归测试

覆盖的真实故障：在「计划录入与备注」填了 2026-10 一部_实绩=193，
保存后「供需分析图」的实际销量仍是 0 —— 因为保存分支只写了 shipments。

运行: python test_grid_writeback.py
"""
import pandas as pd

from grid_writeback import apply_grid_edits


def _grid(rows):
    return pd.DataFrame(rows)


def test_actual_sales_lands_in_actual_sales_bucket():
    """核心回归：实绩必须写进 actual_sales，供需分析图才看得到"""
    db = {"shipments": {}, "dept_plans": {}, "actual_sales": {}, "notes": {}}
    grid = _grid([
        {"月份": "2026-10", "备注": "", "一部_发货": 0, "一部_预测": 400, "一部_实绩": 193,
         "四部_发货": 0, "四部_预测": 0, "四部_实绩": 0},
        {"月份": "2026-11", "备注": "", "一部_发货": 0, "一部_预测": 400, "一部_实绩": 0,
         "四部_发货": 0, "四部_预测": 0, "四部_实绩": 0},
    ])

    apply_grid_edits(db, grid, is_admin=True, current_user="admin")

    assert db["actual_sales"]["2026-10"]["一部"] == 193, db["actual_sales"]
    assert db["dept_plans"]["2026-10"]["一部"] == 400
    assert db["shipments"]["2026-10"]["一部"] == 0
    # 供需分析图的「实际销量」= 各 view_dept 的 actual_sales 之和
    actual_total = sum(db["actual_sales"]["2026-10"].values())
    assert actual_total == 193, f"实际销量应为 193，实际 {actual_total}"
    print("OK  实绩 193 已写入 actual_sales，供需分析图实际销量 = 193")


def test_notes_are_written():
    db = {"shipments": {}, "dept_plans": {}, "actual_sales": {}, "notes": {}}
    grid = _grid([{"月份": "2026-09", "备注": "9月第三周：7成完成率", "一部_实绩": 0}])
    apply_grid_edits(db, grid, is_admin=True, current_user="admin")
    assert db["notes"]["2026-09"] == "9月第三周：7成完成率", db["notes"]
    print("OK  备注已写入 notes")


def test_dept_user_cannot_write_shipment_but_can_write_own_actual():
    db = {"shipments": {}, "dept_plans": {}, "actual_sales": {}, "notes": {}}
    grid = _grid([{
        "月份": "2026-10", "备注": "x",
        "一部_发货": 111, "一部_预测": 222, "一部_实绩": 193,
        "五部_发货": 999, "五部_预测": 888, "五部_实绩": 777,
    }])

    apply_grid_edits(db, grid, is_admin=False, current_user="一部")

    # 自己的预测/实绩能写
    assert db["actual_sales"]["2026-10"]["一部"] == 193
    assert db["dept_plans"]["2026-10"]["一部"] == 222
    # 任何角色都不能写发货（发货仅管理员）
    assert "一部" not in db["shipments"].get("2026-10", {}), db["shipments"]
    # 别的部门完全不能写
    assert "五部" not in db["actual_sales"].get("2026-10", {}), db["actual_sales"]
    assert "五部" not in db["dept_plans"].get("2026-10", {}), db["dept_plans"]
    print("OK  权限：部门用户只写本部门预测/实绩，发货与他部门被拦截")


def test_non_numeric_and_empty_values_do_not_crash():
    db = {"shipments": {}, "dept_plans": {}, "actual_sales": {}, "notes": {}}
    grid = _grid([{"月份": "2026-10", "备注": None, "一部_实绩": "", "一部_预测": None}])
    apply_grid_edits(db, grid, is_admin=True, current_user="admin")
    assert db["actual_sales"]["2026-10"]["一部"] == 0
    assert db["dept_plans"]["2026-10"]["一部"] == 0
    assert db["notes"]["2026-10"] == "", repr(db["notes"]["2026-10"])
    print("OK  空值/None 不崩，落 0；备注 None 落空串")


def test_ignored_columns():
    db = {"shipments": {}, "dept_plans": {}, "actual_sales": {}, "notes": {}}
    grid = _grid([{"月份": "2026-10", "备注": "", "一部_到货": 5, "一部_库存": 99}])
    n = apply_grid_edits(db, grid, is_admin=True, current_user="admin")
    assert db["actual_sales"] == {} and db["dept_plans"] == {} and db["shipments"] == {}
    print(f"OK  非录入列（到货/库存）被跳过，写入数={n}")


def test_empty_df_is_noop():
    db = {"shipments": {}}
    assert apply_grid_edits(db, None, True, "admin") == 0
    assert apply_grid_edits(db, _grid([]), True, "admin") == 0
    print("OK  None / 空表 不产生副作用")


if __name__ == "__main__":
    test_actual_sales_lands_in_actual_sales_bucket()
    test_notes_are_written()
    test_dept_user_cannot_write_shipment_but_can_write_own_actual()
    test_non_numeric_and_empty_values_do_not_crash()
    test_ignored_columns()
    test_empty_df_is_noop()
    print("\n全部通过 ✅")
