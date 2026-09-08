# -*- coding: utf-8 -*-
"""
创发第一轮面试 —— 数据整合与「总均分汇总」脚本
================================================
输入（需放在脚本上一级目录，即项目根目录）：
  - 打分毛数据.xlsx                       （5 位评委，每人一个 sheet）
  - 创发第一轮面试安排（前半.xlsx          （安排表：电话 / 性别，覆盖序号 1~54）
  - 创发第一轮面试安排（后半.xlsx          （被面试者信息：电话 / 性别，覆盖序号 56~80）

输出：
  - 创发第一轮面试_总均分汇总.xlsx   （最终大表，已排序、着色、冻结表头）

计分公式（依据《评分评价依据.docx》，五个维度权重 25/20/15/20/20）：
  基础总分 = 5×动机 + 4×参与度 + 3×融入 + 4×应变创新 + 4×氛围感染力   （满分 100）
  最终得分 = 基础总分 + 加分项                                        （加分 0~10，上限 10）
  一票否决（是）→ 最终得分记为 0

分类规则（与业务口径一致）：
  0 位评委打分 = 缺勤
  1~4 位评委打分 = 一票否决（有人不满意）
  5 位评委打分 = 正常，取 5 位评委最终得分的等权平均作为「总均分」
"""
import os
from xlsx_reader import load_xlsx

# 五个维度的权重（折算后每档对应的分数）：
# 维度满分 25/20/15/20/20 -> 1~5 档 -> 每档 5/4/3/4/4 分
W = [5, 4, 3, 4, 4]

# 打分表列号（1 起）：
# 1 序号 | 2 时间 | 3 姓名 | 4 性别 | 5~9 五维 | 10 基础总分(空) | 11 加分项 | 12 最终得分(空) | 13 一票否决 | 14 录用建议
COL_DIM = (5, 6, 7, 8, 9)
COL_BONUS = 11
COL_VETO = 13


def basic_score(dims):
    """五个 1~5 档评分 -> 基础总分（0~100）。"""
    return sum(W[k] * dims[k] for k in range(5))


def final_score(dims, bonus, veto):
    """基础总分 + 加分项；触发一票否决则记 0。"""
    if veto == '是':
        return 0.0
    return basic_score(dims) + float(bonus or 0)


def key_of(name, seq):
    """王峥铖在序号 33 和 59 重复出现，用序号区分后再合并。"""
    return '王峥铖({})'.format(seq) if name == '王峥铖' else name


def norm_phone(v):
    """把电话统一成纯数字字符串（兼容数字被存成科学计数法的情况）。"""
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        f = float(s)
        if f == int(f) and abs(f) >= 1e9:
            return str(int(f))
    except ValueError:
        pass
    d = re.sub(r'\D', '', s)
    return d if len(d) >= 7 else None


