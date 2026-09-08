"""开发用：监听文件改动，自动重启 bot（改 .py / .yaml 不用手动重启）。

用法（在 qq-bot 目录下）：
    .venv\\Scripts\\python.exe -X utf8 run_reload.py
或直接双击「启动.bat」。

监听范围：src/、../corpus/、config.yaml、.env、pyproject.toml、bot.py。
刻意不监听 data/ 和 .venv：data 里是记忆库（每句话都在变），.venv 是依赖，
监听它们会造成无意义的频繁重启。
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from watchfiles import watch

HERE = Path(__file__).resolve().parent

WATCH_PATHS = [
    HERE / "src",
    HERE.parent / "corpus",
    HERE / "config.yaml",
    HERE / ".env",
    HERE / "pyproject.toml",
    HERE / "bot.py",
]

SUFFIXES = {".py", ".yaml", ".yml", ".toml", ".json"}


def _relevant(change, path: str) -> bool:
    """只对源码/配置/人格文件的变化感兴趣，忽略其它。"""
    p = Path(path)
    if p.suffix.lower() in SUFFIXES:
        return True
    return p.name == ".env"


def _stop(proc) -> None:
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def _start() -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-X", "utf8", str(HERE / "bot.py")], cwd=str(HERE)
    )


def main() -> None:
    print("[reload] 启动 QQ 群 AI 群友（改动文件会自动重启）…")
    print("[reload] 监听：src/  ../corpus/  config.yaml  .env  bot.py")
    proc = _start()
    try:
        for changes in watch(*WATCH_PATHS, watch_filter=_relevant):
            if not changes:
                continue
            print("[reload] 检测到改动，正在重启 …")
            _stop(proc)
            time.sleep(1.0)  # 等上一个进程释放端口
            proc = _start()
    except KeyboardInterrupt:
        print("\n[reload] 退出")
        _stop(proc)


if __name__ == "__main__":
    main()
