"""
ACGTI 两层验证：4 组消融 + 分布检查
A: 去噪 only (q25/q26/q36 -> E_I:0)
B: 去噪 + q28:-2
C: 去噪 + q12:2
D: 去噪 + q28:-2 + q12:2 (当前提交)
E: 去噪 + q28:-1.5 (保守版)
"""
import json, sqlite3, os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'analysis', 'acgti_feedback.db')
QUESTIONS_PATH = os.path.join(os.path.dirname(__file__), '..', 'src', 'data', 'questions.json')

DIMENSION_LETTERS = {
    'E_I': ('E', 'I'), 'S_N': ('S', 'N'), 'T_F': ('T', 'F'), 'J_P': ('J', 'P'),
}

# 0.3.3 original overrides (hardcoded to avoid reading modified file)
OVERRIDES_033 = {
    'q2': {'J_P': -1.15},
    'q5': {'J_P': -0.4},
    'q8': {'J_P': -1.2},
    'q20': {'T_F': -0.5},
    'q23': {'E_I': -1, 'S_N': -0.7},
    'q29': {'T_F': 1.5},
    'q31': {'J_P': -0.65},
    'q35': {'S_N': -0.65},
    'q37': {'S_N': -0.8, 'J_P': 0.25},
    'q38': {'J_P': 0},
}

TYPE_TO_ARCH = {
    'INTJ': 'shadow-strategist', 'INTP': 'icebound-observer',
    'ENTJ': 'oathbound-captain', 'ENTP': 'trickster-orbit',
    'INFJ': 'gentle-healer', 'INFP': 'moonlit-guardian',
    'ENFJ': 'luminous-lead', 'ENFP': 'trickster-orbit',
    'ISTJ': 'moonlit-guardian', 'ISFJ': 'gentle-healer',
    'ESTJ': 'oathbound-captain', 'ESFJ': 'luminous-lead',
    'ISTP': 'icebound-observer', 'ISFP': 'moonlit-guardian',
    'ESTP': 'chaos-spark', 'ESFP': 'chaos-spark',
}


