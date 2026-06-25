"""
ACGTI 第 4 轮消融实验 - 补充：基于符号正确的 EI 优化

关键发现:
  - q25: sign=1 (E), q26: sign=1 (E), q36: sign=1 (E) — 移除它们的 EI 贡献能提升 EI 准确率
  - q28: sign=-1 (I), q12: sign=1 (E) — 放大能提升 EI
  - 原因: 归一化机制下，放大高质量题会稀释噪声题的贡献
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
        'SELECT self_mbti, confidence, answers_json '
        'FROM mbti_feedback WHERE answers_json IS NOT NULL AND predicted_mbti IS NOT NULL '
        'AND confidence >= ? ORDER BY created_at',
        (min_confidence,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


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


def build_dim_weights(questions, overrides, patch):
    """patch: dict of qid -> {dim: weight}, merged ON TOP of overrides"""
    result = {}
    for q in questions:
        qid = q['id']
        base = overrides.get(qid, {q['dimension']: q['sign']})
        if patch and qid in patch:
            merged = dict(base)
            merged.update(patch[qid])
            result[qid] = merged
        else:
            result[qid] = base
    return result


def run_batch(name, feedback_data, questions, overrides, patch, label=''):
    dwm = build_dim_weights(questions, overrides, patch)

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

        predicted = replay_mbti(questions, dwm, answers_list)
        total += 1
        if predicted == self_mbti:
            exact += 1

        for dim_idx, dim in enumerate(('E_I', 'S_N', 'T_F', 'J_P')):
            sl = self_mbti[dim_idx]
            pl = predicted[dim_idx]
            if sl == pl:
                dim_correct[dim] += 1
            dir_map = {
                'E_I': ('I', 'E', 'I->E'), 'S_N': ('N', 'S', 'N->S'),
                'T_F': ('T', 'F', 'T->F'), 'J_P': ('P', 'J', 'P->J'),
            }
            neg, pos, key = dir_map[dim]
            if sl == neg:
                dim_dir[dim][f'{neg}_total'] += 1
                if pl == pos:
                    dim_dir[dim][key] += 1
            else:
                dim_dir[dim][f'{pos}_total'] += 1
                rev_key = f'{pos}->{neg}'
                if pl == neg:
                    dim_dir[dim][rev_key] = dim_dir[dim].get(rev_key, 0) + 1

    if total == 0:
        return None

    r = {
        'match': exact * 100 / total,
        'EI': dim_correct['E_I'] * 100 / total,
        'SN': dim_correct['S_N'] * 100 / total,
        'TF': dim_correct['T_F'] * 100 / total,
        'JP': dim_correct['J_P'] * 100 / total,
    }
    ie = dim_dir['E_I']
    tf = dim_dir['T_F']
    jp = dim_dir['J_P']

    ie_rate = ie['I->E'] * 100 / max(1, ie['I_total'])
    tf_rate = tf['T->F'] * 100 / max(1, tf['T_total'])
    jp_rate = jp['P->J'] * 100 / max(1, jp['P_total'])

    print(f"  [{name:30s}] match={r['match']:5.1f}% "
          f"EI={r['EI']:5.1f}% SN={r['SN']:5.1f}% TF={r['TF']:5.1f}% JP={r['JP']:5.1f}% | "
          f"I->E={ie_rate:4.1f}% T->F={tf_rate:4.1f}% P->J={jp_rate:4.1f}% | {label}")

    return r


def main():
    min_conf = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    questions = load_questions()
    overrides = load_overrides()
    feedback = load_feedback(min_conf)
    print(f"Round 4b: EI-focused ablation (n={len(feedback)}, conf>={min_conf})\n")

    # q12: sign=1(E), q25: sign=1(E), q26: sign=1(E), q28: sign=-1(I), q36: sign=1(E), q39: sign=1(E)

    print("--- Baseline ---")
    run_batch('0.3.0-baseline', feedback, questions, {}, None, 'no overrides')
    run_batch('0.3.3-current', feedback, questions, overrides, None, 'current production')

    print("\n--- A: EI noise removal (set E_I=0 for noisy questions) ---")
    run_batch('A1-no-q25', feedback, questions, overrides,
              {'q25': {'E_I': 0}}, 'q25 E_I:0')
    run_batch('A2-no-q26', feedback, questions, overrides,
              {'q26': {'E_I': 0}}, 'q26 E_I:0')
    run_batch('A3-no-q36', feedback, questions, overrides,
              {'q36': {'E_I': 0}}, 'q36 E_I:0')
    run_batch('A4-no-q25+q26', feedback, questions, overrides,
              {'q25': {'E_I': 0}, 'q26': {'E_I': 0}}, 'q25+q26 E_I:0')
    run_batch('A5-no-q25+q36', feedback, questions, overrides,
              {'q25': {'E_I': 0}, 'q36': {'E_I': 0}}, 'q25+q36 E_I:0')
    run_batch('A6-no-q26+q36', feedback, questions, overrides,
              {'q26': {'E_I': 0}, 'q36': {'E_I': 0}}, 'q26+q36 E_I:0')
    run_batch('A7-no-q25+q26+q36', feedback, questions, overrides,
              {'q25': {'E_I': 0}, 'q26': {'E_I': 0}, 'q36': {'E_I': 0}}, 'q25+q26+q36 E_I:0')

    print("\n--- B: EI amplification (scale strong signal questions) ---")
    # q28: sign=-1, so 2x means E_I:-2 (stronger I push)
    run_batch('B1-q28x2', feedback, questions, overrides,
              {'q28': {'E_I': -2}}, 'q28 E_I:-2 (stronger I)')
    run_batch('B2-q28x1.5', feedback, questions, overrides,
              {'q28': {'E_I': -1.5}}, 'q28 E_I:-1.5')
    # q12: sign=1, so 2x means E_I:2 (stronger E push, but helps via normalization dilution)
    run_batch('B3-q12x2', feedback, questions, overrides,
              {'q12': {'E_I': 2}}, 'q12 E_I:2 (stronger E, dilutes noise)')
    run_batch('B4-q12x1.5', feedback, questions, overrides,
              {'q12': {'E_I': 1.5}}, 'q12 E_I:1.5')
    # Combined amplification
    run_batch('B5-q28x2+q12x2', feedback, questions, overrides,
              {'q28': {'E_I': -2}, 'q12': {'E_I': 2}}, 'q28:-2 + q12:2')
    run_batch('B6-q28x1.5+q12x1.5', feedback, questions, overrides,
              {'q28': {'E_I': -1.5}, 'q12': {'E_I': 1.5}}, 'q28:-1.5 + q12:1.5')

    print("\n--- C: Noise removal + amplification ---")
    run_batch('C1-A7+B5', feedback, questions, overrides,
              {'q25': {'E_I': 0}, 'q26': {'E_I': 0}, 'q36': {'E_I': 0},
               'q28': {'E_I': -2}, 'q12': {'E_I': 2}},
              'remove noise + amplify')
    run_batch('C2-A7+B6', feedback, questions, overrides,
              {'q25': {'E_I': 0}, 'q26': {'E_I': 0}, 'q36': {'E_I': 0},
               'q28': {'E_I': -1.5}, 'q12': {'E_I': 1.5}},
              'remove noise + moderate amplify')
    # Just noise removal + q28 amplify
    run_batch('C3-A7+q28x2', feedback, questions, overrides,
              {'q25': {'E_I': 0}, 'q26': {'E_I': 0}, 'q36': {'E_I': 0},
               'q28': {'E_I': -2}},
              'remove noise + q28x2')
    # Just noise removal + q12 amplify
    run_batch('C4-A7+q12x2', feedback, questions, overrides,
              {'q25': {'E_I': 0}, 'q26': {'E_I': 0}, 'q36': {'E_I': 0},
               'q12': {'E_I': 2}},
              'remove noise + q12x2')

    print("\n--- D: Conservative approaches ---")
    # Just remove the two noisiest (q26 and q36)
    run_batch('D1-no-q26+q36', feedback, questions, overrides,
              {'q26': {'E_I': 0}, 'q36': {'E_I': 0}}, 'only q26+q36 removed')
    run_batch('D2-no-q26+q36+q28x1.5', feedback, questions, overrides,
              {'q26': {'E_I': 0}, 'q36': {'E_I': 0}, 'q28': {'E_I': -1.5}},
              'q26+q36 removed + q28x1.5')
    run_batch('D3-no-q25+q36+q28x1.5', feedback, questions, overrides,
              {'q25': {'E_I': 0}, 'q36': {'E_I': 0}, 'q28': {'E_I': -1.5}},
              'q25+q36 removed + q28x1.5')

    print("\n--- E: Best candidates with fine-tuning ---")
    # Try different amplification levels with noise removal
    for q28_w in [-1.5, -2.0]:
        for q12_w in [1.5, 2.0]:
            run_batch(f'E-q28:{q28_w}+q12:{q12_w}', feedback, questions, overrides,
                      {'q25': {'E_I': 0}, 'q26': {'E_I': 0}, 'q36': {'E_I': 0},
                       'q28': {'E_I': q28_w}, 'q12': {'E_I': q12_w}},
                      f'noise removed + q28:{q28_w} + q12:{q12_w}')

    # Also try with only partial noise removal
    run_batch('E2-partial', feedback, questions, overrides,
              {'q26': {'E_I': 0}, 'q36': {'E_I': 0},
               'q28': {'E_I': -2}, 'q12': {'E_I': 2}},
              'partial noise + amplify')

    print("\nDone.")


if __name__ == '__main__':
    main()
