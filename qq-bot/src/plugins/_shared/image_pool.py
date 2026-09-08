"""共享图片池：扫描素材目录，供所有插件取图。

素材目录：qq-bot 的兄弟目录「素材」（PROJECT_ROOT.parent / "素材"）。
图片名即角色名（如 白子.jpg）。可选 metadata.yaml 补充 series/mood/tags，
方便以后「按情绪挑图 / 随机角色」等玩法。

用法：
    from src.plugins._shared import get_random_image, get_image_by_character

不 import 其它插件，纯 Python + yaml，可独立测试。
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# 本文件在 qq-bot/src/plugins/_shared/ 下，往上 3 级 = qq-bot
PROJECT_ROOT = Path(__file__).resolve().parents[3]
IMAGE_DIR = PROJECT_ROOT.parent / "素材"
METADATA_PATH = IMAGE_DIR / "metadata.yaml"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
DEFAULT_SERIES = "Blue Archive"


@dataclass
class ImageInfo:
    file: str
    path: Path
    character: str
    series: str = DEFAULT_SERIES
    mood: str = ""
    tags: list[str] = field(default_factory=list)


def _load_metadata() -> dict[str, dict]:
    """读 metadata.yaml，返回 {file: {...}}；没有则空。"""
    if not METADATA_PATH.exists():
        return {}
    raw = yaml.safe_load(METADATA_PATH.read_text(encoding="utf-8")) or {}
    out: dict[str, dict] = {}
    for item in raw.get("images", []):
        if isinstance(item, dict) and item.get("file"):
            out[item["file"]] = item
    return out


def _scan() -> list[ImageInfo]:
    """扫描素材目录（每次现扫，十几张开销可忽略，新增图即时生效）。"""
    meta = _load_metadata()
    infos: list[ImageInfo] = []
    if not IMAGE_DIR.exists():
        return infos
    for p in sorted(IMAGE_DIR.iterdir()):
        if p.suffix.lower() not in IMAGE_EXTS:
            continue
        m = meta.get(p.name, {})
        infos.append(
            ImageInfo(
                file=p.name,
                path=p,
                character=str(m.get("character") or p.stem),
                series=str(m.get("series") or DEFAULT_SERIES),
                mood=str(m.get("mood") or ""),
                tags=list(m.get("tags") or []),
            )
        )
    return infos


def list_images() -> list[ImageInfo]:
    return _scan()


def get_random_image(rng: random.Random | None = None) -> ImageInfo | None:
    imgs = _scan()
    if not imgs:
        return None
    if rng is not None:
        return rng.choice(imgs)
    return random.choice(imgs)


def get_image_by_character(name: str) -> ImageInfo | None:
    key = name.strip().lower()
    for img in _scan():
        if img.character.lower() == key or img.file.lower() == key:
            return img
    return None


def get_image_by_series(series: str) -> list[ImageInfo]:
    key = series.strip().lower()
    return [img for img in _scan() if img.series.lower() == key]


def get_image_by_tag(tag: str) -> ImageInfo | None:
    key = tag.strip().lower()
    for img in _scan():
        if key in {t.lower() for t in img.tags}:
            return img
    return None
