-- 0005_restore_submission_answers.sql
-- 补齐逐题明细表，兼容按题查询与排障

CREATE TABLE IF NOT EXISTS submission_answers (
  submission_id TEXT NOT NULL,
  question_id TEXT NOT NULL,
  answer_value INTEGER NOT NULL,
  PRIMARY KEY (submission_id, question_id)
);

CREATE INDEX IF NOT EXISTS idx_submission_answers_submission_id
  ON submission_answers(submission_id);

CREATE INDEX IF NOT EXISTS idx_submission_answers_question_id
  ON submission_answers(question_id);
