#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 5 ]; then
  echo "Usage: $0 <staging_dir> <arch> <version> <lang_lower> <output_path>" >&2
  exit 2
fi

STAGING_DIR="$1"
ARCH="$2"
VERSION="$3"
LANG_LOWER="$4"
OUTPUT_PATH="$5"

if [ ! -d "$STAGING_DIR" ]; then
  echo "staging_dir does not exist: $STAGING_DIR" >&2
  exit 1
fi

case "$ARCH" in
  x86_64|aarch64) ;;
  *)
    echo "unsupported RPM architecture: $ARCH" >&2
    exit 1
    ;;
esac

CLEAN_VERSION="${VERSION#v}"

fpm -s dir -t rpm \
  -n zedg \
  -v "$CLEAN_VERSION" \
  --iteration 1 \
  --architecture "$ARCH" \
  --description "Zed editor with globalization support." \
  --url "https://github.com/x6nux/zed-globalization" \
  --license "MIT" \
  --maintainer "zed-globalization" \
  --depends "glibc" \
  --rpm-summary "Zed editor with globalization support" \
  -C "$STAGING_DIR" \
  -p "$OUTPUT_PATH" \
  .
