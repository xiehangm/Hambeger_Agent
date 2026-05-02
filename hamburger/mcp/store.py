"""持久化：data/mcp/servers.json 读写。

文件结构：
{
  "version": 1,
  "installed": {
      "<server_id>": {"env_values": {...}}
  },
  "custom_catalog": {
      "<server_id>": {"name", "command", "args", "env", "description", "emoji", "category"}
  }
}
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict


STORE_PATH = Path("data") / "mcp" / "servers.json"
SCHEMA_VERSION = 1


def _empty() -> Dict[str, Any]:
    return {"version": SCHEMA_VERSION, "installed": {}, "custom_catalog": {}}


def load() -> Dict[str, Any]:
    """读取持久化文件；不存在或损坏时返回空骨架。"""
    if not STORE_PATH.exists():
        return _empty()
    try:
        with STORE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("根对象必须是 dict")
        data.setdefault("version", SCHEMA_VERSION)
        data.setdefault("installed", {})
        data.setdefault("custom_catalog", {})
        return data
    except Exception as exc:
        print(f"[MCP] 持久化文件损坏，已重置: {exc}")
        return _empty()


def save(data: Dict[str, Any]) -> None:
    """原子写：先写入 .tmp 同目录文件再 rename。"""
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": SCHEMA_VERSION,
        "installed": data.get("installed") or {},
        "custom_catalog": data.get("custom_catalog") or {},
    }
    fd, tmp_path = tempfile.mkstemp(
        prefix="servers.", suffix=".tmp", dir=str(STORE_PATH.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, STORE_PATH)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
