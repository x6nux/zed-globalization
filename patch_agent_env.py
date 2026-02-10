#!/usr/bin/env python3
"""
编译前补丁脚本：修复 Agent 插件环境变量被覆盖问题。

补丁点 1: 删除 agent_server_store.rs 中强制清空 ANTHROPIC_API_KEY 的代码
补丁点 2: 在 claude.rs 的 connect() 中透传系统环境变量（与 codex.rs 模式一致）

用法: python3 patch_agent_env.py [--source-root zed] [--dry-run]
"""

import argparse
import sys
from pathlib import Path

PATCH_MARKER = "[ZED_GLOBALIZATION_PATCH]"


def patch_remove_api_key_clear(source_root: Path, dry_run: bool) -> bool:
    """补丁点 1: 删除强制清空 ANTHROPIC_API_KEY 的代码行。"""
    target = source_root / "crates/project/src/agent_server_store.rs"
    name = "agent_server_store.rs"

    if not target.exists():
        print(f"  WARN: {name} 不存在，跳过")
        return False

    content = target.read_text(encoding="utf-8")

    if PATCH_MARKER in content:
        print(f"  SKIP: {name} 已包含补丁标记，跳过")
        return True

    old_line = 'env.insert("ANTHROPIC_API_KEY".into(), "".into());'
    if old_line not in content:
        print(f"  WARN: {name} 中未找到目标代码片段，上游可能已修改，跳过")
        return False

    new_line = f"// {PATCH_MARKER} 已删除强制清空 ANTHROPIC_API_KEY"
    patched = content.replace(old_line, new_line, 1)

    if dry_run:
        print(f"  DRY-RUN: {name} 将替换目标代码行")
    else:
        target.write_text(patched, encoding="utf-8")
        print(f"  OK: {name} 补丁成功")
    return True


def patch_claude_env_passthrough(source_root: Path, dry_run: bool) -> bool:
    """补丁点 2: 在 claude.rs connect() 中透传系统环境变量。"""
    target = source_root / "crates/agent_servers/src/claude.rs"
    name = "claude.rs"

    if not target.exists():
        print(f"  WARN: {name} 不存在，跳过")
        return False

    content = target.read_text(encoding="utf-8")

    if PATCH_MARKER in content:
        print(f"  SKIP: {name} 已包含补丁标记，跳过")
        return True

    old_snippet = "let extra_env = load_proxy_env(cx);"
    if old_snippet not in content:
        print(f"  WARN: {name} 中未找到目标代码片段，上游可能已修改，跳过")
        return False

    new_snippet = """\
let mut extra_env = load_proxy_env(cx); // {marker}
        // 透传 Claude Code 相关系统环境变量
        for var_name in [
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_BASE_URL",
            "CLAUDE_CODE_USE_BEDROCK",
            "CLAUDE_CODE_USE_VERTEX",
        ] {{
            if let Ok(val) = std::env::var(var_name) {{
                extra_env.insert(var_name.into(), val);
            }}
        }}
        for (key, val) in std::env::vars() {{
            if key.starts_with("AWS_")
                || key.starts_with("GOOGLE_CLOUD_")
                || key == "CLOUD_ML_REGION"
            {{
                extra_env.insert(key, val);
            }}
        }}""".format(marker=PATCH_MARKER)

    patched = content.replace(old_snippet, new_snippet, 1)

    if dry_run:
        print(f"  DRY-RUN: {name} 将注入环境变量透传代码")
    else:
        target.write_text(patched, encoding="utf-8")
        print(f"  OK: {name} 补丁成功")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="编译前补丁：修复 Agent 插件环境变量被覆盖问题"
    )
    parser.add_argument(
        "--source-root",
        default="zed",
        help="Zed 源码根目录（默认: zed）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅检查，不实际修改文件",
    )
    args = parser.parse_args()

    source_root = Path(args.source_root)
    if not source_root.is_dir():
        print(f"ERROR: 源码目录 {source_root} 不存在")
        return 1

    print(f"源码目录: {source_root.resolve()}")
    if args.dry_run:
        print("模式: dry-run（不修改文件）\n")
    else:
        print("模式: 正式补丁\n")

    print("[补丁 1] 删除强制清空 ANTHROPIC_API_KEY")
    r1 = patch_remove_api_key_clear(source_root, args.dry_run)

    print("[补丁 2] Claude Code connect() 透传系统环境变量")
    r2 = patch_claude_env_passthrough(source_root, args.dry_run)

    print()
    if r1 and r2:
        print("全部补丁已就绪。")
        return 0
    else:
        print("部分补丁未能应用，请检查上方 WARN 信息。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
