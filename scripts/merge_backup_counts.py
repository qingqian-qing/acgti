"""
将旧备份 acgti-stats-backup.sql 中的 submissions 明细
重新聚合为当前 schema 使用的 4 张计数表，生成 merge_old_counts.sql。

用法：
    python scripts/merge_backup_counts.py

生成的 merge_old_counts.sql 可通过 wrangler 执行到线上 D1：
    npx wrangler d1 execute acgti-stats --remote --file=./merge_old_counts.sql --yes
"""

import sqlite3
from pathlib import Path

# ── 路径 ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKUP_SQL   = Path(r"C:\Users\TX\Downloads\acgti-stats-backup.sql")
TEMP_DB      = PROJECT_ROOT / "backup_old.db"
OUT_SQL      = PROJECT_ROOT / "merge_old_counts.sql"

# ── 1) 导入旧备份到本地 SQLite ───────────────────────
if TEMP_DB.exists():
    TEMP_DB.unlink()

conn = sqlite3.connect(str(TEMP_DB))
sql_text = BACKUP_SQL.read_text(encoding="utf-8")
conn.executescript(sql_text)

# 统计旧库总量
total = conn.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
print(f"旧备份 submissions 总行数: {total}")

if total == 0:
    print("没有数据可聚合，退出。")
    conn.close()
    raise SystemExit(0)

# ── 2) 聚合并生成 SQL ────────────────────────────────
def esc(s: str) -> str:
    return s.replace("'", "''")

with open(str(OUT_SQL), "w", encoding="utf-8") as f:
    f.write("-- ============================================================\n")
    f.write("-- 旧备份 -> 当前聚合表 (merge_old_counts.sql)\n")
    f.write(f"-- 旧 submissions 总量: {total}\n")
    f.write("-- 执行前请先确认线上当前计数，避免重复累计\n")
    f.write("-- 注意: D1 不支持手动 BEGIN TRANSACTION，wrangler 会自动包裹事务\n")
    f.write("-- ============================================================\n\n")

    # ── archetype_counts ──────────────────────────────
    f.write("-- archetype_counts\n")
    rows = conn.execute("""
        SELECT archetype_code, COUNT(*)
        FROM submissions
        GROUP BY archetype_code
        ORDER BY COUNT(*) DESC
    """).fetchall()
    archetype_total = 0
    for archetype_code, cnt in rows:
        archetype_total += cnt
        f.write(
            f"INSERT INTO archetype_counts (archetype_code, cnt, updated_at) "
            f"VALUES ('{esc(archetype_code)}', {cnt}, CURRENT_TIMESTAMP) "
            "ON CONFLICT(archetype_code) DO UPDATE SET "
            "cnt = archetype_counts.cnt + excluded.cnt, "
            "updated_at = CURRENT_TIMESTAMP;\n"
        )
    f.write(f"\n-- archetype_counts 合计: {archetype_total} ({len(rows)} 种)\n\n")
    print(f"archetype_counts: {len(rows)} 种, 合计 {archetype_total}")

    # ── character_counts ──────────────────────────────
    f.write("-- character_counts\n")
    rows = conn.execute("""
        SELECT character_code, COUNT(*)
        FROM submissions
        GROUP BY character_code
        ORDER BY COUNT(*) DESC
    """).fetchall()
    character_total = 0
    for character_code, cnt in rows:
        character_total += cnt
        f.write(
            f"INSERT INTO character_counts (character_code, cnt, updated_at) "
            f"VALUES ('{esc(character_code)}', {cnt}, CURRENT_TIMESTAMP) "
            "ON CONFLICT(character_code) DO UPDATE SET "
            "cnt = character_counts.cnt + excluded.cnt, "
            "updated_at = CURRENT_TIMESTAMP;\n"
        )
    f.write(f"\n-- character_counts 合计: {character_total} ({len(rows)} 种)\n\n")
    print(f"character_counts: {len(rows)} 种, 合计 {character_total}")

    # ── pair_counts ───────────────────────────────────
    f.write("-- pair_counts\n")
    rows = conn.execute("""
        SELECT archetype_code, character_code, COUNT(*)
        FROM submissions
        GROUP BY archetype_code, character_code
        ORDER BY COUNT(*) DESC
    """).fetchall()
    pair_total = 0
    for archetype_code, character_code, cnt in rows:
        pair_total += cnt
        f.write(
            f"INSERT INTO pair_counts (archetype_code, character_code, cnt, updated_at) "
            f"VALUES ('{esc(archetype_code)}', '{esc(character_code)}', {cnt}, CURRENT_TIMESTAMP) "
            "ON CONFLICT(archetype_code, character_code) DO UPDATE SET "
            "cnt = pair_counts.cnt + excluded.cnt, "
            "updated_at = CURRENT_TIMESTAMP;\n"
        )
    f.write(f"\n-- pair_counts 合计: {pair_total} ({len(rows)} 种组合)\n\n")
    print(f"pair_counts: {len(rows)} 种组合, 合计 {pair_total}")

    # ── daily_counts ──────────────────────────────────
    f.write("-- daily_counts\n")
    rows = conn.execute("""
        SELECT substr(created_at, 1, 10) AS stat_date, COUNT(*)
        FROM submissions
        GROUP BY substr(created_at, 1, 10)
        ORDER BY stat_date
    """).fetchall()
    daily_total = 0
    for stat_date, cnt in rows:
        daily_total += cnt
        f.write(
            f"INSERT INTO daily_counts (stat_date, total_cnt, updated_at) "
            f"VALUES ('{esc(stat_date)}', {cnt}, CURRENT_TIMESTAMP) "
            "ON CONFLICT(stat_date) DO UPDATE SET "
            "total_cnt = daily_counts.total_cnt + excluded.total_cnt, "
            "updated_at = CURRENT_TIMESTAMP;\n"
        )
    f.write(f"\n-- daily_counts 合计: {daily_total} ({len(rows)} 天)\n\n")
    print(f"daily_counts: {len(rows)} 天, 合计 {daily_total}")

    # ── 清除快照缓存 ─────────────────────────────────
    f.write("-- 快照删掉，等 cron / 接口重算\n")
    f.write("DELETE FROM stats_snapshot;\n")

conn.close()
print(f"\n生成完毕 -> {OUT_SQL}")
print("下一步：")
print("  1. 检查 merge_old_counts.sql 内容是否正确")
print("  2. npx wrangler d1 execute acgti-stats --remote --file=./merge_old_counts.sql --yes")
