"""翻译相关的 Prompt 模板和构建函数"""

from __future__ import annotations

import json

from .utils import extract_crate_name, extract_placeholders

SYSTEM_PROMPT_TEMPLATE = """你是一个专业的软件界面翻译专家，正在翻译 Zed 代码编辑器的用户界面。

目标语言: {lang}

翻译规则:
1. 对需要翻译的 UI 字符串，返回准确、自然的翻译
2. 对不需要翻译的内容，返回空字符串 ""。不需要翻译的内容包括：
   - URL、文件路径、目录路径
   - 纯数字、版本号
   - 纯标点符号、特殊字符
   - 编程标识符（变量名、函数名、类名）
   - API 名称、HTTP 方法、MIME 类型
   - 正则表达式
   - 代码片段、命令行指令
   - 只有一两个字母的缩写
   - 键盘按键名: backspace, enter, tab, escape, delete, space, up, down, left, right, home, end, pageup, pagedown, insert, f1~f35 等
   - match/if 分支中作为匹配值或返回值的标识符字符串（如 "backspace".to_string()）
   - 枚举变体名、action 名、内部状态名等程序标识符
   请结合源代码上下文判断每条字符串的用途。如果字符串在代码中用于逻辑匹配、键值映射或 API 调用而非面向用户展示，则不应翻译。
3. 【极其重要】必须完整保留字符串中的所有格式占位符，一个都不能丢失、修改或增加。
   常见格式占位符包括：
   - 匿名占位符（位置绑定）: {{}}, {{:?}}, {{:#?}}, {{:x}}, {{:.2}}, %s, %d, %f
   - 命名/索引占位符: {{name}}, {{0}}, {{key}}, {{name:?}}, {{value:.2}}
   原文有几个占位符，译文就必须有完全相同的几个占位符，内容不变。
   【严禁修正】即使占位符看起来像拼写错误（如 {{path?}} 而非 {{path:?}}），也必须原样保留，绝不能"修正"。
   【特别注意】匿名占位符（如 {{}}, {{:?}}）在 Rust format! 中按出现顺序绑定参数，
   翻译时必须保持它们的出现顺序与原文完全一致，不能调换位置。
   命名/索引占位符（如 {{name}}, {{0}}）不受顺序限制，可以根据译文需要调整位置。
4. 严禁将 ASCII 标点替换为中文标点。逗号保持 ","，不要变为 "、" 或 "，"；分号保持 ";"，不要变为 "；"

{glossary_section}

输入格式: JSON 对象 {{"原文": ""}}
输出格式: JSON 对象 {{"原文": "译文"}}（不需翻译的返回空字符串）

重要: 只返回 JSON 对象，不要添加任何解释文字或 markdown 标记。"""

_USER_PROMPT_WITH_SOURCE = """文件: {file_path}
模块: {crate_name}

=== 源文件代码 ===
```rust
{file_content}
```

=== 待翻译字符串 ===
{entries}

请结合上面的源代码上下文，判断每条字符串的用途后翻译，返回 JSON 对象。"""

_USER_PROMPT_NO_SOURCE = """文件: {file_path}
模块: {crate_name}

以下是需要翻译的字符串:

{entries}

请翻译以上字符串，返回 JSON 对象。"""

XML_FALLBACK_INSTRUCTION = """
（重要：此次请使用 XML 格式返回，不要使用 JSON）

输出格式:
<translations>
<t><s><![CDATA[原文1]]></s><v>译文1</v></t>
<t><s><![CDATA[原文2]]></s><v></v></t>
</translations>

注意：原文必须用 <![CDATA[...]]> 包裹，防止特殊字符干扰 XML 解析。
不需要翻译的字符串，<v> 标签内留空。只返回 XML，不要添加解释。"""


def build_numbered_instruction(count: int) -> str:
    """构建编号格式降级指令"""
    return f"""
（重要：此次请使用编号格式返回，不要使用 JSON 或 XML）

按上面的字符串编号，逐条返回翻译结果。格式如下:
[##1##]译文1
[##2##]
[##3##]译文3

规则:
- 每条以 [##编号##] 开头，紧跟译文（同一行）
- 不需要翻译的字符串，[##编号##] 后面留空即可
- 不要添加任何解释文字
- 必须包含所有编号，从 1 到 {count}"""


