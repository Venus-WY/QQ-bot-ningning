"""SQLite 持久化：每个群友的资料 / 长期记忆 / 关系数值。

三张表：
  users         —— 昵称、profile 摘要、首次/最近出现时间、发言数
  user_memories —— 长期事实/事件（带 importance、时间戳）
  relationships —— 熟悉度 / 好感度 / 信任度 / 被调侃耐受度

这是「关系层」——只读写这些数据，绝不碰 persona 核心人格（那部分只允许手动改）。
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

from .config import PROJECT_ROOT

DB_PATH = Path(PROJECT_ROOT) / "data" / "memory.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id         INTEGER PRIMARY KEY,
    nickname        TEXT NOT NULL DEFAULT '',
    profile_summary TEXT NOT NULL DEFAULT '',
    first_seen      REAL NOT NULL DEFAULT 0,
    last_seen       REAL NOT NULL DEFAULT 0,
    message_count   INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS user_memories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    type        TEXT NOT NULL,           -- fact / event
    content     TEXT NOT NULL,
    importance  REAL NOT NULL DEFAULT 0.5,
    created_at  REAL NOT NULL DEFAULT 0,
    last_used_at REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS relationships (
    user_id           INTEGER PRIMARY KEY,
    familiarity       REAL NOT NULL DEFAULT 0,
    affection         REAL NOT NULL DEFAULT 0,
    trust             REAL NOT NULL DEFAULT 0,
    teasing_tolerance REAL NOT NULL DEFAULT 30
);
CREATE INDEX IF NOT EXISTS idx_mem_user ON user_memories(user_id);
"""

_REL_KEYS = ("familiarity", "affection", "trust", "teasing_tolerance")


class MemoryStore:
    """线程安全的最小封装：小群（十几人）单连接 + 锁足够。"""

    def __init__(self, db_path: Path = DB_PATH) -> None:
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # ---- users ----
    def get_or_create_user(self, user_id: int, nickname: str = "") -> dict:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM users WHERE user_id=?", (user_id,)
            ).fetchone()
            if row is None:
                now = time.time()
                self._conn.execute(
                    "INSERT INTO users(user_id,nickname,first_seen,last_seen) "
                    "VALUES(?,?,?,?)",
                    (user_id, nickname or str(user_id), now, now),
                )
                self._conn.commit()
                row = self._conn.execute(
                    "SELECT * FROM users WHERE user_id=?", (user_id,)
                ).fetchone()
            return dict(row)

    def touch(self, user_id: int, nickname: str = "") -> None:
        """记录一次发言：更新 last_seen、message_count，顺带更新昵称。"""
        with self._lock:
            self._conn.execute(
                "UPDATE users SET last_seen=?, message_count=message_count+1, "
                "nickname=CASE WHEN ?!='' THEN ? ELSE nickname END "
                "WHERE user_id=?",
                (time.time(), nickname, nickname, user_id),
            )
            self._conn.commit()

    def set_profile_summary(self, user_id: int, summary: str) -> None:
        if not summary:
            return
        with self._lock:
            self._conn.execute(
                "UPDATE users SET profile_summary=? WHERE user_id=?",
                (summary, user_id),
            )
            self._conn.commit()

    # ---- memories ----
    def add_memories(self, user_id: int, items: list[dict]) -> None:
        """批量写入记忆，items 形如 {type, content, importance}。"""
        if not items:
            return
        with self._lock:
            now = time.time()
            for it in items:
                self._conn.execute(
                    "INSERT INTO user_memories(user_id,type,content,importance,created_at) "
                    "VALUES(?,?,?,?,?)",
                    (user_id, it.get("type", "fact"), it.get("content", ""),
                     float(it.get("importance", 0.5)), now),
                )
            self._conn.commit()

    def top_memories(self, user_id: int, n: int = 8) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT type, content, importance FROM user_memories "
                "WHERE user_id=? ORDER BY importance DESC, created_at DESC LIMIT ?",
                (user_id, n),
            ).fetchall()
        return [dict(r) for r in rows]

    # ---- relationships ----
    def get_relationship(self, user_id: int) -> dict[str, float]:
        with self._lock:
            row = self._conn.execute(
                "SELECT familiarity, affection, trust, teasing_tolerance "
                "FROM relationships WHERE user_id=?", (user_id,)
            ).fetchone()
        if row is None:
            return {
                "familiarity": 0.0,
                "affection": 0.0,
                "trust": 0.0,
                "teasing_tolerance": 30.0,
            }
        return dict(row)

    def apply_delta(self, user_id: int, delta: dict[str, float]) -> None:
        """叠加关系增量，就地 clamp 到 [-100, 100]。"""
        cur = self.get_relationship(user_id)
        new = {}
        for k in _REL_KEYS:
            v = float(cur.get(k, 0.0)) + float(delta.get(k, 0.0))
            new[k] = max(-100.0, min(100.0, v))
        with self._lock:
            self._conn.execute(
                "INSERT INTO relationships(user_id,familiarity,affection,trust,teasing_tolerance) "
                "VALUES(?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
                "familiarity=excluded.familiarity, affection=excluded.affection, "
                "trust=excluded.trust, teasing_tolerance=excluded.teasing_tolerance",
                (user_id, new["familiarity"], new["affection"],
                 new["trust"], new["teasing_tolerance"]),
            )
            self._conn.commit()

    def snapshot(self) -> list[dict]:
        """导出全部用户 + 关系 + 记忆（供人类查看 / 渲染成文件）。"""
        with self._lock:
            users = [dict(r) for r in self._conn.execute(
                "SELECT * FROM users ORDER BY message_count DESC").fetchall()]
            rels = {r["user_id"]: dict(r) for r in self._conn.execute(
                "SELECT * FROM relationships").fetchall()}
            mems: dict[int, list[dict]] = {}
            for r in self._conn.execute(
                "SELECT user_id,type,content,importance FROM user_memories "
                "ORDER BY importance DESC, created_at DESC").fetchall():
                mems.setdefault(r["user_id"], []).append(dict(r))
        return [
            {"user": u, "rel": rels.get(u["user_id"]), "memories": mems.get(u["user_id"], [])}
            for u in users
        ]


def _fmt_ts(ts: float) -> str:
    if not ts:
        return "-"
    return time.strftime("%m-%d %H:%M", time.localtime(ts))


def render_view(rows: list[dict]) -> str:
    """把 snapshot() 结果渲染成人类可读的 markdown。"""
    lines = ["# 群友记忆视图", "", "> 自动生成，实时更新。数据源：`data/memory.db`", ""]
    if not rows:
        lines.append("（还没有任何群友记录）")
        return "\n".join(lines)
    for row in rows:
        u = row["user"]
        rel = row["rel"] or {}
        mems = row["memories"]
        name = u.get("nickname") or str(u["user_id"])
        lines.append(f"## {name}（id {u['user_id']}）")
        lines.append(
            f"- 发言 {u['message_count']} 次　"
            f"首次 {_fmt_ts(u['first_seen'])}　最近 {_fmt_ts(u['last_seen'])}"
        )
        lines.append(
            f"- 熟悉度 {rel.get('familiarity', 0):.1f}　"
            f"好感度 {rel.get('affection', 0):.1f}　"
            f"信任 {rel.get('trust', 0):.1f}　"
            f"调侃耐受 {rel.get('teasing_tolerance', 30):.0f}"
        )
        prof = u.get("profile_summary")
        if prof:
            lines.append(f"- 印象：{prof}")
        if mems:
            lines.append("- 记得的事：")
            for m in mems[:15]:
                lines.append(f"  - {m['content']}")
        lines.append("")
    return "\n".join(lines)
