"""
hamburger/registry.py — 汉堡（单个 Agent）持久化到磁盘的命名注册表。

目的：套餐系统要通过 `burger_id` 引用若干个已搭建好的汉堡，
因此需要把前端已经配置好的汉堡（等价于 /api/build 的 BuildConfig）保存下来，
之后套餐编译器可根据 id 再次编译出子图。

存储：`data/burgers/<burger_id>.json`，内容示例：
{
  "burger_id": "bgr_abc123",
  "name": "天气查询助手",
  "description": "...",
  "created_at": "2026-01-01T12:00:00",
  "updated_at": "...",
  "config": { ...BuildConfig dict... }
}
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional


# 默认存储目录（可通过环境变量 HAMBURGER_DATA_DIR 覆盖）
def _data_root() -> str:
    root = os.environ.get("HAMBURGER_DATA_DIR") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
    )
    return root


def _burgers_dir() -> str:
    d = os.path.join(_data_root(), "burgers")
    os.makedirs(d, exist_ok=True)
    return d


_SAFE_NAME = re.compile(r"[^a-zA-Z0-9_\-]+")


def _sanitize_slug(name: str) -> str:
    slug = _SAFE_NAME.sub("_", (name or "").strip()).strip("_").lower()
    return slug[:32] or "burger"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def _safe_path(burger_id: str) -> str:
    # 只允许形如 bgr_xxx 的 id；防越权
    if not re.fullmatch(r"[a-zA-Z0-9_\-]{3,64}", burger_id or ""):
        raise ValueError(f"非法的 burger_id: {burger_id!r}")
    return os.path.join(_burgers_dir(), f"{burger_id}.json")


def _record_from_file(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def list_burgers() -> List[Dict[str, Any]]:
    """返回所有已保存汉堡的摘要（不含完整 config）。"""
    out: List[Dict[str, Any]] = []
    for fname in sorted(os.listdir(_burgers_dir())):
        if not fname.endswith(".json"):
            continue
        rec = _record_from_file(os.path.join(_burgers_dir(), fname))
        if not rec:
            continue
        cfg = rec.get("config") or {}
        out.append({
            "burger_id": rec.get("burger_id"),
            "name": rec.get("name"),
            "description": rec.get("description", ""),
            "created_at": rec.get("created_at"),
            "updated_at": rec.get("updated_at"),
            "agent_type": cfg.get("agent_type"),
            "meat_model": cfg.get("meat_model"),
            "vegetables": cfg.get("vegetables") or [],
        })
    # 新的在前
    out.sort(key=lambda r: r.get("updated_at") or "", reverse=True)
    return out


def get_burger(burger_id: str) -> Optional[Dict[str, Any]]:
    """返回完整的汉堡记录（含 config）。"""
    path = _safe_path(burger_id)
    if not os.path.exists(path):
        return None
    return _record_from_file(path)


def save_burger(
    name: str,
    config: Dict[str, Any],
    *,
    burger_id: Optional[str] = None,
    description: str = "",
) -> Dict[str, Any]:
    """创建或覆盖一个汉堡记录。"""
    if not name or not name.strip():
        raise ValueError("汉堡名称不能为空")

    # 存 config 时去掉易变字段（thread_id）
    cfg = {k: v for k, v in (config or {}).items() if k != "thread_id"}

    now = _now_iso()
    if burger_id:
        path = _safe_path(burger_id)
        existing = _record_from_file(path) if os.path.exists(path) else None
        created = (existing or {}).get("created_at") or now
    else:
        burger_id = f"bgr_{_sanitize_slug(name)}_{uuid.uuid4().hex[:6]}"
        path = _safe_path(burger_id)
        created = now

    record = {
        "burger_id": burger_id,
        "name": name.strip(),
        "description": (description or "").strip(),
        "created_at": created,
        "updated_at": now,
        "config": cfg,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return record


def delete_burger(burger_id: str) -> bool:
    path = _safe_path(burger_id)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False
