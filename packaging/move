#!/usr/bin/env bash

allowed_targets=("linux-targz" "macos")
is_allowed_target() {
    for val in "${allowed_targets[@]}"; do
        if [[ "$1" == "$val" ]]; then
            return 0
        fi
    done
    return 1
}

if [[ -n "${1:-}" ]]; then
    if is_allowed_target "$1"; then
        target="$1"
    else
        echo "Error: Target '$1' is not allowed"
        echo "Usage: $0 [${allowed_targets[*]}]"
        exit 1
    fi
else
    echo "Error: Target is not specified"
    echo "Usage: $0 [${allowed_targets[*]}]"
    exit 1
fi
echo "Processing nightly for target: $target"

bucket_name="zed-nightly-host"

sha=$(git rev-parse HEAD)
echo ${sha} > target/latest-sha

find target -type f -name "zed-remote-server-*.gz" -print0 | while IFS= read -r -d '' file_to_move; do
    mv "$file_to_move" "$(basename "$file_to_move")"
done

case "$target" in
    macos)
        mv "zed/target/aarch64-apple-darwin/release/Zed.dmg" "Zed-aarch64.dmg"
        mv "zed/target/x86_64-apple-darwin/release/Zed.dmg" "Zed-x86_64.dmg"
        mv "zed/target/latest-sha" "latest-sha"
        ;;
    linux-targz)
        find . -type f -name "zed-*.tar.gz" -print0 | while IFS= read -r -d '' file_to_move; do
            mv "$file_to_move" "$(basename "$file_to_move")"
        done
        mv "zed/target/latest-sha" "latest-sha-linux-targz"
        ;;
    *)
        echo "Error: Unknown target '$target'"
        exit 1
        ;;
esac
