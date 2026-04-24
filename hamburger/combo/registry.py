"""
hamburger/combo/registry.py — 套餐配方持久化。

与 hamburger.registry（汉堡）对应，存 `data/combos/<combo_id>.json`。
套餐数据结构（combo_recipe）：
{
  "combo_id": "combo_abc",
  "name": "智能客服流水线",
  "description": "...",
  "pattern": "chain|routing|parallel|orchestrator|evaluator",
  "config": {...},              # 模式相关的配置（见 patterns.py 各 build_* 头注释）
  "created_at": "...",
  "updated_at": "..."
}
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional


def _data_root() -> str:
    root = os.environ.get("HAMBURGER_DATA_DIR") or os.path.join(
        os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))),
        "data",
    )
    return root


def _combos_dir() -> str:
    d = os.path.join(_data_root(), "combos")
    os.makedirs(d, exist_ok=True)
    return d


_ID_RE = re.compile(r"[a-zA-Z0-9_\-]{3,64}")
_SAFE_NAME = re.compile(r"[^a-zA-Z0-9_\-]+")


def _safe_path(combo_id: str) -> str:
    if not combo_id or not _ID_RE.fullmatch(combo_id):
        raise ValueError(f"非法的 combo_id: {combo_id!r}")
    return os.path.join(_combos_dir(), f"{combo_id}.json")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def _load(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def list_combos() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for fname in sorted(os.listdir(_combos_dir())):
        if not fname.endswith(".json"):
            continue
        rec = _load(os.path.join(_combos_dir(), fname))
        if not rec:
            continue
        out.append({
            "combo_id": rec.get("combo_id"),
            "name": rec.get("name"),
            "description": rec.get("description", ""),
            "pattern": rec.get("pattern"),
            "created_at": rec.get("created_at"),
            "updated_at": rec.get("updated_at"),
        })
    out.sort(key=lambda r: r.get("updated_at") or "", reverse=True)
    return out


def get_combo(combo_id: str) -> Optional[Dict[str, Any]]:
    path = _safe_path(combo_id)
    if not os.path.exists(path):
        return None
    return _load(path)


def save_combo(
    name: str,
    pattern: str,
    config: Dict[str, Any],
    *,
    combo_id: Optional[str] = None,
    description: str = "",
) -> Dict[str, Any]:
    if not name or not name.strip():
        raise ValueError("套餐名称不能为空")
    if pattern not in {"chain", "routing", "parallel", "orchestrator", "evaluator"}:
        raise ValueError(f"未知的套餐模式: {pattern}")

    now = _now()
    if combo_id:
        path = _safe_path(combo_id)
        existing = _load(path) if os.path.exists(path) else None
        created = (existing or {}).get("created_at") or now
    else:
        slug = _SAFE_NAME.sub("_", name.strip()).strip(
            "_").lower()[:24] or "combo"
        combo_id = f"cmb_{slug}_{uuid.uuid4().hex[:6]}"
        path = _safe_path(combo_id)
        created = now

    rec = {
        "combo_id": combo_id,
        "name": name.strip(),
        "description": (description or "").strip(),
        "pattern": pattern,
        "config": config or {},
        "created_at": created,
        "updated_at": now,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)
    return rec


def delete_combo(combo_id: str) -> bool:
    path = _safe_path(combo_id)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False
