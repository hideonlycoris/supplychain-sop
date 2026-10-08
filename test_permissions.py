"""permissions + 项目负责人写回权限 的单元测试

运行: python -X utf8 test_permissions.py
"""
import pandas as pd

from grid_writeback import apply_grid_edits
from permissions import (account_label, account_scope_user, can_write_cell,
                         dept_has_data, dept_visible_skus,
                         restrict_visible_skus)


def _db():
    return {"shipments": {}, "dept_plans": {}, "actual_sales": {}, "notes": {}}


def test_dept_has_data_matches_dashboard_rule():
    """部门可见口径必须和首页仪表板一致：只看 预测/实绩，不看发货"""
    sku = {"dept_plans": {"2026-10": {"五部": 10}},
           "actual_sales": {"2026-10": {"五部": 0}},
           "shipments": {"2026-10": {"五部": 999}}}
    assert dept_has_data(sku, "五部") is True
    assert dept_has_data(sku, "一部") is False
    # 只有发货、没有预测/实绩 → 不算有数据
    only_ship = {"shipments": {"2026-10": {"tt": 5}}, "dept_plans": {}, "actual_sales": {}}
    assert dept_has_data(only_ship, "tt") is False
    print("OK  部门口径 = 预测/实绩 > 0（与仪表板一致，不含发货）")


def test_legacy_accounts_are_untouched_by_restrict():
    """不做部门过滤、只限制新账号：老账号 restrict 后必须原样返回"""
    skus = ["A-割草机", "B-发电机", "C-清洗机"]
    legacy = {"username": "一部", "kind": "legacy", "department": "一部",
              "owned_skus": [], "is_admin": False}
    admin = {"username": "admin", "kind": "legacy", "department": None,
             "owned_skus": [], "is_admin": True}
    assert restrict_visible_skus(skus, legacy, {"A-割草机"}) == set(skus)
    assert restrict_visible_skus(skus, admin, set()) == set(skus)
    print("OK  admin / 6 个部门账号的可见范围完全不变")


def test_pure_owner_sees_only_owned_project():
    """部门留空的项目负责人 → 只能看见自己负责的那个项目"""
    skus = {"A-割草机": {}, "B-发电机": {}, "C-清洗机": {}}
    owner = {"username": "张三", "kind": "personal", "department": None,
             "owned_skus": ["A-割草机"], "is_admin": False}
    got = restrict_visible_skus(skus.keys(), owner, dept_visible_skus(skus, "张三"))
    assert got == {"A-割草机"}, got
    print("OK  纯项目负责人 只看得见自己负责的 1 个项目")


def test_owner_with_dept_sees_union():
    """叠加：挂了部门的项目负责人 = 自己负责的 ∪ 本部门有数据的"""
    skus = {
        "A-割草机": {"dept_plans": {"2026-10": {"五部": 10}}},
        "B-发电机": {"dept_plans": {"2026-10": {"五部": 10}}},
        "C-清洗机": {"actual_sales": {"2026-10": {"一部": 7}}},
    }
    owner = {"username": "张三", "kind": "personal", "department": "五部",
             "owned_skus": ["C-清洗机"], "is_admin": False}
    dept_rule = dept_visible_skus(skus, "五部")
    got = restrict_visible_skus(skus.keys(), owner, dept_rule)
    # 负责 C（即使五部在 C 上没数据）+ 五部有数据的 A、B
    assert got == {"A-割草机", "B-发电机", "C-清洗机"}, got
    print("OK  挂部门的项目负责人 = 本部门 ∪ 自己负责的项目")


