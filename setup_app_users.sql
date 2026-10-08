-- 个人账号 / 项目负责人表
-- 在 Supabase SQL Editor 里执行一次即可，已存在则跳过（幂等）。
--
-- 与 app.py 里硬编码的 USER_CREDENTIALS（admin + 6 个部门账号）并存：
-- 老账号不迁移、不受影响，这个表只装「新加的个人账号」。
--
-- 字段说明：
--   department   NULL = 纯项目负责人（只看得见自己负责的项目）
--                非空 = 同时保留该部门的权限（叠加）
--   owned_skus   该账号负责的项目（SKU 名）JSON 数组，例 ["USWBLM0100260-割草机"]
--   salt/password_hash  PBKDF2-HMAC-SHA256(10万次) 加盐哈希，不存明文

CREATE TABLE IF NOT EXISTS public.app_users (
    username      TEXT PRIMARY KEY,
    salt          TEXT        NOT NULL,
    password_hash TEXT        NOT NULL,
    department    TEXT,
    owned_skus    JSONB       NOT NULL DEFAULT '[]'::jsonb,
    is_active     BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE  public.app_users            IS 'S&OP 系统个人账号（项目负责人）';
COMMENT ON COLUMN public.app_users.department IS 'NULL=纯项目负责人；非空=叠加该部门权限';
COMMENT ON COLUMN public.app_users.owned_skus IS '负责的项目（SKU 名）JSON 数组';

CREATE INDEX IF NOT EXISTS idx_app_users_department ON public.app_users (department);

-- 关于 RLS：本项目其余表（sku_data / operation_logs / ai_reports / ai_tasks / ai_memory）
-- 都没有开 RLS，本表保持一致 —— 否则用 publishable key 的应用读不到自己刚写的账号，
-- 登录页会直接哑掉。真正的堵漏是整库开 RLS + 换 service_role key，那是独立的一轮改造。
-- 密码侧的兜底：加盐 + PBKDF2 10 万次迭代，账号密码要求至少 6 位。

-- 校验：应返回 0 行
-- SELECT username, department, owned_skus FROM public.app_users;