def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # 1) 评委打分
    score = load_xlsx(os.path.join(base, '打分毛数据.xlsx'))
    judges = list(score.keys())                      # 5 位评委 = 5 个 sheet
    first = score[judges[0]]

    # 用第一位评委（刘颢鸣，覆盖序号 1~80 最全）建立候选人名册
    canon = []
    for r in sorted(first):
        c = first[r]
        name = c.get(3, '')
        if not name or name in ('姓名', '序号'):
            continue
        canon.append(dict(key=key_of(name, c.get(1, '')),
                          seq=c.get(1, ''),
                          name=name,
                          gender=c.get(4, '')))

    # 逐评委计算最终得分
    judge_final = {j: {} for j in judges}
    for j in judges:
        for r in sorted(score[j]):
            c = score[j][r]
            name = c.get(3, '')
            if not name or name in ('姓名', '序号'):
                continue
            key = key_of(name, c.get(1, ''))
            try:
                dims = [int(c.get(k, '')) for k in COL_DIM]
            except (TypeError, ValueError):
                continue
            if len(dims) == 5:                       # 五维齐全才算该评委打分
                judge_final[j][key] = final_score(dims, c.get(COL_BONUS, ''), c.get(COL_VETO, ''))

    # 2) 电话 / 性别来源
    sched = load_xlsx(os.path.join(base, '创发第一轮面试安排（前半.xlsx'))
    phone_sched, gender_sched = {}, {}
    for rows in sched.values():
        for r in sorted(rows):
            c = rows[r]
            name = c.get(1, '')
            if not name or name == '姓名':
                continue
            p = norm_phone(c.get(6, ''))
            if p:
                phone_sched.setdefault(name, p)
            if c.get(2, ''):
                gender_sched.setdefault(name, c.get(2, ''))

    app = load_xlsx(os.path.join(base, '创发第一轮面试安排（后半.xlsx'))
    phone_app, gender_app = {}, {}
    for rows in app.values():
        for r in sorted(rows):
            c = rows[r]
            name = c.get(2, '')
            if not name or name == '姓名':
                continue
            p = norm_phone(c.get(11, ''))
            if p:
                phone_app.setdefault(name, p)
            if c.get(3, ''):
                gender_app.setdefault(name, c.get(3, ''))

    phone_all = dict(phone_sched, **phone_app)
    gender_extra = dict(gender_sched, **gender_app)

    # 3) 汇总、分类
    records = []
    for cd in canon:
        key = cd['key']
        if key == '王峥铖(59)':        # 与序号 33 重复（电话一致），合并掉
            continue
        scores = {j: judge_final[j].get(key) for j in judges}
        valid = [v for v in scores.values() if v is not None]
        n = len(valid)
        status = '正常' if n == 5 else ('一票否决' if n >= 1 else '缺勤')
        mean = round(sum(valid) / n, 2) if valid else None
        gender = cd['gender'] or gender_extra.get(cd['name'], '')
        phone = phone_all.get(cd['name'], '')
        records.append(dict(seq=cd['seq'], name=cd['name'], gender=gender, phone=phone,
                            scores=scores, n=n, status=status, mean=mean))

    # 特殊修正与备注
    notes = {
        '王峥铖': '序号59与33重复(电话相同)，已合并为序号33；59另有赵轩62/魏国萍64两笔',
        '张一凡': '性别记录不一致(4位评委记女)；未在安排表、无电话、时间与黄一迪冲突',
    }
    for r in records:
        if r['name'] == '张一凡' and r['gender'] == '男':
            r['gender'] = '女'
        r['note'] = notes.get(r['name'], '')

    # 4) 排序：正常按均分降序，一票否决 / 缺勤按序号升序排后
    def seq_key(s):
        try:
            return int(s)
        except (TypeError, ValueError):
            return 9999

    normal = [r for r in records if r['status'] == '正常']
    veto = [r for r in records if r['status'] == '一票否决']
    absent = [r for r in records if r['status'] == '缺勤']
    normal.sort(key=lambda x: (-(x['mean'] or 1), seq_key(x['seq'])))
    veto.sort(key=lambda x: seq_key(x['seq']))
    absent.sort(key=lambda x: seq_key(x['seq']))
    ordered = normal + veto + absent

    # 5) 导出 xlsx
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = Workbook()
    ws = wb.active
    ws.title = '总均分汇总'
    headers = ['序号', '姓名', '性别', '电话', '刘颢鸣', '许程棋', '刘弈宏', '赵轩', '魏国萍', '总均分', '状态', '备注']
    ws.append(headers)
    for c in ws[1]:
        c.font = Font(bold=True, color='FFFFFF')
        c.fill = PatternFill('solid', fgColor='4472C4')
        c.alignment = Alignment(horizontal='center')

    for r in ordered:
        s = r['scores']
        ws.append([r['seq'], r['name'], r['gender'], r['phone'],
                   s['刘颢鸣'] if s['刘颢鸣'] is not None else '',
                   s['许程棋'] if s['许程棋'] is not None else '',
                   s['刘弈宏'] if s['刘弈宏'] is not None else '',
                   s['赵轩'] if s['赵轩'] is not None else '',
                   s['魏国萍'] if s['魏国萍'] is not None else '',
                   r['mean'] if r['mean'] is not None else '',
                   r['status'], r['note']])

    color = {'正常': ('C6EFCE', '006100'), '一票否决': ('FFEB9C', '9C6500'), '缺勤': ('FFC7CE', '9C0006')}
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=11, max_col=11):
        fill, font_color = color.get(row[0].value, ('FFFFFF', '000000'))
        row[0].fill = PatternFill('solid', fgColor=fill)
        row[0].font = Font(color=font_color, bold=True)

    for i, w in enumerate([6, 10, 6, 14, 8, 8, 8, 8, 8, 9, 10, 30], 1):
        ws.column_dimensions[chr(64 + i)].width = w
    ws.freeze_panes = 'A2'

    out = os.path.join(base, '创发第一轮面试_总均分汇总.xlsx')
    wb.save(out)
    print('正常 {} 人 / 一票否决 {} 人 / 缺勤 {} 人，合计 {} 人'.format(
        len(normal), len(veto), len(absent), len(ordered)))
    print('已写出：', out)


if __name__ == '__main__':
    import re
    main()
