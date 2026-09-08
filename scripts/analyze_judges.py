# -*- coding: utf-8 -*-
"""
创发第一轮面试 —— 评委打分特征与一致性分析
================================================
输出五块内容：
  1. 各评委整体统计（打分人数、均分、标准差、极值、加分行为、5 分使用频率）
  2. 各评委五维打分均值（用于观察某评委在某个维度上偏松/偏严）
  3. 评委「宽松度」与「共识相关性」（仅取 5 位评委都打分的候选人）
  4. 评委两两相关系数矩阵
  5. 三种加权方案（等权平均 / 去最高最低 / z-score 标准化）的 TOP20 对比

运行：python analyze_judges.py
"""
import os
import statistics as st
from xlsx_reader import load_xlsx

W = [5, 4, 3, 4, 4]
COL_DIM = (5, 6, 7, 8, 9)
COL_BONUS = 11
COL_VETO = 13


def basic(dims):
    return sum(W[k] * dims[k] for k in range(5))


def final(dims, bonus, veto):
    if veto == '是':
        return 0.0
    return basic(dims) + float(bonus or 0)


def key_of(name, seq):
    return '王峥铖({})'.format(seq) if name == '王峥铖' else name


def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    score = load_xlsx(os.path.join(base, '打分毛数据.xlsx'))
    judges = list(score.keys())

    # 逐评委：dims 原始档位 + bonus + 最终得分
    raw = {j: {} for j in judges}      # key -> {'d':[...], 'bonus':str, 'veto':str}
    for j in judges:
        for r in sorted(score[j]):
            c = score[j][r]
            name = c.get(3, '')
            if not name or name in ('姓名', '序号'):
                continue
            key = key_of(name, c.get(1, ''))
            raw[j][key] = dict(d=[c.get(k, '') for k in COL_DIM],
                               bonus=c.get(COL_BONUS, ''),
                               veto=c.get(COL_VETO, ''))

    final_score = {j: {} for j in judges}
    for j in judges:
        for key, v in raw[j].items():
            try:
                dims = [int(x) for x in v['d']]
            except (TypeError, ValueError):
                continue
            if len(dims) == 5:
                final_score[j][key] = final(dims, v['bonus'], v['veto'])

    def bar(rows):
        print('-' * 100)

    # ===== 1. 整体统计 =====
    bar(None)
    print('【1】各评委整体统计（最终得分 = 基础总分 + 加分项）')
    print('评委 | 打分人数 | 均分 | 标准差 | 最低 | 最高 | 给加分人数 | 加分均值 | 打5分/五维总数')
    for j in judges:
        vals = list(final_score[j].values())
        n = len(vals)
        if n == 0:
            print(j, '| 0'); continue
        bonus_vals = [float(v['bonus']) for v in raw[j].values() if v['bonus'] not in ('', None)]
        fives = sum(1 for v in raw[j].values() for x in v['d'] if x == '5')
        total = sum(1 for v in raw[j].values() for x in v['d'])
        print('{} | {} | {:.2f} | {:.2f} | {:.1f} | {:.1f} | {} | {:.2f} | {}/{}'.format(
            j, n, st.mean(vals), st.pstdev(vals), min(vals), max(vals),
            len(bonus_vals), (sum(bonus_vals) / len(bonus_vals) if bonus_vals else 0),
            fives, total))

    # ===== 2. 五维均值 =====
    bar(None)
    print('【2】各评委五维打分均值（1~5 档）')
    print('评委 | 动机(25) | 参与度(20) | 融入(15) | 应变创新(20) | 氛围(20)')
    for j in judges:
        dims = [[] for _ in range(5)]
        for v in raw[j].values():
            for k, x in enumerate(v['d']):
                try:
                    dims[k].append(int(x))
                except (TypeError, ValueError):
                    pass
        parts = [j] + ['{:.2f}'.format(st.mean(d)) if d else '-' for d in dims]
        print(' | '.join(parts))

    # ===== 3~4. 仅 5 评委齐全的候选人 =====
    full = [k for k in final_score[judges[0]] if all(k in final_score[j] for j in judges)]
    bar(None)
    print('【3】宽松度 & 与「共识」的相关性（5 评委齐全的 {} 人）'.format(len(full)))
    overall = st.mean([final_score[j][k] for j in judges for k in full])
    print('评委 | 均分 | 宽松度偏差(相对总均{:.2f}) | 与共识相关系数r | 与共识平均绝对差'.format(overall))
    for j in judges:
        own = [final_score[j][k] for k in full]
        cons = [st.mean([final_score[o][k] for o in judges if o != j]) for k in full]
        r = st.correlation(own, cons)
        mad = st.mean([abs(own[i] - cons[i]) for i in range(len(own))])
        print('{} | {:.2f} | {:+.2f} | {:.3f} | {:.2f}'.format(
            j, st.mean(own), st.mean(own) - overall, r, mad))

    bar(None)
    print('【4】评委两两相关系数矩阵（5 评委齐全）')
    print('        ' + '  '.join(j[:2] for j in judges))
    for a in judges:
        row = [a[:2]]
        for b in judges:
            if a == b:
                row.append(' - ')
            else:
                row.append('{:.2f}'.format(st.correlation(
                    [final_score[a][k] for k in full], [final_score[b][k] for k in full])))
        print('  '.join(row))

    # ===== 5. 加权方案对比 =====
    bar(None)
    print('【5】不同加权方案 TOP20（5 评委齐全）')

    def show(title, sc):
        ranked = sorted(sc.items(), key=lambda x: -x[1])
        print('--- {} ---'.format(title))
        print(' | '.join('{}({:.2f})'.format(k, v) for k, v in ranked[:20]))

    show('等权平均', {k: st.mean([final_score[j][k] for j in judges]) for k in full})
    show('去最高最低(3评委均值)', {
        k: st.mean(sorted([final_score[j][k] for j in judges])[1:4]) for k in full})

    z = {}
    for j in judges:
        vals = [final_score[j][k] for k in full]
        m, s = st.mean(vals), st.pstdev(vals)
        z[j] = {k: (final_score[j][k] - m) / s if s > 0 else 0 for k in full}
    show('z-score标准化(映射75±15)', {
        k: 75 + 15 * st.mean([z[j][k] for j in judges]) for k in full})


if __name__ == '__main__':
    main()
