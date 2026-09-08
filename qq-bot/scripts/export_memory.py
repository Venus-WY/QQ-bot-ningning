#!/usr/bin/env python3
"""手动把 data/memory.db 导出成人类可读的 data/memory_view.md。

bot 运行时这个文件会自动刷新；bot 没跑时，想看一眼就跑本脚本。
用法（在 qq-bot 目录下）：
    .venv/Scripts/python.exe -X utf8 scripts/export_memory.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
QQ_BOT = HERE.parent
sys.path.insert(0, str(QQ_BOT))  # 让 `import src.plugins...` 可用

from src.plugins.qqbot.memory_store import MemoryStore, render_view  # noqa: E402


def main() -> None:
    store = MemoryStore()
    text = render_view(store.snapshot())
    out = QQ_BOT / "data" / "memory_view.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"已导出到 {out}\n")
    print(text)


if __name__ == "__main__":
    main()
