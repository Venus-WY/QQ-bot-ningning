# -*- coding: utf-8 -*-
"""分析《超神机械师》txt 的对话格式，为提取韩萧语料做准备。"""
import re
from collections import Counter

path = r'D:\QQBot\QQ-bot-ningning\超神机械师 (齐佩甲).txt'
text = open(path, encoding='gb18030', errors='replace').read()
lines = text.split('\n')
print(f'总行数: {len(lines)}, 总字数: {len(text)}')

# 1. 引号类型统计
print('\n=== 引号统计 ===')
for ch in ['“', '”', '「', '」', '"', "'", '‘', '’']:
    print(f'  {ch!r}: {text.count(ch)}')

# 2. 韩萧后面的动词（说话/心理标记）
print('\n=== "韩萧" 后跟动词统计 ===')
verbs = Counter()
for m in re.finditer(r'韩萧\s*([\u4e00-\u9fff]{1,3})[道说喊问答叫喝嚷笑叹骂嘀咕沉吟](?:道)?[:：]', text):
    verbs[m.group(1)] += 1
for v, n in verbs.most_common(30):
    print(f'  {v}...: {n}')

# 3. 韩萧 + 心理/说话动词（不带冒号，如 "韩萧吐槽"）
print('\n=== 韩萧+心理/动作动词（无冒号）统计 ===')
verbs2 = Counter()
for m in re.finditer(r'韩萧\s*([\u4e00-\u9fff]{2,4})', text):
    w = m.group(1)
    if any(k in w for k in ['道', '说', '想', '暗', '腹', '吐', '嘀咕', '自语', '叹', '笑', '骂', '问', '答', '喊']):
        verbs2[w] += 1
for v, n in verbs2.most_common(30):
    print(f'  {v}: {n}')

# 4. 抽几段韩萧对话看结构
print('\n=== 韩萧对话示例（含引号） ===')
count = 0
for line in lines:
    if '韩萧' in line and ('“' in line or '「' in line):
        print('  ', line.strip()[:80])
        count += 1
        if count >= 15:
            break
