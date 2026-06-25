-- ACGTI 统计数据库简化：去掉一题一行，改为 answers_json 打包
-- 一次提交只写 1 行到 submissions，题目数据序列化为 JSON 可选保存

-- submissions 新增字段
ALTER TABLE submissions ADD COLUMN predicted_mbti TEXT;
ALTER TABLE submissions ADD COLUMN answers_json TEXT;
ALTER TABLE submissions ADD COLUMN answer_count INTEGER;
ALTER TABLE submissions ADD COLUMN questions_version TEXT;
