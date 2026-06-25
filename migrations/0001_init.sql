-- ACGTI 统计数据库初始化
-- 3 张表：提交记录、答题明细、用户反馈

CREATE TABLE IF NOT EXISTS submissions (
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  app_version TEXT NOT NULL,
  archetype_code TEXT NOT NULL,
  character_code TEXT NOT NULL,
  ei_score REAL,
  sn_score REAL,
  tf_score REAL,
  jp_score REAL,
  duration_ms INTEGER
);

CREATE TABLE IF NOT EXISTS submission_answers (
  submission_id TEXT NOT NULL,
  question_id TEXT NOT NULL,
  answer_value INTEGER NOT NULL,
  PRIMARY KEY (submission_id, question_id)
);

CREATE TABLE IF NOT EXISTS mbti_feedback (
  id TEXT PRIMARY KEY,
  submission_id TEXT,
  created_at TEXT NOT NULL,
  app_version TEXT NOT NULL,
  self_mbti TEXT NOT NULL,
  confidence INTEGER NOT NULL,
  note TEXT,
  answers_json TEXT,
  answer_count INTEGER
);

-- 索引：加速按时间、原型、角色聚合查询
CREATE INDEX IF NOT EXISTS idx_submissions_created_at ON submissions(created_at);
CREATE INDEX IF NOT EXISTS idx_submissions_archetype ON submissions(archetype_code);
CREATE INDEX IF NOT EXISTS idx_submissions_character ON submissions(character_code);
CREATE INDEX IF NOT EXISTS idx_feedback_submission_id ON mbti_feedback(submission_id);
