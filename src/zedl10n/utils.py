"""共享工具函数与类型定义"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# 翻译字典类型：{文件路径: {原文: 译文}}
TranslationDict = dict[str, dict[str, str]]

# 上下文字典类型：{原文: {"line": 行号, "context": "周围代码"}}
ContextDict = dict[str, dict[str, Any]]


@dataclass
class AIConfig:
    """AI 配置，统一封装 scan 和 translate 共用的参数。

    优先级: CLI 参数 > 环境变量 > 默认值
    """

    base_url: str = ""
    api_key: str = ""
    model: str = ""
    concurrency: int = 10

    def __post_init__(self) -> None:
        if not self.base_url:
            self.base_url = os.environ.get(
                "AI_BASE_URL", "https://api.openai.com/v1"
            )
        if not self.api_key:
            self.api_key = os.environ.get("AI_API_KEY", "")
        if not self.model:
            self.model = os.environ.get("AI_MODEL", "gpt-4o-mini")
        if self.concurrency <= 0:
            raw = os.environ.get("AI_CONCURRENCY", "10")
            self.concurrency = int(raw) if raw.isdigit() else 10

    def validate(self) -> None:
        """校验必填字段"""
        if not self.api_key:
            raise SystemExit(
                "错误: 未设置 AI API Key。"
                "请通过 --api-key 参数或 AI_API_KEY 环境变量提供。"
            )


class ProgressBar:
    """终端进度条，支持实时刷新耗时和附加信息"""

    def __init__(self, total: int, desc: str = "", width: int = 30) -> None:
        self.total = max(total, 1)
        self.desc = desc
        self.width = width
        self.current = 0
        self.extra = ""
        self._start = time.time()

    def update(self, n: int = 1, extra: str = "") -> None:
        self.current += n
        if extra:
            self.extra = extra
        self._render()

    def _render(self) -> None:
        pct = self.current / self.total
        filled = int(self.width * pct)
        bar = "█" * filled + "░" * (self.width - filled)
        elapsed = time.time() - self._start
        m, s = divmod(int(elapsed), 60)
        ts = f"{m}m{s:02d}s" if m else f"{s}s"
        parts = [f"\r{self.desc}: {bar} {self.current}/{self.total}"]
        if self.extra:
            parts.append(f"| {self.extra}")
        parts.append(f"| {ts}")
        line = " ".join(parts)
        sys.stderr.write(f"{line}\033[K")
        sys.stderr.flush()

    def finish(self) -> None:
        self._render()
        sys.stderr.write("\n")
        sys.stderr.flush()


def setup_logging(verbose: bool = False) -> None:
    """统一日志配置"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    # 压制 httpx/openai 的 HTTP Request 日志
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def parse_json_response(raw: str) -> dict[str, str]:
    """从 AI 返回的文本中提取 JSON，容忍 markdown 代码块包裹"""
    import re

    for extract in [
        lambda s: s,
        lambda s: m.group(1).strip()
        if (m := re.search(r"```(?:json)?\s*\n?(.*?)```", s, re.DOTALL))
        else None,
        lambda s: m.group(0)
        if (m := re.search(r"\{.*\}", s, re.DOTALL))
        else None,
    ]:
        text = extract(raw)
        if text is None:
            continue
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            continue
    return {}


def parse_xml_response(raw: str) -> dict[str, str]:
    """从 AI 返回的 XML 中提取翻译结果"""
    import re
    import xml.etree.ElementTree as ET

    m = re.search(r"<translations.*?>.*</translations>", raw, re.DOTALL)
    if not m:
        return {}
    try:
        root = ET.fromstring(m.group(0))
    except ET.ParseError:
        return {}
    result: dict[str, str] = {}
    for t in root.findall("t"):
        s_el, v_el = t.find("s"), t.find("v")
        if s_el is not None and s_el.text:
            result[s_el.text] = (v_el.text or "") if v_el is not None else ""
    return result


def parse_numbered_response(raw: str, keys: list[str]) -> dict[str, str]:
    """从 AI 返回的编号格式文本中提取翻译结果。

    格式: [##1##]译文1\\n[##2##]\\n[##3##]译文3
    通过编号映射回原始 key，避免原文中的特殊字符干扰解析。
    """
    import re

    result: dict[str, str] = {}
    pattern = re.compile(r"\[##(\d+)##\](.*?)(?=\[##\d+##\]|\Z)", re.DOTALL)
    for m in pattern.finditer(raw):
        idx = int(m.group(1)) - 1  # 编号从 1 开始
        value = m.group(2).strip()
        if 0 <= idx < len(keys):
            result[keys[idx]] = value
    return result


def build_glossary_section(glossary_path: str) -> str:
    """构建术语表提示文本"""
    path = Path(glossary_path)
    if not path.exists():
        return ""
    try:
        data = load_yaml(path)
    except Exception:
        return ""
    lines: list[str] = ["术语表（请严格遵守）:"]
    for en, zh in data.get("terms", {}).items():
        lines.append(f"  - {en} → {zh}")
    keep = data.get("keep_original", [])
    if keep:
        lines.append("保持原文不译的专有名词:")
        lines.append(f"  {', '.join(keep)}")
    return "\n".join(lines)


def extract_crate_name(file_path: str) -> str:
    """从文件路径提取 Rust crate 名称"""
    parts = Path(file_path).parts
    try:
        idx = list(parts).index("crates")
        return parts[idx + 1] if idx + 1 < len(parts) else "unknown"
    except ValueError:
        return "unknown"


def load_json(path: str | Path) -> Any:
    """读取 JSON 文件"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Any, path: str | Path) -> None:
    """写入 JSON 文件（UTF-8，4 空格缩进）"""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def load_yaml(path: str | Path) -> Any:
    """读取 YAML 文件"""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
