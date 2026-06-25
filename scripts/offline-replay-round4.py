"""
ACGTI 第 4 轮消融实验 — 基于 0.3.3-tf-fix 数据的全维度优化

基于数据:
  - 总 feedback: 8171 (高置信 5399)
  - 0.3.3-tf-fix 线上: n=392, 完全匹配 20.2%, EI 65.1%, SN 72.7%, TF 65.1%, JP 64.8%
  - 离线回放(当前权重): T→F 53.4%, I→E 37.9%

目标:
  1. 找到提升 EI 准确率的方向（当前 64%, I→E 37.9%）
  2. 确认 TF 是否还能进一步改善
  3. 不改题面，只调 questionDimensionWeights.json
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


def build_dim_weights(questions, overrides, custom_overrides=None):
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
            if dim == 'E_I':
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
            elif dim == 'T_F':
                if self_letter == 'T':
                    dim_dir[dim]['T_total'] += 1
                    if pred_letter == 'F':
                        dim_dir[dim]['T->F'] += 1
                else:
                    dim_dir[dim]['F_total'] += 1
                    if pred_letter == 'T':
                        dim_dir[dim]['F->T'] += 1
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
        return None

    result = {
        'total': total,
        'exact': exact,
        'exact_pct': exact * 100 / total,
        'dims': {dim: dim_correct[dim] * 100 / total for dim in ('E_I', 'S_N', 'T_F', 'J_P')},
        'dim_dir': dim_dir,
    }

    t_total = max(1, dim_dir['T_F']['T_total'])
    f_total = max(1, dim_dir['T_F']['F_total'])
    i_total = max(1, dim_dir['E_I']['I_total'])
    e_total = max(1, dim_dir['E_I']['E_total'])
    p_total = max(1, dim_dir['J_P']['P_total'])
    j_total = max(1, dim_dir['J_P']['J_total'])
    n_total = max(1, dim_dir['S_N']['N_total'])
    s_total = max(1, dim_dir['S_N']['S_total'])

    print(f"  [{name:20s}] n={total:5d} match={result['exact_pct']:5.1f}% "
          f"EI={result['dims']['E_I']:5.1f}% SN={result['dims']['S_N']:5.1f}% "
          f"TF={result['dims']['T_F']:5.1f}% JP={result['dims']['J_P']:5.1f}% | "
          f"I->E={dim_dir['E_I']['I->E']*100/i_total:4.1f}% "
          f"T->F={dim_dir['T_F']['T->F']*100/t_total:4.1f}% "
          f"P->J={dim_dir['J_P']['P->J']*100/p_total:4.1f}% "
          f"| {label}")

    return result


def main():
    min_conf = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    print(f"=== 第 4 轮消融实验 (confidence >= {min_conf}) ===\n")

    questions = load_questions()
    overrides = load_overrides()
    feedback = load_feedback(min_conf)
    print(f"有效反馈: {len(feedback)} 条\n")

    # ===== 基线 =====
    print("--- 基线 ---")
    run_experiment('0.3.0-baseline', feedback, questions, {}, None, '无 override')
    run_experiment('0.3.3-current', feedback, questions, overrides, None, '当前线上权重')

    # ===== 阶段 1: EI 单题消融 =====
    # EI 在 ML 模型中准确率 76.2%，但回放只有 64%。强信号题: q28(-0.46), q12(+0.38), q32(-0.27), q39(+0.20)
    # I→E 37.9% 说明大量 I 被判为 E，说明 E 方向题信号过强
    print("\n--- 阶段 1: EI 单题消融（逐题关闭对 EI 的贡献）---")

    # 列出所有有 EI 维度的题
    ei_questions = []
    for q in questions:
        qid = q['id']
        ov = overrides.get(qid, {q['dimension']: q['sign']})
        if 'E_I' in ov or q['dimension'] == 'E_I':
            ei_questions.append(qid)
    print(f"  EI 维度题目: {', '.join(ei_questions)}")

    for qid in ei_questions:
        custom = {}
        for oid, ov in overrides.items():
            custom[oid] = dict(ov)
        # 关闭该题的 EI 贡献
        if qid in custom:
            custom[qid] = {k: v for k, v in custom[qid].items() if k != 'E_I'}
        if qid not in custom:
            custom[qid] = {}
        if not custom.get(qid):
            custom[qid] = {'E_I': 0}
        elif 'E_I' not in custom.get(qid, {}):
            custom[qid]['E_I'] = 0
        run_experiment(f'no-EI-{qid}', feedback, questions, overrides, custom,
                       f'移除 {qid} EI')

    # ===== 阶段 2: EI 压低 E 方向题 =====
    # q28、q32、q6 是 E 方向强信号题（coef<0 表示越同意越 E）
    # q12、q39 是 I 方向强信号题
    print("\n--- 阶段 2: EI 权重扫描 ---")

    # q28 是最强 E 题目（sign=1, dimension=E_I, 原始 coef=-0.465 表示负相关E）
    # 让我试压低它的权重
    for qid in ['q28', 'q12', 'q32', 'q39', 'q11', 'q23']:
        for scale in [0.5, 0.7, 1.3, 1.5, 2.0]:
            custom = {}
            for oid, ov in overrides.items():
                custom[oid] = dict(ov)
            # 只修改该题的 EI 权重
            if qid in custom:
                custom[qid]['E_I'] = scale * custom[qid].get('E_I',
                    next((q['sign'] for q in questions if q['id'] == qid), 1))
            else:
                base_sign = next((q['sign'] for q in questions if q['id'] == qid), 1)
                custom[qid] = {'E_I': scale * base_sign}
            run_experiment(f'{qid}-EI*{scale}', feedback, questions, overrides, custom,
                           f'{qid} EI *{scale}')

    # ===== 阶段 3: EI 定向增强实验 =====
    print("\n--- 阶段 3: EI 联合增强 ---")

    # 基于 ML 模型: I->E 过多，说明 E 方向信号过强
    # 尝试增强 I 方向锚点（q12 coef=+0.38 意味着越同意越 I）
    ei_configs = [
        # 增强 I 方向
        ('q12x1.5', {'q12': {'E_I': 1.5}}),
        ('q12x2.0', {'q12': {'E_I': 2.0}}),
        ('q39x1.5', {'q39': {'E_I': 1.5}}),
        # 压低 E 方向
        ('q28x0.7', {'q28': {'E_I': 0.7}}),
        ('q28x0.5', {'q28': {'E_I': 0.5}}),
        ('q32x0.7', {'q32': {'E_I': 0.7}}),
        ('q32x0.5', {'q32': {'E_I': 0.5}}),
        # 联合
        ('q12x1.5+q28x0.7', {'q12': {'E_I': 1.5}, 'q28': {'E_I': 0.7}}),
        ('q12x1.5+q32x0.7', {'q12': {'E_I': 1.5}, 'q32': {'E_I': 0.7}}),
        ('q12x1.5+q28x0.7+q32x0.7', {'q12': {'E_I': 1.5}, 'q28': {'E_I': 0.7}, 'q32': {'E_I': 0.7}}),
        ('q12x2.0+q28x0.7+q32x0.7', {'q12': {'E_I': 2.0}, 'q28': {'E_I': 0.7}, 'q32': {'E_I': 0.7}}),
        # q39 也加入
        ('q12x1.5+q39x1.5', {'q12': {'E_I': 1.5}, 'q39': {'E_I': 1.5}}),
        ('q12x1.5+q39x1.5+q28x0.7', {'q12': {'E_I': 1.5}, 'q39': {'E_I': 1.5}, 'q28': {'E_I': 0.7}}),
    ]

    for label, custom in ei_configs:
        merged = {}
        for oid, ov in overrides.items():
            merged[oid] = dict(ov)
        for qid, qov in custom.items():
            if qid in merged:
                merged[qid].update(qov)
            else:
                merged[qid] = qov
        run_experiment(f'EI-{label}', feedback, questions, overrides, merged, label)

    # ===== 阶段 4: TF 进一步优化 =====
    print("\n--- 阶段 4: TF 进一步优化 ---")

    tf_configs = [
        # q29 继续增强
        ('q29x2.0', {'q29': {'T_F': 2.0}}),
        ('q29x2.5', {'q29': {'T_F': 2.5}}),
        # q20 继续压低
        ('q20x-0.3', {'q20': {'T_F': -0.3}}),
        ('q20x0', {'q20': {'T_F': 0}}),
        # q19 压低
        ('q19x0.3', {'q19': {'T_F': 0.3}}),
        ('q19x0.5', {'q19': {'T_F': 0.5}}),
        # 联合
        ('q20x-0.3+q29x2.0', {'q20': {'T_F': -0.3}, 'q29': {'T_F': 2.0}}),
        ('q20x0+q29x2.0', {'q20': {'T_F': 0}, 'q29': {'T_F': 2.0}}),
        ('q20x-0.3+q19x0.3+q29x2.0', {'q20': {'T_F': -0.3}, 'q19': {'T_F': 0.3}, 'q29': {'T_F': 2.0}}),
        ('q20x0+q19x0.3+q29x2.0', {'q20': {'T_F': 0}, 'q19': {'T_F': 0.3}, 'q29': {'T_F': 2.0}}),
    ]

    for label, custom in tf_configs:
        merged = {}
        for oid, ov in overrides.items():
            merged[oid] = dict(ov)
        for qid, qov in custom.items():
            if qid in merged:
                merged[qid].update(qov)
            else:
                merged[qid] = qov
        run_experiment(f'TF-{label}', feedback, questions, overrides, merged, label)

    # ===== 阶段 5: EI + TF 联合 =====
    print("\n--- 阶段 5: EI + TF 联合搜索 ---")

    joint_configs = [
        ('v1', {'q12': {'E_I': 1.5}, 'q28': {'E_I': 0.7}, 'q20': {'T_F': -0.3}, 'q29': {'T_F': 2.0}}),
        ('v2', {'q12': {'E_I': 1.5}, 'q28': {'E_I': 0.7}, 'q32': {'E_I': 0.7}, 'q20': {'T_F': -0.3}, 'q29': {'T_F': 2.0}}),
        ('v3', {'q12': {'E_I': 2.0}, 'q28': {'E_I': 0.7}, 'q20': {'T_F': -0.3}, 'q29': {'T_F': 2.0}}),
        ('v4', {'q12': {'E_I': 1.5}, 'q39': {'E_I': 1.5}, 'q28': {'E_I': 0.7}, 'q20': {'T_F': -0.3}, 'q29': {'T_F': 2.0}}),
        ('v5', {'q12': {'E_I': 1.5}, 'q39': {'E_I': 1.5}, 'q28': {'E_I': 0.7}, 'q32': {'E_I': 0.7}, 'q20': {'T_F': 0}, 'q29': {'T_F': 2.0}}),
        # 保守版
        ('v6-conservative', {'q12': {'E_I': 1.3}, 'q28': {'E_I': 0.8}, 'q20': {'T_F': -0.3}, 'q29': {'T_F': 1.8}}),
        ('v7-moderate', {'q12': {'E_I': 1.5}, 'q28': {'E_I': 0.7}, 'q20': {'T_F': 0}, 'q29': {'T_F': 2.0}}),
    ]

    for label, custom in joint_configs:
        merged = {}
        for oid, ov in overrides.items():
            merged[oid] = dict(ov)
        for qid, qov in custom.items():
            if qid in merged:
                merged[qid].update(qov)
            else:
                merged[qid] = qov
        run_experiment(f'joint-{label}', feedback, questions, overrides, merged, label)

    # ===== 阶段 6: JP 和 SN 微调探索 =====
    print("\n--- 阶段 6: JP 微调（P->J 仍 36.3%）---")

    # P->J 36.3% 仍偏高，尝试进一步压低 J 方向信号
    jp_configs = [
        ('q2x-0.8', {'q2': {'J_P': -0.8}}),
        ('q2x-0.5', {'q2': {'J_P': -0.5}}),
        ('q8x-1.0', {'q8': {'J_P': -1.0}}),
        ('q8x-0.8', {'q8': {'J_P': -0.8}}),
        ('q31x-0.5', {'q31': {'J_P': -0.5}}),
        ('q2x-0.8+q8x-1.0', {'q2': {'J_P': -0.8}, 'q8': {'J_P': -1.0}}),
    ]

    for label, custom in jp_configs:
        merged = {}
        for oid, ov in overrides.items():
            merged[oid] = dict(ov)
        for qid, qov in custom.items():
            if qid in merged:
                merged[qid].update(qov)
            else:
                merged[qid] = qov
        run_experiment(f'JP-{label}', feedback, questions, overrides, merged, label)

    # ===== 阶段 7: 全局最优候选组合 =====
    print("\n--- 阶段 7: 全局最优候选组合 ---")

    final_configs = [
        # 基于以上实验的最有希望的组合
        ('best-EI-only', {
            'q12': {'E_I': 1.5}, 'q28': {'E_I': 0.7}, 'q39': {'E_I': 1.5},
        }),
        ('best-TF-only', {
            'q20': {'T_F': 0}, 'q29': {'T_F': 2.0},
        }),
        ('best-EI+TF', {
            'q12': {'E_I': 1.5}, 'q28': {'E_I': 0.7}, 'q39': {'E_I': 1.5},
            'q20': {'T_F': 0}, 'q29': {'T_F': 2.0},
        }),
        ('best-all', {
            'q12': {'E_I': 1.5}, 'q28': {'E_I': 0.7}, 'q39': {'E_I': 1.5},
            'q20': {'T_F': 0}, 'q29': {'T_F': 2.0},
            'q2': {'J_P': -0.8},
        }),
        ('best-all-v2', {
            'q12': {'E_I': 1.5}, 'q28': {'E_I': 0.7},
            'q20': {'T_F': 0}, 'q29': {'T_F': 2.0},
            'q2': {'J_P': -0.8},
        }),
        ('best-conservative', {
            'q12': {'E_I': 1.3}, 'q28': {'E_I': 0.8},
            'q20': {'T_F': -0.3}, 'q29': {'T_F': 1.8},
        }),
    ]

    for label, custom in final_configs:
        merged = {}
        for oid, ov in overrides.items():
            merged[oid] = dict(ov)
        for qid, qov in custom.items():
            if qid in merged:
                merged[qid].update(qov)
            else:
                merged[qid] = qov
        run_experiment(f'final-{label}', feedback, questions, overrides, merged, label)

    print("\n\nDone.")


if __name__ == '__main__':
    main()
