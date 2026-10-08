"""个人账号存取（Supabase 表 `app_users`）

与 app.py 里硬编码的 USER_CREDENTIALS（admin + 6 个部门账号）并存，
登录时取两者并集 —— 老账号一行都不用改，零迁移风险。

密码用 加盐 PBKDF2-HMAC-SHA256（10 万次）存储，不存明文、不用可彩虹表攻击的裸 SHA-256。

注意：本仓库是公开的、Supabase 用的是 publishable key，且这些表都没开 RLS，
所以 app_users 表对拿到 key 的人是可读可写的。加盐慢哈希把「读到哈希 → 爆破出密码」
的成本拉高了几个数量级，但真正堵死要等 RLS 那件事（另行处理）。
"""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

TABLE = "app_users"
PBKDF2_ITERATIONS = 100_000

# 表还没建 / 连不上时只提示一次，不要每次 rerun 刷屏
_table_state = {"ok": None, "msg": ""}


# ---------------------------------------------------------------- 密码
def hash_password(password: str, salt: str | None = None) -> tuple:
    """返回 (salt_hex, hash_hex)。"""
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ITERATIONS
    )
    return salt, dk.hex()


def verify_password(password: str, salt: str, expected: str) -> bool:
    if not password or not salt or not expected:
        return False
    _, got = hash_password(password, salt)
    # 定长比较，避免时序侧信道
    return secrets.compare_digest(got, expected)


# ---------------------------------------------------------------- 行 <-> 账号
def row_to_account(row: dict) -> dict:
    owned = row.get("owned_skus") or []
    if isinstance(owned, str):
        try:
            owned = json.loads(owned)
        except (TypeError, ValueError):
            owned = []
    dept = row.get("department") or None
    if dept in ("", "（不挂部门）"):
        dept = None
    return {
        "username": row.get("username", ""),
        "kind": "personal",
        "department": dept,
        "owned_skus": [s for s in owned if s],
        "is_admin": False,
        "salt": row.get("salt", ""),
        "password_hash": row.get("password_hash", ""),
        "is_active": bool(row.get("is_active", True)),
        "updated_at": row.get("updated_at", ""),
    }


def _mark_table_missing(err) -> None:
    text = str(err).lower()
    missing = (
        "does not exist" in text
        or "42p01" in text
        or "schema cache" in text
        or "could not find the table" in text
    )
    if missing and _table_state["ok"] is not False:
        _table_state["ok"] = False
        _table_state["msg"] = (
            f"个人账号表 `{TABLE}` 还没创建 —— 请在 Supabase SQL Editor 执行 "
            "`setup_app_users.sql` 一次。"
        )
        logger.warning(_table_state["msg"])


def table_issue() -> str:
    """表不可用时给 admin 看的一句话说明；正常时返回空串。"""
    return _table_state["msg"] if _table_state["ok"] is False else ""


def setup_sql() -> str:
    """建表 SQL 原文 —— 表没建时直接在侧边栏贴给 admin 复制，省得去仓库里翻文件。"""
    path = Path(__file__).with_name("setup_app_users.sql")
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return "-- 找不到 setup_app_users.sql，请从仓库根目录取"


def reset_state() -> None:
    """建表后手动清一次状态。"""
    _table_state["ok"] = None
    _table_state["msg"] = ""


# ---------------------------------------------------------------- 查询
def list_personal_users(client) -> list:
    """全部个人账号；表不存在/查询失败时返回 []（登录页因此仍能用老账号）。"""
    try:
        result = client.table(TABLE).select("*").execute()
        rows = result.data or []
    except Exception as e:  # noqa: BLE001 - 表缺失与网络错误都要退化成「没有个人账号」
        _mark_table_missing(e)
        if _table_state["ok"] is not False:
            logger.error(f"读取 {TABLE} 失败: {e}")
        return []
    _table_state["ok"] = True
    accounts = [row_to_account(r) for r in rows]
    return [a for a in accounts if a["username"] and a["is_active"]]


def find_user(client, username: str):
    for acc in list_personal_users(client):
        if acc["username"] == username:
            return acc
    return None


def authenticate(client, username: str, password: str):
    """成功返回 account 字典，失败返回 None。"""
    for acc in list_personal_users(client):
        if acc["username"] != username:
            continue
        if verify_password(password, acc["salt"], acc["password_hash"]):
            return acc
        return None
    return None


# ---------------------------------------------------------------- 写入
def upsert_user(client, *, username: str, password: str, department=None,
                owned_skus=None, is_active: bool = True) -> dict:
    """新建或更新（用户名已存在则覆盖，且 password 为空时保留原密码）。"""
    username = (username or "").strip()
    if not username:
        raise ValueError("用户名不能为空")
    if len(password or "") < 6 and not find_user(client, username):
        raise ValueError("密码至少 6 位（表是可被 key 读到的，太短的密码挡不住爆破）")

    owned = [s for s in (owned_skus or []) if s]
    if isinstance(department, str) and department in ("", "（不挂部门）"):
        department = None

    existing = find_user(client, username)
    row = {
        "username": username,
        "department": department,
        "owned_skus": json.dumps(owned, ensure_ascii=False),
        "is_active": is_active,
        "updated_at": datetime.now().isoformat(),
    }
    if password:
        salt, digest = hash_password(password)
        row["salt"] = salt
        row["password_hash"] = digest
    elif existing:
        row["salt"] = existing["salt"]
        row["password_hash"] = existing["password_hash"]
    else:
        raise ValueError("新账号必须设置密码")

    if not existing:
        row["created_at"] = datetime.now().isoformat()

    client.table(TABLE).upsert(row, on_conflict="username").execute()
    return row_to_account(row)


def delete_user(client, username: str) -> bool:
    try:
        client.table(TABLE).delete().eq("username", username).execute()
        return True
    except Exception as e:  # noqa: BLE001
        logger.error(f"删除账号 {username} 失败: {e}")
        return False


