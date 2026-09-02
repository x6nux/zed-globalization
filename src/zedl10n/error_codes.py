# error_codes.py — zedl10n 在 CI（GitHub Actions）中的对外错误输出契约。
#
# 设计动机：AI 网关返回的原始错误体可能包含内部端点、账号信息或大段
# HTML，直接 log/raise 会整段落进公开的 Actions 日志。这里把可预期的
# 失败归类成稳定短码：默认日志只出现"短码 + 一句话摘要"，原始异常
# 细节一律降到 debug 级别（Actions 默认不显示，排障时手动开 debug）。
#
# 稳定性承诺：短码一经发布不再改含义，只增不改名。下游脚本可以
# grep "ZLxxxx" 做自动化分支。

from __future__ import annotations

import logging
import re

# 短码 → 一句话摘要。摘要里不含任何异常原文。
ERROR_CODES: dict[str, str] = {
    "ZL1001": "AI 调用失败：网络/超时（已重试 5 次）",
    "ZL1002": "AI 调用失败：认证被拒（检查 API Key）",
    "ZL1003": "AI 调用失败：配额/限流（稍后重试或降低并发）",
    "ZL1004": "AI 响应解析失败：三种格式（JSON/XML/编号）均无法解析",
    "ZL1005": "AI 响应中占位符损坏（{name} 丢失或被改动）",
    "ZL2001": "源文件读取失败（路径不存在或权限不足）",
    "ZL2002": "翻译文件 JSON 解析失败（文件损坏）",
    "ZL3001": "输出目录不可写",
}

# 异常文本 → 短码的分类规则。按声明顺序匹配，先命中先得。
_CLASSIFIERS: list[tuple[str, re.Pattern[str]]] = [
    ("ZL1002", re.compile(r"401|unauthorized|invalid[ _-]?api[ _-]?key|authentication", re.I)),
    ("ZL1003", re.compile(r"429|quota|rate[ _-]?limit|too many requests", re.I)),
    ("ZL1004", re.compile(r"parse|解析|format|json\.decoder|xml", re.I)),
    ("ZL1001", re.compile(r"timeout|timed? ?out|connection|network|ssl|eof|reset|proxy", re.I)),
]


def classify(err: BaseException) -> str:
    """把任意异常归类为 ZL 短码。未命中任何规则时返回 ZL1001（网络类兜底）。"""
    text = f"{type(err).__name__}: {err}"
    for code, pat in _CLASSIFIERS:
        if pat.search(text):
            return code
    return "ZL1001"


def extract_http_status(err: BaseException) -> int | None:
    """从 AI SDK 异常里提取 HTTP 状态码（openai sdk 的 APIStatusError.status_code）。"""
    status = getattr(err, "status_code", None)
    if isinstance(status, int):
        return status
    m = re.search(r"\b([1-5]\d{2})\b", str(err))
    return int(m.group(1)) if m else None


def extract_body_code(err: BaseException) -> str | None:
    """从错误体 JSON 里提取业务 code 字段（如果网关带了）。只取 code，不取 message/body。"""
    body = getattr(err, "body", None)
    if isinstance(body, dict):
        code = body.get("code") or (body.get("error") or {}).get("code") if isinstance(body.get("error"), dict) else body.get("code")
        if code is not None:
            return str(code)
    m = re.search(r"['\"]?code['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9_.-]+)", str(err))
    return m.group(1) if m else None


def report(logger: logging.Logger, err: BaseException, context: str = "") -> None:
    """以 CI 友好的方式记录一条错误。

    输出契约（Alpha 指定）：只输出 ZL 短码 + 摘要 + HTTP 状态码 + 响应体
    里的 code 字段（如有）。原始异常消息、响应体正文、堆栈一律不输出。
    示例：
        ZL1003 [file] http=429 code=1302: 配额/限流（稍后重试或降低并发）
    """
    code = classify(err)
    http = extract_http_status(err)
    body_code = extract_body_code(err)
    ctx = f" [{context}]" if context else ""
    parts = [code]
    if http is not None:
        parts.append(f"http={http}")
    if body_code:
        parts.append(f"code={body_code}")
    parts.append(ERROR_CODES[code])
    logger.warning("%s%s", " ".join(parts), ctx)
