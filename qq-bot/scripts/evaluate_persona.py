#!/usr/bin/env python3
"""
评测绫地宁宁人格：跑测试场景 → 生成回复 → 5 维打分。

五个维度：
  character_consistency  角色一致性：是否像宁宁
  language_style         语言辨识度：是否有宁宁的语言特征
  naturalness            自然程度：是否自然、不像 AI/客服
  qq_adaptation          群聊适应性：不默认恋爱、不堆原作设定、不越界
  repetition             反套路度：是否有新鲜感、不套公式（5=不套路）

产出（corpus/eval/ 下）：
  scenarios.json   测试场景（60 个，10 类）
  results.jsonl    每条场景的回复 + 各维得分
  report.md        汇总报告（总均分 / 分情境 / 最差案例 / 客观重复度）

用法 :
  python scripts/evaluate_persona.py --limit 10         # 先跑 10 个验证
  python scripts/evaluate_persona.py                    # 全量 60 个
  python scripts/evaluate_persona.py --no-fewshot       # 消融：去掉 few-shot 看影响
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
QQ_BOT = os.path.join(ROOT, "qq-bot")
CORPUS = os.path.join(ROOT, "corpus")
OUT_DIR = os.path.join(CORPUS, "eval")

# 复用生产环境的人格组装逻辑（nene_persona 已自包含，无相对依赖）
sys.path.insert(0, os.path.join(QQ_BOT, ".venv", "Lib", "site-packages"))
sys.path.insert(0, os.path.join(QQ_BOT, "src", "plugins", "qqbot"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(QQ_BOT, ".env"))

import httpx2 as httpx  # noqa: E402
from openai import OpenAI  # noqa: E402
import nene_persona  # noqa: E402

SCENARIOS_PATH = os.path.join(OUT_DIR, "scenarios.json")

DIMS = [
    "character_consistency", "language_style", "naturalness",
    "qq_adaptation", "repetition",
]

JUDGE_SYSTEM = (
    "你是角色扮演评测专家。给宁宁（绫地宁宁，《魔女的夜宴》女主）在 QQ 群里的一条回复打分。\n"
    "宁宁参考特质：温柔体贴但害羞傲娇、认真负责、被夸会谦虚否认、被调侃会嗔怪回击"
    "（如「下流」「坏心眼」）、短句多、犹豫用省略号、对陌生人礼貌疏离。\n"
    "五个维度各打 1~5 整数分（5 最好）：\n"
    "1. character_consistency 角色一致性：是否符合宁宁人格\n"
    "2. language_style 语言辨识度：是否有宁宁的语言特征\n"
    "3. naturalness 自然程度：是否自然、不像 AI/客服\n"
    "4. qq_adaptation 群聊适应性：是否适合群聊，不默认恋爱、不堆原作设定、不越界\n"
    "5. repetition 反套路度：是否有新鲜感、不套公式（5=不套路，1=每条都一个套路）\n"
    "只返回 JSON："
    '{"character_consistency":5,"language_style":4,"naturalness":4,'
    '"qq_adaptation":5,"repetition":3,"comment":"一句话点评"}'
)


def _client() -> OpenAI:
    # trust_env=False：绕过 Windows 系统代理（127.0.0.1:7897），直连国内 DeepSeek。
    return OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        http_client=httpx.Client(trust_env=False, timeout=60.0),
    )


def _generate(client: OpenAI, context_text: str, use_fewshot: bool) -> str:
    """用生产同款人格组装逻辑生成回复。"""
    system = nene_persona.build_system_prompt()
    if use_fewshot:
        fb = nene_persona.build_fewshot_block(context_text)
        if fb:
            system += "\n\n" + fb
    user = f"以下是 QQ 群最近聊天：\n\n{context_text}\n\n请以群成员身份自然地回复一句。"
    resp = client.chat.completions.create(
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=120,
        temperature=0.9,
    )
    return (resp.choices[0].message.content or "").strip()


def _judge(client: OpenAI, context_text: str, reply: str) -> dict:
    """LLM 裁判给 5 维打分，失败返回空。"""
    user = f"【群聊场景】\n{context_text}\n\n【宁宁的回复】\n{reply}"
    resp = client.chat.completions.create(
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": user},
        ],
        max_tokens=300,
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    try:
        return json.loads(resp.choices[0].message.content or "{}")
    except json.JSONDecodeError:
        return {}


def _objective_repetition(replies: list[str]) -> dict:
    n = len(replies)
    cnt = collections.Counter(replies)
    exact_dup = sum(v - 1 for v in cnt.values() if v > 1)
    starts = [r[:4] if len(r) >= 4 else r for r in replies]
    top_starts = collections.Counter(starts).most_common(5)
    return {"total": n, "exact_dup": exact_dup, "top_starts": top_starts}


def main() -> int:
    ap = argparse.ArgumentParser(description="评测宁宁人格")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 个场景（0=全量）")
    ap.add_argument("--no-fewshot", action="store_true", help="消融：不用 few-shot")
    ap.add_argument("--in", dest="in_path", default=SCENARIOS_PATH)
    args = ap.parse_args()

    scenarios = json.load(open(args.in_path, encoding="utf-8"))
    if args.limit:
        scenarios = scenarios[: args.limit]
    print(f"场景 {len(scenarios)} 个，few-shot={'关' if args.no_fewshot else '开'}。")

    client = _client()
    results: list[dict] = []
    for sc in scenarios:
        ctx = "\n".join(sc["context"])
        reply = _generate(client, ctx, not args.no_fewshot)
        scores = _judge(client, ctx, reply)
        row = dict(sc)
        row["reply"] = reply
        row["comment"] = str(scores.get("comment", "")).strip()
        for d in DIMS:
            try:
                row[d] = int(scores.get(d, 0))
            except (TypeError, ValueError):
                row[d] = 0
        results.append(row)
        print(f"  [{sc['id']} {sc['situation']}] {reply[:24]}")
        time.sleep(0.3)

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "results.jsonl"), "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 汇总
    avg = {d: round(statistics.mean(r[d] for r in results), 2) for d in DIMS}
    overall = round(statistics.mean(avg.values()), 2)

    by_sit: dict[str, list[dict]] = collections.defaultdict(list)
    for r in results:
        by_sit[r["situation"]].append(r)
    sit_avg = {
        s: round(statistics.mean(statistics.mean(r[d] for d in DIMS) for r in rs), 2)
        for s, rs in sorted(by_sit.items())
    }

    def overall_of(r: dict) -> float:
        return statistics.mean(r[d] for d in DIMS)

    worst = sorted(results, key=overall_of)[:5]
    reps = _objective_repetition([r["reply"] for r in results])

    # 写报告
    lines = ["# 宁宁人格评测报告", ""]
    lines.append(f"- 场景数：{len(results)}　few-shot：{'关' if args.no_fewshot else '开'}")
    lines.append(f"- **总均分：{overall} / 5**")
    lines.append("")
    lines.append("## 各维度均分")
    lines.append("| 维度 | 均分 |")
    lines.append("| --- | --- |")
    for d in DIMS:
        lines.append(f"| {d} | {avg[d]} |")
    lines.append("")
    lines.append("## 分情境均分")
    lines.append("| 情境 | 均分 |")
    lines.append("| --- | --- |")
    for s, a in sit_avg.items():
        lines.append(f"| {s} | {a} |")
    lines.append("")
    lines.append("## 最差 5 条（需改进）")
    for r in worst:
        lines.append(f"- [{r['id']} {r['situation']}] {r['reply']}（{round(overall_of(r), 2)}）")
    lines.append("")
    lines.append("## 客观重复度")
    lines.append(f"- 完全相同的回复：{reps['exact_dup']} 条 / {reps['total']} 条")
    lines.append("- 高频开头：" + "、".join(f"「{s}」×{c}" for s, c in reps["top_starts"]))

    report = "\n".join(lines)
    with open(os.path.join(OUT_DIR, "report.md"), "w", encoding="utf-8") as f:
        f.write(report)

    print("\n" + report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
