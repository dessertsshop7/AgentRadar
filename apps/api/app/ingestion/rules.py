import hashlib
import json
import math
import re
from datetime import timedelta
from pathlib import Path

CATEGORIES = {
    "knowledge": ("知识管理/RAG", ("rag", "retrieval", "knowledge", "知识", "检索")),
    "agent-workflow": ("Agent/工作流", ("agent", "agentic", "workflow", "工作流")),
    "mcp-integration": ("MCP/集成", ("mcp", "model context protocol", "integration", "连接器")),
    "framework": ("开发框架", ("framework", "sdk", "框架")),
}


def content_hash(value) -> str:
    text = (
        value
        if isinstance(value, str)
        else json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def classify(description: str, tags: list[str]) -> dict[str, str]:
    value = " ".join([description, *tags]).lower()
    matches = {}
    for key, (_, words) in CATEGORIES.items():
        hits = [
            word
            for word in words
            if (
                re.search(r"\b" + re.escape(word) + r"\b", value)
                if word.isascii()
                else word in value
            )
        ]
        if hits:
            matches[key] = "rules-v1:" + ",".join(hits)
    return matches


def calculate_trend(
    observations, pushed_at, created_at, has_readme, *, weights=None, formula_version="p02-v1"
):
    weights = weights or {"growth": 0.5, "activity": 0.25, "freshness": 0.15, "quality": 0.1}
    observations = sorted(observations)
    end = observations[-1][0]
    observations = [row for row in observations if row[0] >= end - timedelta(days=7)]
    start = observations[0][0]
    delta = (
        observations[-1][1] - observations[0][1] if len(observations) >= 2 and end > start else None
    )
    growth = (
        min(100, math.log1p(max(0, delta)) / math.log(1001) * 100) if delta is not None else None
    )
    activity = (
        max(0, 100 * (1 - max(0, (end - pushed_at).total_seconds()) / (180 * 86400)))
        if pushed_at
        else 0
    )
    freshness = (
        max(0, 100 * (1 - max(0, (end - created_at).total_seconds()) / (365 * 86400)))
        if created_at
        else 0
    )
    quality = 100 if has_readme else 50
    components = {
        "growth": growth,
        "activity": activity,
        "freshness": freshness,
        "quality": quality,
    }
    return {
        "formula_version": formula_version,
        "score": round(sum(weights[key] * (value or 0) for key, value in components.items()), 4),
        "components": {**components, "weights": weights},
        "star_growth": delta,
        "sample_count": len(observations),
        "window_start": start,
        "window_end": end,
    }


def read_skill_metadata(path: Path, trusted_root: Path) -> dict[str, str]:
    path, trusted_root = path.resolve(), trusted_root.resolve()
    if not path.is_relative_to(trusted_root) or path.name != "SKILL.md":
        raise ValueError("Skill 必须位于明确指定的可信目录")
    if path.stat().st_size > 100_000:
        raise ValueError("Skill 元信息文件过大")
    body = path.read_text(encoding="utf-8-sig")
    match = re.match(r"\A---\n(.*?)\n---(?:\n|\Z)", body, re.S)
    if not match:
        raise ValueError("缺少简单 frontmatter")
    frontmatter = match[1]
    result = {}
    for line in frontmatter.splitlines():
        match = re.fullmatch(r"(name|description):\s*(.{1,2000})", line)
        if match:
            if re.fullmatch(r"[>|][+-]?\d*[+-]?", match[2].strip()):
                raise ValueError("只支持简单字符串元信息，不解析多行 YAML")
            result[match[1]] = match[2].strip().strip("\"'")
    if not result.get("name") or not result.get("description"):
        raise ValueError("只支持含 name 和 description 的简单字符串元信息")
    return result
