-- ACGTI 反馈表补充答题明细字段
-- 仅在用户主动提交反馈时保存完整答题列表，减少主结果提交写入量

ALTER TABLE mbti_feedback ADD COLUMN answers_json TEXT;
ALTER TABLE mbti_feedback ADD COLUMN answer_count INTEGER;