-- 0002_rate_limit.sql — 简易限流表（内存级，定期清理）
-- 仅用于 API 层分钟级限流，不存储业务数据

CREATE TABLE IF NOT EXISTS _rate_limit (
  k TEXT PRIMARY KEY,
  cnt INTEGER NOT NULL DEFAULT 1,
  exp INTEGER NOT NULL
);

-- 清理过期记录的索引
CREATE INDEX IF NOT EXISTS idx_rate_limit_exp ON _rate_limit(exp);
