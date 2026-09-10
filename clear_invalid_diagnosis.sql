-- 清除无效的AI诊断结果（risk_level为normal的）
DELETE FROM sku_reports WHERE risk_level = 'normal' OR risk_level IS NULL OR risk_level = '';
