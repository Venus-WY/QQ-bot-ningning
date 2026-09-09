#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从《超神机械师》提取世界观名词知识库（增强版）。

策略（质量优先，数量越多越好）：
  1. jieba 词性：nr=人名、ns=地名、nt=机构 → 候选
  2. 规则后缀：科幻自造词（星/星系/刀/枪/机甲/术/之战/币…）→ 归类
  3. 2~3 字高频词 + 后缀匹配 → 补充 jieba 认不出的词
  4. 停用词表 + 频率 + 长度过滤 → 去掉普通词/虚词/动词短语

输出 : corpus/knowledge.yaml（分类 -> 名词列表，按频次降序）
"""

from __future__ import annotations

import argparse
import os
import re
from collections import Counter, defaultdict

import jieba
import jieba.posseg as pseg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DEFAULT_TXT = os.path.join(ROOT, "超神机械师 (齐佩甲).txt")
DEFAULT_OUT = os.path.join(ROOT, "corpus", "knowledge.yaml")

# 规则后缀：按后缀归类（科幻/星际/机械世界观）
SUFFIX_RULES = {
    "地点": [
        "星系", "星域", "星团", "星云", "星球", "星", "文明", "大陆", "位面",
        "宇宙", "基地", "区域", "维度", "帝国", "联邦", "共和国", "联盟",
        "城", "海", "山脉", "荒原", "遗迹", "巢穴", "边境",
    ],
    "装备": [
        "刀", "枪", "剑", "盾", "甲", "机甲", "机械臂", "动力臂", "炮", "舰",
        "战机", "飞船", "战舰", "装备", "武器", "装甲", "战车", "引擎", "核心",
        "模块", "外骨骼", "无人机", "卫星", "舰队", "母舰",
    ],
    "技能": [
        "术", "诀", "功法", "心法", "技能", "能力", "之力", "掌控", "领域",
        "天赋", "异能", "剑法", "刀法", "枪法", "秘术", "神术", "奥术", "魔法",
    ],
    "事件": [
        "之战", "战役", "战争", "事件", "危机", "之灾", "灾变", "协议", "条约",
        "革命", "起义", "入侵", "对决", "围剿", "战争",
    ],
    "知识": [
        "币", "货币", "粒子", "能量", "基因", "量子", "科技", "等级", "职业",
        "属性", "材料", "元素", "晶体", "合金", "药剂", "芯片", "程序", "系统",
        "引擎", "能源", "燃料", "矿石", "矿物", "资源",
    ],
}

# 停用词/过滤：普通词、虚词、代词、动词短语、口语（不属于世界观专名）
STOPWORDS = {
    # 虚词/代词/副词
    "的", "了", "是", "在", "有", "和", "就", "都", "而", "及", "与", "着",
    "我", "你", "他", "她", "它", "我们", "你们", "他们", "她们", "它们",
    "这", "那", "什么", "谁", "怎么", "为什么", "这样", "那样", "这些", "那些",
    "很", "又", "再", "也", "才", "只", "不", "没", "别", "非常", "比较",
    "已经", "正在", "立刻", "马上", "果然", "当然", "突然", "终于", "还是",
    "只是", "还有", "就是", "不是", "没有", "一样", "可以", "应该", "可能",
    # 动词短语（被 jieba 误标）
    "闻言", "明白", "说道", "问道", "想到", "觉得", "知道", "看到", "听到",
    "发现", "开始", "继续", "看着", "望着", "说着", "说着", "点头", "摇头",
    "开口", "开口", "说话", "回答", "询问", "解释", "表示", "认为",
    # 普通名词/泛词
    "玩家", "游戏", "世界", "时候", "东西", "事情", "问题", "方法", "办法",
    "想法", "看法", "说法", "做法", "打法", "无法", "没法", "普通", "和平",
    "汇报", "聊天", "报告", "消息", "情况", "结果", "原因", "目标", "计划",
    "能力", "技术", "战术", "战略", "战争", "战斗", "训练", "实力", "力量",
    "速度", "距离", "时间", "空间", "地方", "位置", "方向", "程度", "数量",
    "一个", "一种", "一些", "一点", "一下", "整个", "全部", "所有", "其他",
    # 额外噪音（被规则后缀误匹配的普通词）
    "立马", "矛盾", "一枪", "一刀", "一炮", "光辉", "越野车", "最大化", "深有体会",
    "付诸行动", "采取行动", "自由行动", "联合行动", "军事行动", "秘密行动",
}

# 已知核心世界观词（确保不遗漏，尤其 jieba 可能切错的）
KNOWN = {
    "地点": ["海蓝星", "破碎星环", "嘉顿星系", "古拉尔文明", "银灵文明", "歌朵拉", "黑星军团本部", "龙坦", "黯星", "西风星系", "圣约", "六国", "避难所", "苟斯特荒原"],
    "人物": ["韩萧", "海拉", "艾默丝", "霍莱德", "林维贤", "欧若拉", "剑者芙", "异神", "麦尼逊", "碧空悠悠", "单抽之王", "黄誉"],
    "装备": ["折叠战刀", "机械动力臂", "磁力切割刃", "高能粒子炮", "反重力推进器", "纳米装甲", "电磁步枪", "高频振荡刀", "幽能护盾"],
    "事件": ["萌芽组织", "异神之战", "海蓝星事件", "异化之灾", "黑幽灵的机械箱子", "星际战争", "进化图腾"],
    "技能": ["机械制造", "磁力掌控", "异能", "基因修复", "机械改造"],
    "知识": ["星海", "通用货币", "海蓝币", "信用点", "超A级", "A级", "B级", "C级", "副本", "职业", "属性", "经验", "技能书"],
}


def _chunks(text: str, size: int = 200000):
    for i in range(0, len(text), size):
        yield text[i:i + size]


def _add_core_dict():
    """把核心世界观词加入 jieba 词典，确保正确切分（避免「韩萧道」「韩萧笑」这类拼接）。"""
    for cat, names in KNOWN.items():
        for name in names:
            jieba.add_word(name, 100000)


def extract(text: str) -> dict[str, Counter]:
    cats: dict[str, Counter] = defaultdict(Counter)
    word_freq: Counter = Counter()

    _add_core_dict()

    # 1) jieba 词性
    for chunk in _chunks(text):
        for word, flag in pseg.cut(chunk):
            w = word.strip()
            if len(w) < 2:
                continue
            word_freq[w] += 1
            if flag == "nr":
                cats["人物"][w] += 1
            elif flag == "ns":
                cats["地点"][w] += 1
            elif flag == "nt":
                cats["事件"][w] += 1
            elif flag == "nz":
                cats["知识"][w] += 1

    # 2) 规则后缀（对全部词按后缀归类，比 jieba 词性更可靠）
    for w, f in word_freq.items():
        for cat, suffixes in SUFFIX_RULES.items():
            if any(w.endswith(s) for s in suffixes):
                cats[cat][w] += f

    # 3) 已知核心词兜底
    for cat, names in KNOWN.items():
        for name in names:
            cats[cat][name] = max(cats[cat][name], word_freq.get(name, 0) + 1)

    return cats


def _is_bad(w: str) -> bool:
    if w in STOPWORDS:
        return True
    # 纯数字/字母/标点
    if re.fullmatch(r"[0-9a-zA-Z\W_]+", w):
        return True
    # 含明显动词/语气（被误标的）
    if re.search(r"(闻言|明白|说道|问道|想到|觉得|知道|看到|听到|发现|开始|继续|看着|望着|说着|点头|摇头|开口|说话|回答|询问|解释|表示|认为|然后|接着|于是|但是|因为|所以)", w):
        return True
    return False


def _clean(cats: dict[str, Counter], min_freq: int) -> dict[str, list[str]]:
    core = {name for names in KNOWN.values() for name in names}
    out: dict[str, list[str]] = {}
    for cat, counter in cats.items():
        names = []
        for w, f in counter.most_common():
            w = w.strip()
            if w in core:
                # 核心词强制保留（不受频率/长度过滤影响）
                names.append(w)
                continue
            if len(w) < 2 or len(w) > 12:
                continue
            if _is_bad(w):
                continue
            if f < min_freq:
                continue
            names.append(w)
        out[cat] = names
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="提取超神机械师世界观名词知识库")
    ap.add_argument("--txt", default=DEFAULT_TXT)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--min-freq", type=int, default=2)
    args = ap.parse_args()

    print("读取小说...")
    text = open(args.txt, encoding="gb18030", errors="replace").read()
    print(f"小说 {len(text)} 字符，开始分词...")

    cats = extract(text)
    cleaned = _clean(cats, args.min_freq)

    import yaml
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    total = 0
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("# ===== 《超神机械师》世界观知识库 =====\n")
        f.write("# 分类：地点 / 人物 / 装备 / 事件 / 技能 / 知识\n")
        f.write("# 由 scripts/extract_knowledge.py 从原著提取，按出现频次降序。\n\n")
        for cat in ["地点", "人物", "装备", "事件", "技能", "知识"]:
            names = cleaned.get(cat, [])
            total += len(names)
            f.write(f"{cat}:\n")
            for n in names:
                f.write(f"  - {n}\n")
            f.write("\n")

    print(f"输出 → {args.out}")
    for cat in ["地点", "人物", "装备", "事件", "技能", "知识"]:
        print(f"  {cat}: {len(cleaned.get(cat, []))} 个")
    print(f"总计: {total} 个名词")
    return 0


if __name__ == "__main__":
    exit(main())