def test_can_write_rules():
    # 发货只有管理员
    assert can_write_cell(is_admin=False, current_user="一部", dept="一部", kind="发货") is False
    assert can_write_cell(is_admin=True, current_user="admin", dept="一部", kind="发货") is True
    # 部门用户只能写本部门预测/实绩
    assert can_write_cell(is_admin=False, current_user="一部", dept="一部", kind="预测") is True
    assert can_write_cell(is_admin=False, current_user="一部", dept="五部", kind="实绩") is False
    # 项目负责人在自己项目里：预测/实绩全部门可写，发货仍然只读
    assert can_write_cell(is_admin=False, current_user="张三", dept="五部",
                          kind="预测", is_owner=True) is True
    assert can_write_cell(is_admin=False, current_user="张三", dept="一部",
                          kind="实绩", is_owner=True) is True
    assert can_write_cell(is_admin=False, current_user="张三", dept="一部",
                          kind="发货", is_owner=True) is False
    print("OK  发货仅管理员；部门用户限本部门；负责人在本项目内预测/实绩全开")


def test_owner_writes_all_depts_but_not_shipment():
    """端到端：负责人在自己的 SKU 里改全部门预测/实绩，发货被拦"""
    db = _db()
    grid = pd.DataFrame([{
        "月份": "2026-10", "备注": "负责人备注",
        "一部_发货": 111, "一部_预测": 100, "一部_实绩": 90,
        "五部_发货": 222, "五部_预测": 200, "五部_实绩": 180,
    }])
    n = apply_grid_edits(db, grid, is_admin=False, current_user="张三",
                         sku_name="A-割草机", owned_skus=["A-割草机"])
    assert db["dept_plans"]["2026-10"] == {"一部": 100, "五部": 200}
    assert db["actual_sales"]["2026-10"] == {"一部": 90, "五部": 180}
    assert db["shipments"] == {}, db["shipments"]
    assert db["notes"]["2026-10"] == "负责人备注"
    assert n == 5, n
    print("OK  负责人在自己项目里写全部门 预测/实绩/备注，发货被拦")


def test_same_person_without_ownership_is_blocked():
    """同一个人，但打开的不是他负责的 SKU → 退回成「谁都不是」，全部门都写不了"""
    db = _db()
    grid = pd.DataFrame([{
        "月份": "2026-10", "备注": "",
        "一部_预测": 100, "五部_预测": 200,
    }])
    apply_grid_edits(db, grid, is_admin=False, current_user="张三",
                     sku_name="B-发电机", owned_skus=["A-割草机"])
    assert db["dept_plans"] == {}, db["dept_plans"]
    print("OK  非负责项目里，个人账号一个格子也写不进去")


def test_account_scope_user():
    admin, all_ = account_scope_user({"username": "admin", "is_admin": True, "kind": "legacy"})
    assert (admin, all_) == (None, True)
    d, all2 = account_scope_user({"username": "一部", "is_admin": False, "kind": "legacy",
                                  "department": "一部"})
    assert (d, all2) == ("一部", False)
    pure, all3 = account_scope_user({"username": "张三", "kind": "personal",
                                     "department": None, "is_admin": False})
    assert (pure, all3) == (None, True)
    withdept, all4 = account_scope_user({"username": "张三", "kind": "personal",
                                         "department": "五部", "is_admin": False})
    assert (withdept, all4) == ("五部", False)
    print("OK  account_scope_user：纯负责人为全口径，挂部门的按部门取数")


def test_account_label():
    assert account_label({"is_admin": True, "kind": "legacy"}) == "管理员"
    assert account_label({"username": "一部", "kind": "legacy", "department": "一部"}) == "部门用户"
    lbl = account_label({"username": "张三", "kind": "personal", "department": None,
                         "owned_skus": ["A", "B"]})
    assert "项目负责人" in lbl and "2 个项目" in lbl, lbl
    print(f"OK  身份文案: {lbl}")


if __name__ == "__main__":
    test_dept_has_data_matches_dashboard_rule()
    test_legacy_accounts_are_untouched_by_restrict()
    test_pure_owner_sees_only_owned_project()
    test_owner_with_dept_sees_union()
    test_can_write_rules()
    test_owner_writes_all_depts_but_not_shipment()
    test_same_person_without_ownership_is_blocked()
    test_account_scope_user()
    test_account_label()
    print("\n全部通过 ✅")
