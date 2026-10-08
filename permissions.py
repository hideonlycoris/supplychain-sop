"""权限模型：部门维度 + 项目负责人（个人账号）维度

需求逐条对应：
  1. 现有 admin + 6 个部门账号行为完全不变，不引入新的部门过滤。
  2. 新增「个人账号」，存 Supabase `app_users`，admin 可增删。
  3. 个人账号可见 = 自己负责的项目 ∪ 本部门（department 为空则只有自己负责的）。
  4. 对自己负责的项目：预测 / 实绩 / 备注可写，发货只读（管理员专属）。

本文件是纯函数，不 import streamlit / supabase，方便单独测试。
"""
from __future__ import annotations


def dept_has_data(sku_data: dict, dept: str) -> bool:
    """该部门在这个 SKU 上是否有过 预测 或 实绩 —— 与首页仪表板既有的过滤口径一致。"""
    if not isinstance(sku_data, dict) or not dept:
        return False
    for bucket in ("dept_plans", "actual_sales"):
        for _month, per_dept in (sku_data.get(bucket) or {}).items():
            if isinstance(per_dept, dict) and per_dept.get(dept):
                return True
    return False


def dept_visible_skus(full_db: dict, dept: str) -> set:
    """某部门有数据的全部 SKU（老的仪表板过滤规则）。"""
    if not dept:
        return set()
    return {sku for sku, data in (full_db or {}).items() if dept_has_data(data, dept)}


def restrict_visible_skus(skus, account: dict, dept_rule) -> set:
    """把候选 SKU 列表按账号收窄。

    关键：只对个人账号生效。admin 和 6 个部门账号原样返回 ——
    「不做部门过滤，只限制新账号」。
    """
    skus = set(skus or [])
    if not account or account.get("kind") != "personal":
        return skus

    allowed = set(account.get("owned_skus") or []) & skus
    dept = account.get("department")
    if dept:
        allowed |= set(dept_rule or []) & skus
    return allowed


def can_write_cell(*, is_admin: bool, current_user: str, dept: str, kind: str,
                   is_owner: bool = False) -> bool:
    """某一个格子 `f"{dept}_{kind}"` 当前账号能不能写。

    规则：
      - 发货(shipments)   仅管理员
      - 预测/实绩          管理员 → 任意部门；项目负责人在自己负责的 SKU 内 → 任意部门；
                           其余 → 只有本部门
      - 备注(notes)        按月共享，由调用方单独处理（见 grid_writeback）
    """
    if is_admin:
        return True
    if kind == "发货":
        return False
    if is_owner:
        return True
    return dept == current_user


def account_scope_user(account: dict) -> tuple:
    """返回 (看数用的部门, 是否按全部门汇总)。

    纯项目负责人（没挂部门）在自己项目里要看全部门的数，
    所以 metrics 层面要等同管理员的「汇总所有部门」口径。
    """
    if not account:
        return None, False
    if account.get("is_admin"):
        return None, True
    if account.get("kind") == "personal":
        dept = account.get("department")
        if dept:
            return dept, False
        return None, True
    # 6 个部门账号：用户名本身就是部门
    return account.get("department") or account.get("username"), False


def account_label(account: dict) -> str:
    """登录后右上角的角色说明。"""
    if not account:
        return ""
    if account.get("is_admin"):
        return "管理员"
    if account.get("kind") == "personal":
        dept = account.get("department")
        owned = len(account.get("owned_skus") or [])
        base = f"项目负责人 · 负责 {owned} 个项目"
        if dept:
            base += f" · {dept}"
        return base
    return "部门用户"
