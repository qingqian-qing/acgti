"""
ACGTI 离线回放消融实验脚本
用 feedback 表中的 answers_json 回放不同权重配置，对比四维准确率。
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


def load_feedback(min_confidence=1):
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


def build_dim_weights(questions, overrides, config):
    """
    config 可以是:
    - 'baseline': 完全不用 override (0.3.0)
    - '0.3.1': 用完整 override
    - dict: 自定义每题覆盖, 例 {'q23': None, 'q37': {'S_N': -0.5}}
      None 表示移除该题的 override, 回到原始
    """
    result = {}
    for q in questions:
        qid = q['id']
        if config == 'baseline':
            result[qid] = {q['dimension']: q['sign']}
        elif config == '0.3.1':
            result[qid] = overrides.get(qid, {q['dimension']: q['sign']})
        elif isinstance(config, dict):
            if qid in config:
                custom = config[qid]
                if custom is None:
                    result[qid] = {q['dimension']: q['sign']}
                else:
                    result[qid] = custom
            elif qid in overrides:
                result[qid] = overrides[qid]
            else:
                result[qid] = {q['dimension']: q['sign']}
        else:
            result[qid] = {q['dimension']: q['sign']}
    return result


def replay_mbti(questions, dim_weights_map, answers_list):
    """用给定权重配置回放，返回 mbti code"""
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


def run_experiment(name, feedback_data, questions, overrides, config, label=''):
    """跑一组实验并输出统计"""
    dim_weights_map = build_dim_weights(questions, overrides, config)

    total = 0
    exact = 0
    dim_correct = {'E_I': 0, 'S_N': 0, 'T_F': 0, 'J_P': 0}
    # 方向性统计
    dim_dir = {
        'E_I': {'I->E': 0, 'E->I': 0, 'I_total': 0, 'E_total': 0},
        'S_N': {'N->S': 0, 'S->N': 0, 'N_total': 0, 'S_total': 0},
        'T_F': {'T->F': 0, 'F->T': 0, 'T_total': 0, 'F_total': 0},
        'J_P': {'P->J': 0, 'J->P': 0, 'P_total': 0, 'J_total': 0},
    }
    archetype_counts = {}

    for row in feedback_data:
        self_mbti = row['self_mbti']
        if not self_mbti or len(self_mbti) != 4:
            continue

        answers_raw = row['answers_json']
        if not answers_raw:
            continue
        try:
            answers_data = json.loads(answers_raw)
        except:
            continue

        # 解析答案列表
        # 格式: [{"questionId": "q1", "answerValue": 2}, ...]
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
        else:
            continue

        predicted = replay_mbti(questions, dim_weights_map, answers_list)
        total += 1

        if predicted == self_mbti:
            exact += 1

        for dim_idx, dim in enumerate(('E_I', 'S_N', 'T_F', 'J_P')):
            if self_mbti[dim_idx] == predicted[dim_idx]:
                dim_correct[dim] += 1

            # 方向统计
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
        print(f"  [{name}] 无有效数据")
        return

    print(f"\n{'='*60}")
    print(f"  {name} {label}")
    print(f"{'='*60}")
    print(f"  样本量: {total}")
    print(f"  完全匹配: {exact} ({exact*100/total:.1f}%)")
    print(f"  四维匹配率:")
    for dim in ('E_I', 'S_N', 'T_F', 'J_P'):
        pct = dim_correct[dim] * 100 / total
        print(f"    {dim}: {dim_correct[dim]} ({pct:.1f}%)")

    print(f"  偏移方向:")
    for dim, dirs in dim_dir.items():
        if dim == 'E_I':
            i_total = dirs['I_total'] or 1
            e_total = dirs['E_total'] or 1
            print(f"    I->E: {dirs['I->E']} ({dirs['I->E']*100/i_total:.1f}% of I)  "
                  f"E->I: {dirs['E->I']} ({dirs['E->I']*100/e_total:.1f}% of E)")
        elif dim == 'S_N':
            n_total = dirs['N_total'] or 1
            s_total = dirs['S_total'] or 1
            print(f"    N->S: {dirs['N->S']} ({dirs['N->S']*100/n_total:.1f}% of N)  "
                  f"S->N: {dirs['S->N']} ({dirs['S->N']*100/s_total:.1f}% of S)")
        elif dim == 'T_F':
            t_total = dirs['T_total'] or 1
            f_total = dirs['F_total'] or 1
            print(f"    T->F: {dirs['T->F']} ({dirs['T->F']*100/t_total:.1f}% of T)  "
                  f"F->T: {dirs['F->T']} ({dirs['F->T']*100/f_total:.1f}% of F)")
        elif dim == 'J_P':
            p_total = dirs['P_total'] or 1
            j_total = dirs['J_total'] or 1
            print(f"    P->J: {dirs['P->J']} ({dirs['P->J']*100/p_total:.1f}% of P)  "
                  f"J->P: {dirs['J->P']} ({dirs['J->P']*100/j_total:.1f}% of J)")

    return {
        'total': total,
        'exact': exact,
        'exact_pct': exact * 100 / total,
        'dims': {dim: dim_correct[dim] * 100 / total for dim in ('E_I', 'S_N', 'T_F', 'J_P')},
        'dim_dir': dim_dir,
    }


def main():
    min_conf = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    print(f"加载题目和反馈数据 (confidence >= {min_conf})...")
    questions = load_questions()
    overrides = load_overrides()
    feedback = load_feedback(min_conf)
    print(f"有效反馈: {len(feedback)} 条")

    # 解析答案格式检查
    sample = feedback[0]['answers_json'] if feedback else '[]'
    sample_parsed = json.loads(sample)
    print(f"答案格式样本: {type(sample_parsed).__name__}, 长度: {len(sample_parsed) if isinstance(sample_parsed, list) else 'N/A'}")
    if isinstance(sample_parsed, list) and len(sample_parsed) > 0:
        print(f"  第一条样本: {json.dumps(sample_parsed[0], ensure_ascii=False)[:100]}")

    # ===== 消融实验 =====

    # A 组: 0.3.0 基线（无 override）
    run_experiment('A', feedback, questions, overrides, 'baseline', '(0.3.0 基线)')

    # B 组: 0.3.1 原样（完整 override）
    run_experiment('B', feedback, questions, overrides, '0.3.1', '(0.3.1 原样)')

    # C 组: 只弱化 q23（回到原始 E/I）
    config_c = {'q23': None}
    run_experiment('C', feedback, questions, overrides, config_c, '(0.3.1 + q23 回原始 E/I)')

    # D 组: 只弱化 q37（回到原始 J/P）
    config_d = {'q37': None}
    run_experiment('D', feedback, questions, overrides, config_d, '(0.3.1 + q37 回原始 J/P)')

    # E 组: 同时弱化 q23 + q37
    config_e = {'q23': None, 'q37': None}
    run_experiment('E', feedback, questions, overrides, config_e, '(0.3.1 + q23+q37 回原始)')

    # ===== S/N 回调实验（基于最佳消融组） =====

    # F 组: q23 回原始 + S/N 整体 * 0.7
    overrides_sn07 = {}
    for qid, ov in overrides.items():
        new_ov = {}
        for dim, w in ov.items():
            if dim == 'S_N':
                new_ov[dim] = round(w * 0.7, 4)
            else:
                new_ov[dim] = w
        overrides_sn07[qid] = new_ov
    config_f = dict(overrides_sn07)
    config_f['q23'] = None  # q23 回原始
    run_experiment('F', feedback, questions, overrides, config_f, '(q23回原始 + S/N*0.7)')

    # G 组: q23 回原始 + S/N 整体 * 0.6
    overrides_sn06 = {}
    for qid, ov in overrides.items():
        new_ov = {}
        for dim, w in ov.items():
            if dim == 'S_N':
                new_ov[dim] = round(w * 0.6, 4)
            else:
                new_ov[dim] = w
        overrides_sn06[qid] = new_ov
    config_g = dict(overrides_sn06)
    config_g['q23'] = None
    run_experiment('G', feedback, questions, overrides, config_g, '(q23回原始 + S/N*0.6)')

    # ===== 附加：只回拉 q23 的 S/N 权重 =====

    # H 组: q23 S/N 从 -0.9 调到 -0.5
    config_h = {'q23': {'S_N': -0.5}}
    run_experiment('H', feedback, questions, overrides, config_h, '(q23 S_N: -0.5)')

    # I 组: q23 S/N 从 -0.9 调到 -0.3
    config_i = {'q23': {'S_N': -0.3}}
    run_experiment('I', feedback, questions, overrides, config_i, '(q23 S_N: -0.3)')

    # J 组: q23 保留 E/I + 加 S/N (双维度贡献)
    config_j = {'q23': {'E_I': -1, 'S_N': -0.5}}
    run_experiment('J', feedback, questions, overrides, config_j, '(q23 E_I:-1 + S_N:-0.5)')

    # K 组: q23 E_I:-1 + S_N:-0.3 + q37 S_N:-0.5 J_P:0.25
    config_k = {'q23': {'E_I': -1, 'S_N': -0.3}, 'q37': {'S_N': -0.5, 'J_P': 0.25}}
    run_experiment('K', feedback, questions, overrides, config_k, '(q23双维度 + q37弱化S/N)')

    # ===== 精调实验：q23 双维度 S/N 权重扫描 =====
    print("\n\n" + "=" * 60)
    print("  精调实验：q23 E_I:-1 + S_N:变量")
    print("=" * 60)

    for sn_val in [-0.9, -0.8, -0.7, -0.6, -0.5]:
        config = {'q23': {'E_I': -1, 'S_N': sn_val}}
        run_experiment(f'L{abs(sn_val)}', feedback, questions, overrides, config,
                       f'(q23 E_I:-1 + S_N:{sn_val})')

    # ===== 精调实验：q23 双维度 + q37 S/N 联合扫描 =====
    print("\n\n" + "=" * 60)
    print("  精调实验：q23 + q37 联合")
    print("=" * 60)

    for q23_sn in [-0.7, -0.8]:
        for q37_sn in [-0.5, -0.6]:
            config = {
                'q23': {'E_I': -1, 'S_N': q23_sn},
                'q37': {'S_N': q37_sn, 'J_P': 0.25},
            }
            run_experiment(f'M-{abs(q23_sn)}-{abs(q37_sn)}', feedback, questions, overrides, config,
                           f'(q23 E_I:-1 S_N:{q23_sn} + q37 S_N:{q37_sn})')

    # ===== 精调：q35 也参与回调 =====
    for q35_sn in [-0.3, -0.4]:
        config = {
            'q23': {'E_I': -1, 'S_N': -0.8},
            'q37': {'S_N': -0.6, 'J_P': 0.25},
            'q35': {'S_N': q35_sn},
        }
        run_experiment(f'N-{abs(q35_sn)}', feedback, questions, overrides, config,
                       f'(q23 dual + q37 S_N:-0.6 + q35 S_N:{q35_sn})')

    print("\n\nDone.")


if __name__ == '__main__':
    main()
