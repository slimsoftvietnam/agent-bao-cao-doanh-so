"""Nạp 3 file cấu hình: sources.yaml, recipients.yaml, alert_rules.yaml."""
from __future__ import annotations

from pathlib import Path

import yaml


class ConfigError(Exception):
    pass


def _load(path: Path) -> dict:
    if not path.exists():
        raise ConfigError(f"Thiếu file cấu hình: {path}")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"File cấu hình sai định dạng (cần dạng khoá: giá trị): {path}")
    return data


def load_config(config_dir: str | Path) -> dict:
    d = Path(config_dir)
    cfg = {
        "sources": _load(d / "sources.yaml"),
        "recipients": _load(d / "recipients.yaml"),
        "rules": _load(d / "alert_rules.yaml"),
    }
    validate(cfg)
    return cfg


def validate(cfg: dict) -> None:
    src = cfg["sources"]
    if not src.get("sources"):
        raise ConfigError("sources.yaml: chưa khai báo nguồn dữ liệu nào (mục 'sources').")
    ids = set()
    for s in src["sources"]:
        for k in ("id", "owner", "file_patterns"):
            if not s.get(k):
                raise ConfigError(f"sources.yaml: nguồn {s.get('id', '?')} thiếu trường '{k}'.")
        if s["id"] in ids:
            raise ConfigError(f"sources.yaml: id nguồn bị trùng: {s['id']}")
        ids.add(s["id"])
    if not src.get("columns"):
        raise ConfigError("sources.yaml: thiếu mục 'columns' (bảng tên cột đồng nghĩa).")
    r = cfg["recipients"]
    if not (r.get("owner") or {}).get("email"):
        raise ConfigError("recipients.yaml: thiếu owner.email (người phụ trách nhận cảnh báo).")
    if not (r.get("team") or {}).get("to"):
        raise ConfigError("recipients.yaml: thiếu team.to (danh sách email nhận báo cáo).")
    if "rules" not in cfg["rules"]:
        raise ConfigError("alert_rules.yaml: thiếu mục 'rules'.")


def rule(cfg: dict, name: str) -> dict:
    """Quy tắc đã gộp giá trị mặc định; enabled=True nếu không khai báo."""
    r = dict((cfg["rules"].get("rules") or {}).get(name) or {})
    r.setdefault("enabled", True)
    r.setdefault("severity", "critical")
    return r
