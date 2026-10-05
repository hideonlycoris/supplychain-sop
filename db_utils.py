"""数据库连接辅助：错误定位与重试

报错时带上具体域名，避免 socket.gaierror 只有一句
"Name or service not known" 而看不出是哪个主机解析失败。
"""
import socket
import time
import logging

import streamlit as st

logger = logging.getLogger(__name__)


def supabase_host() -> str:
    """取当前配置的数据库域名（用于报错定位）"""
    try:
        raw = str(st.secrets.get("SUPABASE_URL", "")).strip()
    except Exception:
        raw = ""
    if not raw:
        return "(未配置 SUPABASE_URL)"
    return raw.split("//")[-1].split("/")[0].strip()


def describe_db_error(e: Exception) -> str:
    """把底层异常翻译成能看出该查哪里的提示"""
    host = supabase_host()
    err = str(e)
    if isinstance(e, socket.gaierror) or any(
        s in err for s in ("Name or service not known", "getaddrinfo failed",
                           "nodename nor servname", "Temporary failure in name resolution")
    ):
        return (
            f"**数据库域名解析失败:** `{host}`\n\n"
            "常见原因（按可能性排序）：\n"
            "1. Supabase 项目已被暂停或删除 → 打开 [Supabase 控制台](https://supabase.com/dashboard) 确认项目状态\n"
            "2. Streamlit 密钥里的 `SUPABASE_URL` 被改动或写错 → App → Settings → Secrets 检查\n"
            "3. 运行环境网络/代理故障 → 稍后点「刷新数据」重试"
        )
    if isinstance(e, socket.timeout) or "timed out" in err:
        return f"**连接数据库超时:** `{host}`，请稍后点「刷新数据」重试。"
    if "Invalid API key" in err or "401" in err:
        return f"**密钥无效 (401):** 检查 Streamlit Secrets 中的 `SUPABASE_KEY` 是否与 `{host}` 匹配。"
    if "relation" in err and "does not exist" in err:
        return "**数据表不存在:** 请在 Supabase SQL Editor 执行仓库里的 `setup_supabase.sql`。"
    return f"**数据库请求失败:** `{host}` — {err}"


def db_retry(fn, tries: int = 3, delay: float = 0.6):
    """网络/数据库调用重试（DNS 抖动通常重试即恢复）"""
    last = None
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            last = e
            if i == tries - 1:
                raise
            logger.warning(f"数据库调用失败，第 {i + 1}/{tries} 次重试: {e}")
            time.sleep(delay * (i + 1))
    raise last
