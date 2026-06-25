"""
ACGTI T/F 维度专项校准消融实验

基于 0.3.2-ei-fix 稳定基线，只调 T/F 维度权重。
目标：
  - T/F >= 68%
  - T→F 从 ~64% 降到 55% 以下
  - E/I、S/N、J/P 不明显回退（<=2pp）
"""
import json
import sqlite3
import sys
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'analysis', 'acgti_feedback.db')
QUESTIONS_PATH = os.path.join(os.path.dirname(__file__), '..', 'src', 'data', 'questions.json')
OVERRIDES_PATH = os.path.join(os.path.dirname(__file__), '..', 'src', 'data', 'questionDimensionWeights.json')

DIMENSION_LETTERS = {
    'E_I': ('E', 'I'),
    'S_N': ('S', 'N'),
    'T_F': ('T', 'F'),
    'J_P': ('J', 'P'),
}


def load_questions():
    with open(QUESTIONS_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_overrides():
    with open(OVERRIDES_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_feedback(min_confidence=4):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        'SELECT self_mbti, confidence, answers_json, app_version '
        'FROM mbti_feedback WHERE answers_json IS NOT NULL AND predicted_mbti IS NOT NULL '
        'AND confidence >= ? ORDER BY created_at',
        (min_confidence,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def build_dim_weights(questions, overrides, custom_overrides=None):
    """构建维度权重映射。custom_overrides 为 dict，覆盖 overrides 中的值"""
    result = {}
    for q in questions:
        qid = q['id']
        base = overrides.get(qid, {q['dimension']: q['sign']})
        if custom_overrides and qid in custom_overrides:
            result[qid] = custom_overrides[qid]
        else:
            result[qid] = base
    return result


def replay_mbti(questions, dim_weights_map, answers_list):
    raw = {'E_I': 0.0, 'S_N': 0.0, 'T_F': 0.0, 'J_P': 0.0}
    dmax = {
        'E_I': {'pos': 0.0, 'neg': 0.0},
        'S_N': {'pos': 0.0, 'neg': 0.0},
        'T_F': {'pos': 0.0, 'neg': 0.0},
        'J_P': {'pos': 0.0, 'neg': 0.0},
    }

    for i, q in enumerate(questions):
        if i >= len(answers_list):
            break
        answer = answers_list[i]
        if not isinstance(answer, (int, float)) or answer < -3 or answer > 3:
            continue

        weights = dim_weights_map.get(q['id'], {q['dimension']: q['sign']})
        for dim, weight in weights.items():
            if weight == 0:
                continue
            raw[dim] += answer * weight
            if weight > 0:
                dmax[dim]['pos'] += 3 * weight
            else:
                dmax[dim]['neg'] += 3 * abs(weight)

    code = ''
    for dim in ('E_I', 'S_N', 'T_F', 'J_P'):
        r = raw[dim]
        if r >= 0:
            score = r / max(1, dmax[dim]['pos'])
        else:
            score = r / max(1, dmax[dim]['neg'])
        pos_letter, neg_letter = DIMENSION_LETTERS[dim]
        code += pos_letter if score >= 0 else neg_letter
    return code


def parse_answers(answers_raw, questions):
    try:
        answers_data = json.loads(answers_raw)
    except:
        return None

    if isinstance(answers_data, list):
        answers_list = [0] * len(questions)
        for item in answers_data:
            qid = item.get('questionId', '')
            val = item.get('answerValue', 0)
            try:
                idx = int(qid.replace('q', '')) - 1
            except (ValueError, AttributeError):
                continue
            if 0 <= idx < len(answers_list):
                answers_list[idx] = val
        return answers_list
    return None


def run_experiment(name, feedback_data, questions, overrides, custom_overrides=None, label=''):
    dim_weights_map = build_dim_weights(questions, overrides, custom_overrides)

    total = 0
    exact = 0
    dim_correct = {'E_I': 0, 'S_N': 0, 'T_F': 0, 'J_P': 0}
    dim_dir = {
        'E_I': {'I->E': 0, 'E->I': 0, 'I_total': 0, 'E_total': 0},
        'S_N': {'N->S': 0, 'S->N': 0, 'N_total': 0, 'S_total': 0},
        'T_F': {'T->F': 0, 'F->T': 0, 'T_total': 0, 'F_total': 0},
        'J_P': {'P->J': 0, 'J->P': 0, 'P_total': 0, 'J_total': 0},
    }

    for row in feedback_data:
        self_mbti = row['self_mbti']
        if not self_mbti or len(self_mbti) != 4:
            continue

        answers_list = parse_answers(row['answers_json'], questions)
        if answers_list is None:
            continue

        predicted = replay_mbti(questions, dim_weights_map, answers_list)
        total += 1

        if predicted == self_mbti:
            exact += 1

        for dim_idx, dim in enumerate(('E_I', 'S_N', 'T_F', 'J_P')):
            if self_mbti[dim_idx] == predicted[dim_idx]:
                dim_correct[dim] += 1

            self_letter = self_mbti[dim_idx]
            pred_letter = predicted[dim_idx]
            if dim == 'T_F':
                if self_letter == 'T':
                    dim_dir[dim]['T_total'] += 1
                    if pred_letter == 'F':
                        dim_dir[dim]['T->F'] += 1
                else:
                    dim_dir[dim]['F_total'] += 1
                    if pred_letter == 'T':
                        dim_dir[dim]['F->T'] += 1
            elif dim == 'E_I':
                if self_letter == 'I':
                    dim_dir[dim]['I_total'] += 1
                    if pred_letter == 'E':
                        dim_dir[dim]['I->E'] += 1
                else:
                    dim_dir[dim]['E_total'] += 1
                    if pred_letter == 'I':
                        dim_dir[dim]['E->I'] += 1
            elif dim == 'S_N':
                if self_letter == 'N':
                    dim_dir[dim]['N_total'] += 1
                    if pred_letter == 'S':
                        dim_dir[dim]['N->S'] += 1
                else:
                    dim_dir[dim]['S_total'] += 1
                    if pred_letter == 'N':
                        dim_dir[dim]['S->N'] += 1
            elif dim == 'J_P':
                if self_letter == 'P':
                    dim_dir[dim]['P_total'] += 1
                    if pred_letter == 'J':
                        dim_dir[dim]['P->J'] += 1
                else:
                    dim_dir[dim]['J_total'] += 1
                    if pred_letter == 'P':
                        dim_dir[dim]['J->P'] += 1

    if total == 0:
        print(f"  [{name}] 无有效数据")
        return None

    result = {
        'total': total,
        'exact': exact,
        'exact_pct': exact * 100 / total,
        'dims': {dim: dim_correct[dim] * 100 / total for dim in ('E_I', 'S_N', 'T_F', 'J_P')},
        'dim_dir': dim_dir,
    }

    print(f"\n{'='*60}")
    print(f"  {name} {label}")
    print(f"{'='*60}")
    print(f"  n={total}  完全匹配: {result['exact_pct']:.1f}%")
    print(f"  E/I: {result['dims']['E_I']:.1f}%  S/N: {result['dims']['S_N']:.1f}%  "
          f"T/F: {result['dims']['T_F']:.1f}%  J/P: {result['dims']['J_P']:.1f}%")

    t_total = dim_dir['T_F']['T_total'] or 1
    f_total = dim_dir['T_F']['F_total'] or 1
    print(f"  T→F: {dim_dir['T_F']['T->F']*100/t_total:.1f}%  F→T: {dim_dir['T_F']['F->T']*100/f_total:.1f}%")

    i_total = dim_dir['E_I']['I_total'] or 1
    print(f"  I→E: {dim_dir['E_I']['I->E']*100/i_total:.1f}%")

    return result


def main():
    min_conf = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    print(f"加载题目和反馈数据 (confidence >= {min_conf})...")
    questions = load_questions()
    overrides = load_overrides()
    feedback = load_feedback(min_conf)
    print(f"有效反馈: {len(feedback)} 条")

    # ===== 0. 基线 =====
    print("\n" + "=" * 60)
    print("  阶段 0: 基线")
    print("=" * 60)

    # A: 0.3.0 原始（无 override）
    run_experiment('A', feedback, questions, {}, None, '(0.3.0 基线，无 override)')

    # B: 0.3.2 当前线上
    run_experiment('B', feedback, questions, overrides, None, '(0.3.2 当前线上)')

    # ===== 1. T/F 单题消融：逐题关闭看哪题对 T/F 贡献最大 =====
    print("\n" + "=" * 60)
    print("  阶段 1: T/F 单题消融（逐题从 T/F 维度移除）")
    print("=" * 60)

    tf_questions = [q for q in questions if q['dimension'] == 'T_F']
    print(f"  T/F 维度题目: {', '.join(q['id'] for q in tf_questions)}")

    for q in tf_questions:
        qid = q['id']
        # 把该题从 T/F 维度移除（设权重为 0 或只保留其他维度）
        custom = {}
        for oid, ov in overrides.items():
            custom[oid] = dict(ov)
        # 该题的 T_F 权重设为 0（不贡献 T/F 分数）
        if qid in custom:
            if 'T_F' in custom[qid]:
                custom[qid]['T_F'] = 0
            else:
                custom[qid]['T_F'] = 0
        else:
            custom[qid] = {'T_F': 0}
        run_experiment(f'no-{qid}', feedback, questions, overrides, custom,
                       f'(移除 {qid} 的 T/F 贡献)')

    # ===== 2. 跨维度 T/F 强信号题消融 =====
    print("\n" + "=" * 60)
    print("  阶段 2: 跨维度 T/F 信号题消融")
    print("=" * 60)

    # 来自 weights_TF.csv 的跨维度强信号题
    cross_dim_tf = ['q24', 'q2', 'q25', 'q37', 'q26', 'q36', 'q5']
    for qid in cross_dim_tf:
        custom = {}
        for oid, ov in overrides.items():
            custom[oid] = dict(ov)
        if qid in custom:
            custom[qid]['T_F'] = 0
        else:
            custom[qid] = {'T_F': 0}
        run_experiment(f'no-{qid}-tf', feedback, questions, overrides, custom,
                       f'(移除 {qid} 的 T/F 跨维度贡献)')

    # ===== 3. 压低 F 方向题权重（这些题 sign=-1 即偏向 F）=====
    print("\n" + "=" * 60)
    print("  阶段 3: F 方向题权重压低扫描")
    print("=" * 60)

    # q9 是最强 F 信号题（sign=-1, coef=-0.291），q19、q22、q27 也是 F 方向
    f_dir_questions = ['q9', 'q19', 'q22', 'q27']

    for qid in f_dir_questions:
        print(f"\n--- {qid} 压低扫描 ---")
        for scale in [0.5, 0.3, 0.0, -0.3, -0.5]:
            custom = {}
            for oid, ov in overrides.items():
                custom[oid] = dict(ov)
            custom[qid] = {'T_F': scale}
            run_experiment(f'{qid}-tf{scale}', feedback, questions, overrides, custom,
                           f'({qid} T_F={scale})')

    # ===== 4. 增强 T 方向锚点（q29 是最强 T 信号题，sign=1）=====
    print("\n" + "=" * 60)
    print("  阶段 4: 增强 T 方向锚点")
    print("=" * 60)

    for scale in [1.0, 1.2, 1.5, 1.8, 2.0]:
        custom = {}
        for oid, ov in overrides.items():
            custom[oid] = dict(ov)
        custom['q29'] = {'T_F': scale}
        run_experiment(f'q29-tf{scale}', feedback, questions, overrides, custom,
                       f'(q29 T_F={scale})')

    # ===== 5. 联合调优：压低 F + 增强 T =====
    print("\n" + "=" * 60)
    print("  阶段 5: 联合 T/F 调优")
    print("=" * 60)

    # 基于阶段 3 和 4 的最佳结果组合
    configs = [
        # (label, custom_overrides)
        ('q9-down-q29-up', {
            'q9': {'T_F': 0.3},
            'q29': {'T_F': 1.5},
        }),
        ('q9-off-q29-up', {
            'q9': {'T_F': 0},
            'q29': {'T_F': 1.5},
        }),
        ('q9-0.3-q19-0.3-q29-1.5', {
            'q9': {'T_F': 0.3},
            'q19': {'T_F': 0.3},
            'q29': {'T_F': 1.5},
        }),
        ('q9-0-q19-0.3-q22-0.3-q29-1.5', {
            'q9': {'T_F': 0},
            'q19': {'T_F': 0.3},
            'q22': {'T_F': 0.3},
            'q29': {'T_F': 1.5},
        }),
        ('q9-0-q19-0.5-q22-0.5-q29-1.8', {
            'q9': {'T_F': 0},
            'q19': {'T_F': 0.5},
            'q22': {'T_F': 0.5},
            'q29': {'T_F': 1.8},
        }),
        ('q9-0-q19-0.3-q22-0.3-q27-0.5-q29-1.5', {
            'q9': {'T_F': 0},
            'q19': {'T_F': 0.3},
            'q22': {'T_F': 0.3},
            'q27': {'T_F': 0.5},
            'q29': {'T_F': 1.5},
        }),
        # q24 跨维度也有 T/F 信号，尝试给它加 T/F 反向
        ('q9-0-q24-TF0.5-q29-1.5', {
            'q9': {'T_F': 0},
            'q24': {'S_N': 1, 'T_F': 0.5},
            'q29': {'T_F': 1.5},
        }),
        ('q9-0-q19-0.3-q24-TF0.5-q29-1.5', {
            'q9': {'T_F': 0},
            'q19': {'T_F': 0.3},
            'q24': {'S_N': 1, 'T_F': 0.5},
            'q29': {'T_F': 1.5},
        }),
    ]

    for label, custom in configs:
        # 合并现有 overrides（保留 E/I、S/N、J/P 的改动）
        merged = {}
        for oid, ov in overrides.items():
            merged[oid] = dict(ov)
        for qid, qov in custom.items():
            if qid in merged:
                merged[qid].update(qov)
            else:
                merged[qid] = qov
        run_experiment(f'joint-{label}', feedback, questions, overrides, merged,
                       f'(联合: {label})')

    # ===== 6. 最优候选精调扫描 =====
    print("\n" + "=" * 60)
    print("  阶段 6: 最优候选精调扫描")
    print("=" * 60)

    # 基于阶段 5 的最佳结果，做细粒度扫描
    # 只在最优区间附近微调
    fine_configs = []
    for q9_val in [0, 0.3]:
        for q29_val in [1.2, 1.5, 1.8]:
            for q19_val in [0.3, 0.5]:
                label = f'q9={q9_val}-q29={q29_val}-q19={q19_val}'
                custom = {}
                for oid, ov in overrides.items():
                    custom[oid] = dict(ov)
                custom['q9'] = {'T_F': q9_val}
                custom['q19'] = {'T_F': q19_val}
                custom['q29'] = {'T_F': q29_val}
                fine_configs.append((label, custom))

    for label, custom in fine_configs:
        run_experiment(f'fine-{label}', feedback, questions, overrides, custom,
                       f'(精调: {label})')

    print("\n\nDone.")


if __name__ == '__main__':
    main()