def build_entries_text(strings: dict[str, str]) -> str:
    """构建待翻译条目文本（编号 + 字符串）"""
    lines: list[str] = []
    for i, (s, _) in enumerate(strings.items(), 1):
        lines.append(f'{i}. "{s}"')
    return "\n".join(lines)


def estimate_tokens(text: str) -> int:
    """使用 o200k_base 编码计算 token 数，乘 1.1 保守估算"""
    import tiktoken
    enc = tiktoken.get_encoding("o200k_base")
    return int(len(enc.encode(text, disallowed_special=())) * 1.1)


def build_user_prompt(
    file_path: str, strings: dict[str, str], file_content: str = "",
) -> str:
    """构建用户 prompt，可附带完整源文件内容"""
    crate_name = extract_crate_name(file_path)
    entries_text = build_entries_text(strings)
    if file_content:
        template = _USER_PROMPT_WITH_SOURCE
        prompt = template.format(
            file_path=file_path, crate_name=crate_name,
            file_content=file_content, entries=entries_text,
        )
    else:
        prompt = _USER_PROMPT_NO_SOURCE.format(
            file_path=file_path, crate_name=crate_name, entries=entries_text,
        )
    input_json = {s: "" for s in strings}
    prompt += f"\n\n输入:\n```json\n{json.dumps(input_json, ensure_ascii=False)}\n```"
    return prompt


def _is_positional(ph: str) -> bool:
    """判断占位符是否按位置绑定参数。

    位置绑定（顺序敏感）：{}, {:?}, {:.2}, %s, %d 等
    命名/索引（顺序无关）：{name}, {0}, {name:?} 等
    """
    if ph.startswith("%"):
        return True
    inner = ph[1:-1]
    return inner == "" or inner.startswith(":")


def validate_placeholders(
    translations: dict[str, str],
) -> dict[str, tuple[list[str], list[str]]]:
    """校验译文占位符是否与原文一致。

    - 位置绑定占位符（{}, {:?} 等）：顺序必须严格一致
    - 命名/索引占位符（{name}, {0} 等）：只需集合一致

    返回有问题的条目: {原文: (原文占位符列表, 译文占位符列表)}
    """
    errors: dict[str, tuple[list[str], list[str]]] = {}
    for original, translated in translations.items():
        if not translated:
            continue
        src_ph = extract_placeholders(original)
        dst_ph = extract_placeholders(translated)
        # 位置绑定占位符：按顺序比较
        src_pos = [p for p in src_ph if _is_positional(p)]
        dst_pos = [p for p in dst_ph if _is_positional(p)]
        if src_pos != dst_pos:
            errors[original] = (src_ph, dst_ph)
            continue
        # 命名占位符：按集合比较
        src_named = sorted(p for p in src_ph if not _is_positional(p))
        dst_named = sorted(p for p in dst_ph if not _is_positional(p))
        if src_named != dst_named:
            errors[original] = (src_ph, dst_ph)
    return errors


def build_fix_prompt(
    errors: dict[str, tuple[list[str], list[str]]],
    translations: dict[str, str],
) -> str:
    """构建占位符修正提示，用于重试翻译"""
    lines = ["以下翻译的格式占位符有误，请修正："]
    for original, (src_ph, dst_ph) in errors.items():
        wrong_translation = translations.get(original, "")
        lines.append(f'- 原文: "{original}"')
        lines.append(f'  错误译文: "{wrong_translation}"')
        lines.append(f"  问题: 原文占位符为 {src_ph}，译文占位符为 {dst_ph}，不匹配")
    lines.append("请重新翻译以上条目，确保占位符与原文完全一致。")
    lines.append("特别注意：匿名占位符（{}, {:?} 等）的出现顺序必须与原文一致。")
    lines.append("只返回 JSON 对象，不要添加任何解释文字或 markdown 标记。")
    return "\n".join(lines)
