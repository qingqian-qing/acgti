-- ACGTI 排行榜快照表
-- 预计算结果存储，由 Cron Worker 定时更新
-- 避免每次请求都对大表做 GROUP BY 聚合

CREATE TABLE IF NOT EXISTS stats_snapshot (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  cached_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 使用示例：
-- key = 'overview'           -> { totalSubmissions, todaySubmissions, last24hSubmissions }
-- key = 'archetypes'         -> [ { archetype_code, cnt }, ... ]
-- key = 'characters'         -> [ { character_code, cnt }, ... ]

-- 索引加速快照查询
CREATE INDEX IF NOT EXISTS idx_stats_snapshot_key ON stats_snapshot(key);
CREATE INDEX IF NOT EXISTS idx_stats_snapshot_updated_at ON stats_snapshot(updated_at);
