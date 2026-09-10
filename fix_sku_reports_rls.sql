-- 修复 sku_reports 表的 RLS 策略，允许匿名用户插入和更新

-- 删除旧策略
DROP POLICY IF EXISTS "Allow authenticated insert" ON sku_reports;
DROP POLICY IF EXISTS "Allow authenticated update" ON sku_reports;

-- 创建新策略：允许所有用户插入和更新
CREATE POLICY "Allow all insert" ON sku_reports FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow all update" ON sku_reports FOR UPDATE USING (true);
