-- 创建 sku_reports 表（存储AI诊断结果）
CREATE TABLE IF NOT EXISTS sku_reports (
  id SERIAL PRIMARY KEY,
  sku_name TEXT NOT NULL,
  department TEXT,
  report_type TEXT DEFAULT 'ai_diagnosis',
  content TEXT,
  risk_level TEXT,  -- 'high' / 'medium' / 'low' / 'normal'
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_sku_reports_sku_name ON sku_reports(sku_name);
CREATE INDEX IF NOT EXISTS idx_sku_reports_department ON sku_reports(department);

-- 启用 RLS
ALTER TABLE sku_reports ENABLE ROW LEVEL SECURITY;

-- 创建策略：所有用户可读， authenticated 用户可写
CREATE POLICY "Allow all read" ON sku_reports FOR SELECT USING (true);
CREATE POLICY "Allow authenticated insert" ON sku_reports FOR INSERT WITH CHECK (auth.role() = 'authenticated');
CREATE POLICY "Allow authenticated update" ON sku_reports FOR UPDATE USING (auth.role() = 'authenticated');