def load_questions():
    with open(QUESTIONS_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_feedback():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        'SELECT self_mbti, confidence, answers_json FROM mbti_feedback '
        'WHERE answers_json IS NOT NULL AND predicted_mbti IS NOT NULL AND confidence >= 4 '
        'ORDER BY created_at'
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def parse_answers(raw, qs):
    try:
        d = json.loads(raw)
    except:
        return None
    if isinstance(d, list):
        a = [0] * len(qs)
        for item in d:
            qid = item.get('questionId', '')
            val = item.get('answerValue', 0)
            try:
                idx = int(qid.replace('q', '')) - 1
            except:
                continue
            if 0 <= idx < len(a):
                a[idx] = val
        return a
    return None


def replay(qs, dwm, answers):
    raw = {'E_I': 0, 'S_N': 0, 'T_F': 0, 'J_P': 0}
    dmax = {
        'E_I': {'pos': 0, 'neg': 0}, 'S_N': {'pos': 0, 'neg': 0},
        'T_F': {'pos': 0, 'neg': 0}, 'J_P': {'pos': 0, 'neg': 0},
    }
    for i, q in enumerate(qs):
        if i >= len(answers):
            break
        a = answers[i]
        if not isinstance(a, (int, float)) or a < -3 or a > 3:
            continue
        weights = dwm.get(q['id'], {q['dimension']: q['sign']})
        for dim, w in weights.items():
            if w == 0:
                continue
            raw[dim] += a * w
            if w > 0:
                dmax[dim]['pos'] += 3 * w
            else:
                dmax[dim]['neg'] += 3 * abs(w)
    code = ''
    for dim in ('E_I', 'S_N', 'T_F', 'J_P'):
        r = raw[dim]
        s = r / max(1, dmax[dim]['pos']) if r >= 0 else r / max(1, dmax[dim]['neg'])
        code += DIMENSION_LETTERS[dim][0] if s >= 0 else DIMENSION_LETTERS[dim][1]
    return code


def build_dwm(qs, base, patch):
    result = {}
    for q in qs:
        qid = q['id']
        b = base.get(qid, {q['dimension']: q['sign']})
        if patch and qid in patch:
            m = dict(b)
            m.update(patch[qid])
            result[qid] = m
        else:
            result[qid] = b
    return result


def run(name, fb, qs, base, patch):
    dwm = build_dwm(qs, base, patch)
    total = 0
    exact = 0
    dc = {'E_I': 0, 'S_N': 0, 'T_F': 0, 'J_P': 0}
    dd = {
        'E_I': {'I->E': 0, 'E->I': 0, 'It': 0, 'Et': 0},
        'S_N': {'N->S': 0, 'S->N': 0, 'Nt': 0, 'St': 0},
        'T_F': {'T->F': 0, 'F->T': 0, 'Tt': 0, 'Ft': 0},
        'J_P': {'P->J': 0, 'J->P': 0, 'Pt': 0, 'Jt': 0},
    }
    pred_dist = {}
    self_dist = {}
    archetype_dist = {}

    for row in fb:
        sm = row['self_mbti']
        if not sm or len(sm) != 4:
            continue
        al = parse_answers(row['answers_json'], qs)
        if al is None:
            continue
        pred = replay(qs, dwm, al)
        total += 1
        if pred == sm:
            exact += 1
        self_dist[sm] = self_dist.get(sm, 0) + 1
        pred_dist[pred] = pred_dist.get(pred, 0) + 1
        arch = TYPE_TO_ARCH.get(pred, 'unknown')
        archetype_dist[arch] = archetype_dist.get(arch, 0) + 1

        for di, dim in enumerate(('E_I', 'S_N', 'T_F', 'J_P')):
            sl = sm[di]
            pl = pred[di]
            if sl == pl:
                dc[dim] += 1
            dm = {'E_I': ('I', 'E'), 'S_N': ('N', 'S'), 'T_F': ('T', 'F'), 'J_P': ('P', 'J')}
            neg, pos = dm[dim]
            if sl == neg:
                dd[dim][f'{neg}t'] += 1
                if pl == pos:
                    dd[dim][f'{neg}->{pos}'] += 1
            else:
                dd[dim][f'{pos}t'] += 1
                if pl == neg:
                    dd[dim][f'{pos}->{neg}'] += 1

    if total == 0:
        return

    pct = {d: dc[d] * 100 / total for d in dc}
    ie = dd['E_I']
    tf = dd['T_F']
    jp = dd['J_P']
    pred_e = sum(v for k, v in pred_dist.items() if k[0] == 'E')
    pred_i = sum(v for k, v in pred_dist.items() if k[0] == 'I')
    self_e = sum(v for k, v in self_dist.items() if k[0] == 'E')
    self_i = sum(v for k, v in self_dist.items() if k[0] == 'I')

    print(f'\n  [{name}]')
    print(f'    match={exact * 100 / total:.1f}%  EI={pct["E_I"]:.1f}%  SN={pct["S_N"]:.1f}%  TF={pct["T_F"]:.1f}%  JP={pct["J_P"]:.1f}%')
    print(f'    I->E={ie["I->E"] * 100 / max(1, ie["It"]):.1f}%  E->I={ie["E->I"] * 100 / max(1, ie["Et"]):.1f}%  '
          f'T->F={tf["T->F"] * 100 / max(1, tf["Tt"]):.1f}%  P->J={jp["P->J"] * 100 / max(1, jp["Pt"]):.1f}%')
    print(f'    pred E:I = {pred_e}:{pred_i} ({pred_e * 100 / (pred_e + pred_i):.1f}% / {pred_i * 100 / (pred_e + pred_i):.1f}%)')
    print(f'    self E:I = {self_e}:{self_i} ({self_e * 100 / (self_e + self_i):.1f}% / {self_i * 100 / (self_e + self_i):.1f}%)')
    top_pred = sorted(pred_dist.items(), key=lambda x: -x[1])[:5]
    print(f'    top5 pred: {top_pred}')
    top_arch = sorted(archetype_dist.items(), key=lambda x: -x[1])
    arch_total = sum(archetype_dist.values())
    arch_str = '  '.join(f'{k}={v * 100 / arch_total:.1f}%' for k, v in top_arch)
    print(f'    archetypes: {arch_str}')

    return {
        'match': exact * 100 / total,
        'EI': pct['E_I'],
        'ie': ie,
    }


def main():
    questions = load_questions()
    feedback = load_feedback()
    print(f'Two-layer verification (n={len(feedback)}, conf>=4)')

    print('\n' + '=' * 60)
    print('  BASELINE: 0.3.3 线上权重')
    print('=' * 60)
    run('0.3.3-baseline', feedback, questions, OVERRIDES_033, None)

    print('\n' + '=' * 60)
    print('  A: 去噪 only (q25/q26/q36 -> E_I:0)')
    print('=' * 60)
    run('A-noise-only', feedback, questions, OVERRIDES_033,
        {'q25': {'E_I': 0}, 'q26': {'E_I': 0}, 'q36': {'E_I': 0}})

    print('\n' + '=' * 60)
    print('  B: 去噪 + q28:-2')
    print('=' * 60)
    run('B-noise+q28', feedback, questions, OVERRIDES_033,
        {'q25': {'E_I': 0}, 'q26': {'E_I': 0}, 'q36': {'E_I': 0}, 'q28': {'E_I': -2}})

    print('\n' + '=' * 60)
    print('  C: 去噪 + q12:2')
    print('=' * 60)
    run('C-noise+q12', feedback, questions, OVERRIDES_033,
        {'q25': {'E_I': 0}, 'q26': {'E_I': 0}, 'q36': {'E_I': 0}, 'q12': {'E_I': 2}})

    print('\n' + '=' * 60)
    print('  D: 去噪 + q28:-2 + q12:2 (当前提交)')
    print('=' * 60)
    run('D-full-C1', feedback, questions, OVERRIDES_033,
        {'q25': {'E_I': 0}, 'q26': {'E_I': 0}, 'q36': {'E_I': 0},
         'q28': {'E_I': -2}, 'q12': {'E_I': 2}})

    print('\n' + '=' * 60)
    print('  E: 去噪 + q28:-1.5 (保守版)')
    print('=' * 60)
    run('E-noise+q28-1.5', feedback, questions, OVERRIDES_033,
        {'q25': {'E_I': 0}, 'q26': {'E_I': 0}, 'q36': {'E_I': 0}, 'q28': {'E_I': -1.5}})

    print('\n\nDone.')


if __name__ == '__main__':
    main()
