#!/usr/bin/env bash
# zedg-activate.sh — 把 ZedG 注册为系统里的 `zed`（生态兼容开关）
#
# 适用于 macOS / Linux 手动解压安装的用户。功能：
#   1. 创建 ~/.local/bin/zed → ZedG 的符号链接（生态工具/git difftool/终端识别）
#   2. 注册/更新 desktop 入口（应用列表、"默认编辑器"选择器）
#   3. --revert 一键还原到官方状态
#
# 用法:
#   ./zedg-activate.sh            # 激活生态兼容
#   ./zedg-activate.sh --revert   # 还原
#   ./zedg-activate.sh --status   # 查看当前状态
set -euo pipefail

BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/zedg"
DESKTOP_DIR="$HOME/.local/share/applications"
ZEDG_CANDIDATES=(
  "$APP_DIR/ZedG.app/Contents/MacOS/zedg"
  "$APP_DIR/zedg"
  "/usr/local/bin/zedg"
  "/usr/bin/zedg"
)
OFFICIAL_CANDIDATES=(
  "/Applications/Zed.app/Contents/MacOS/zed"
  "$HOME/.local/bin/zed.orig"
  "/usr/bin/zed"
)

find_zedg() {
  for c in "${ZEDG_CANDIDATES[@]}"; do
    [ -x "$c" ] && { echo "$c"; return 0; }
  done
  return 1
}

find_official_zed() {
  for c in "${OFFICIAL_CANDIDATES[@]}"; do
    [ -x "$c" ] && { echo "$c"; return 0; }
  done
  return 1
}

do_status() {
  echo "== ZedG 生态兼容状态 =="
  if [ -L "$BIN_DIR/zed" ]; then
    echo "  ~/.local/bin/zed -> $(readlink "$BIN_DIR/zed")  [已激活]"
  elif [ -x "$BIN_DIR/zed" ]; then
    echo "  ~/.local/bin/zed 是独立文件（可能是官方安装）       [未接管]"
  else
    echo "  ~/.local/bin/zed 不存在                           [未接管]"
  fi
  command -v zedg >/dev/null 2>&1 \
    && echo "  zedg: $(command -v zedg)" \
    || echo "  zedg: 未安装"
}

do_activate() {
  ZEDG_BIN="$(find_zedg)" || {
    echo "✗ 未找到 ZedG 可执行文件，请先安装 ZedG" >&2
    exit 1
  }
  mkdir -p "$BIN_DIR" "$DESKTOP_DIR"

  # 1. zed 符号链接（备份官方二进制——若它是独立文件而非我们的链接）
  if [ -e "$BIN_DIR/zed" ] && [ ! -L "$BIN_DIR/zed" ]; then
    cp "$BIN_DIR/zed" "$BIN_DIR/zed.orig"
    echo "  已备份官方 zed → zed.orig"
  fi
  ln -sf "$ZEDG_BIN" "$BIN_DIR/zed"
  echo "✓ $BIN_DIR/zed -> $ZEDG_BIN"

  # 2. PATH 提示
  case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) echo "⚠ $BIN_DIR 不在 PATH 中，请将其加入 ~/.zshrc 或 ~/.bashrc" ;;
  esac

  # 3. desktop 入口（Linux；macOS 用 app bundle 自身的 Info.plist）
  if [ "$(uname)" = "Linux" ]; then
    for name in zed zedg; do
      cat > "$DESKTOP_DIR/$name.desktop" <<DESKTOP
[Desktop Entry]
Version=1.0
Type=Application
Name=ZedG${name:+ ($name)}
GenericName=Text Editor
Comment=Zed 编辑器多语言版
Exec=$ZEDG_BIN %F
Icon=$APP_DIR/zedg.png
Categories=Utility;TextEditor;Development;IDE;
MimeType=text/plain;text/x-rust;text/x-python;application/json;
StartupNotify=true
DESKTOP
    done
    command -v update-desktop-database >/dev/null 2>&1 \
      && update-desktop-database "$DESKTOP_DIR" || true
    echo "✓ desktop 入口已注册（zed + zedg）"
  fi

  echo "完成。终端运行 'zed' 或从应用列表启动即为 ZedG。"
  echo "还原: $0 --revert"
}

do_revert() {
  # 还原符号链接
  if [ -L "$BIN_DIR/zed" ]; then
    if [ -e "$BIN_DIR/zed.orig" ]; then
      mv "$BIN_DIR/zed.orig" "$BIN_DIR/zed"
      echo "✓ 已还原官方 zed（来自 zed.orig）"
    else
      rm "$BIN_DIR/zed"
      echo "✓ 已移除 zed 链接（无官方备份可还原）"
    fi
  else
    echo "  zed 链接不存在，无需还原"
  fi

  # 移除我们注册的 desktop 入口
  if [ "$(uname)" = "Linux" ]; then
    rm -f "$DESKTOP_DIR/zed.desktop" "$DESKTOP_DIR/zedg.desktop"
    command -v update-desktop-database >/dev/null 2>&1 \
      && update-desktop-database "$DESKTOP_DIR" || true
    echo "✓ desktop 入口已移除"
  fi

  echo "还原完成。"
}

case "${1:-}" in
  --revert) do_revert ;;
  --status) do_status ;;
  "")       do_activate ;;
  *) echo "用法: $0 [--revert|--status]"; exit 2 ;;
esac
