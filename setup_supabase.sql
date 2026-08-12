-- ============================================================
-- S&OP 决策系统 V12 - Supabase 数据库建表脚本
-- 请在 Supabase Dashboard -> SQL Editor 中执行此脚本
-- ============================================================

-- 1. SKU 主数据表（替换 sop_v11_db.json）
CREATE TABLE IF NOT EXISTS sku_data (
    sku_name TEXT PRIMARY KEY,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. 操作日志表（替换 operation_log.csv）
CREATE TABLE IF NOT EXISTS operation_logs (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    "user" TEXT NOT NULL,
    sku TEXT NOT NULL,
    action TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. AI 诊断报告表（替换 ai_reports/ 目录）
CREATE TABLE IF NOT EXISTS ai_reports (
    sku_name TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. AI 任务清单表（替换 ai_tasks/ 目录）
CREATE TABLE IF NOT EXISTS ai_tasks (
    sku_name TEXT PRIMARY KEY,
    tasks JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. AI 专家规约表（替换 ai_memory.txt）
CREATE TABLE IF NOT EXISTS ai_memory (
    id INTEGER PRIMARY KEY DEFAULT 1,
    content TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 索引：提升日志查询性能
CREATE INDEX IF NOT EXISTS idx_operation_logs_sku ON operation_logs(sku);
CREATE INDEX IF NOT EXISTS idx_operation_logs_user ON operation_logs("user");
CREATE INDEX IF NOT EXISTS idx_operation_logs_timestamp ON operation_logs(timestamp DESC);

-- 插入默认 AI 规约（可选）
INSERT INTO ai_memory (id, content) VALUES (1, '')
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- 完成！接下来运行 migrate_data.py 导入现有数据
-- ============================================================
