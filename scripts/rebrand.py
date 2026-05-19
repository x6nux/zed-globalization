#!/usr/bin/env python3
"""
Rebrand script for ZedG (zed-globalization).

Applies all necessary renaming transformations from "zed" to "zedg" to the
upstream Zed source code. Designed to be run after each upstream sync.

Usage:
    python3 scripts/rebrand.py [--zed-dir ./zed] [--dry-run]
"""

import argparse
import logging
import os
import re
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read_file(path: Path) -> str | None:
    """Read a file and return its content, or None if it doesn't exist."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        log.warning("File not found: %s", path)
        return None
    except Exception as e:
        log.warning("Error reading %s: %s", path, e)
        return None


def write_file(path: Path, content: str, *, dry_run: bool = False) -> None:
    """Write content to a file (no-op in dry-run mode)."""
    if dry_run:
        return
    path.write_text(content, encoding="utf-8")


def apply_replacements(
    path: Path,
    replacements: list[tuple[str, str]],
    *,
    dry_run: bool = False,
    description: str = "",
) -> bool:
    """Apply a list of (old, new) string replacements to a file.

    Returns True if any changes were made.
    """
    content = read_file(path)
    if content is None:
        return False

    original = content
    for old, new in replacements:
        content = content.replace(old, new)

    if content == original:
        log.info("  [no change] %s%s", path, f" ({description})" if description else "")
        return False

    write_file(path, content, dry_run=dry_run)
    action = "would modify" if dry_run else "modified"
    log.info("  [%s] %s%s", action, path, f" ({description})" if description else "")
    return True


def apply_regex_replacements(
    path: Path,
    replacements: list[tuple[str, str, int]],
    *,
    dry_run: bool = False,
    description: str = "",
) -> bool:
    """Apply a list of (pattern, replacement, flags) regex replacements to a file.

    Returns True if any changes were made.
    """
    content = read_file(path)
    if content is None:
        return False

    original = content
    for pattern, repl, flags in replacements:
        new_content = re.sub(pattern, repl, content, flags=flags)
        if new_content == content:
            log.warning("  Pattern not matched in %s: %s", path, pattern[:80])
        content = new_content

    if content == original:
        log.info("  [no change] %s%s", path, f" ({description})" if description else "")
        return False

    write_file(path, content, dry_run=dry_run)
    action = "would modify" if dry_run else "modified"
    log.info("  [%s] %s%s", action, path, f" ({description})" if description else "")
    return True


# ---------------------------------------------------------------------------
# Category 1: SSH/Remote -- Runtime binary name detection (Rust code patches)
# ---------------------------------------------------------------------------

def patch_get_zed_cli_path(zed_dir: Path, *, dry_run: bool = False) -> bool:
    """Patch get_zed_cli_path() in util.rs to detect binary name at runtime."""
    path = zed_dir / "crates" / "util" / "src" / "util.rs"
    content = read_file(path)
    if content is None:
        return False

    # Check if the function already uses runtime detection (file_stem() or .file_name()
    # near get_zed_cli_path). If so, the patch is already applied or upstream adopted it.
    func_match = re.search(r'fn get_zed_cli_path\b.*?\n\}', content, re.DOTALL)
    if func_match:
        func_body = func_match.group(0)
        if "file_stem()" in func_body or ".file_name()" in func_body:
            log.info("  [already patched] %s (get_zed_cli_path already uses runtime detection)", path)
            return True

    # Find and replace the function body.
    # The current function hardcodes paths like "bin/zed.exe" and "../bin/zed".
    # We replace it to detect the actual binary name at runtime.
    old_body = '''    let possible_locations: &[&str] = if cfg!(target_os = "macos") {
        // On macOS, the zed executable and zed-cli are inside the app bundle,
        // so here ./cli is for both installed and development builds.
        &["./cli"]
    } else if cfg!(target_os = "windows") {
        // bin/zed.exe is for installed builds, ./cli.exe is for development builds.
        &["bin/zed.exe", "./cli.exe"]
    } else if cfg!(target_os = "linux") || cfg!(target_os = "freebsd") {
        // bin is the standard, ./cli is for the target directory in development builds.
        &["../bin/zed", "./cli"]
    } else {
        anyhow::bail!("unsupported platform for determining zed-cli path");
    };

    possible_locations
        .iter()
        .find_map(|p| {
            parent
                .join(p)
                .canonicalize()
                .ok()
                .filter(|p| p != &zed_path)
        })
        .with_context(|| {
            format!(
                "could not find zed-cli from any of: {}",
                possible_locations.join(", ")
            )
        })'''

    new_body = '''    // Detect the actual binary name at runtime so that renamed binaries
    // (e.g. "zedg" instead of "zed") work correctly.
    let exe_name = zed_path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("zed");

    let possible_locations: Vec<std::borrow::Cow<'_, str>> = if cfg!(target_os = "macos") {
        vec!["./cli".into()]
    } else if cfg!(target_os = "windows") {
        vec![
            format!("bin/{exe_name}.exe").into(),
            "./cli.exe".into(),
        ]
    } else if cfg!(target_os = "linux") || cfg!(target_os = "freebsd") {
        vec![
            format!("../libexec/{exe_name}").into(),
            format!("../bin/{exe_name}").into(),
            "./cli".into(),
        ]
    } else {
        anyhow::bail!("unsupported platform for determining zed-cli path");
    };

    possible_locations
        .iter()
        .find_map(|p| {
            parent
                .join(p.as_ref())
                .canonicalize()
                .ok()
                .filter(|p| p != &zed_path)
        })
        .with_context(|| {
            format!(
                "could not find zed-cli from any of: {}",
                possible_locations.iter().map(|c| c.as_ref()).collect::<Vec<_>>().join(", ")
            )
        })'''

    if old_body not in content:
        log.warning("  Pattern not found in %s for get_zed_cli_path()", path)
        return False

    content = content.replace(old_body, new_body)
    write_file(path, content, dry_run=dry_run)
    action = "would modify" if dry_run else "modified"
    log.info("  [%s] %s (get_zed_cli_path runtime detection)", action, path)
    return True


def patch_remote_server_crash_files(zed_dir: Path, *, dry_run: bool = False) -> bool:
    """Patch remote_server/src/server.rs to accept crash files from renamed binary."""
    path = zed_dir / "crates" / "remote_server" / "src" / "server.rs"
    content = read_file(path)
    if content is None:
        return False

    # Check if the crash file prefix check already uses runtime detection.
    # Look for exe_prefix variable which is unique to our patch, near the crash file filtering.
    if "exe_prefix" in content:
        log.info("  [already patched] %s (crash file prefix already uses runtime detection)", path)
        return True

    # Replace the hardcoded prefix check with a runtime-aware check.
    old_check = '''                    if !filename.starts_with("zed") {
                        continue;
                    }'''

    new_check = '''                    let exe_prefix = std::env::current_exe()
                        .ok()
                        .and_then(|p| p.file_stem().and_then(|s| s.to_str().map(|s| s.to_owned())));
                    let accepted = filename.starts_with("zed")
                        || exe_prefix.as_deref().is_some_and(|prefix| filename.starts_with(prefix));
                    if !accepted {
                        continue;
                    }'''

    if old_check not in content:
        log.warning("  Pattern not found in %s for crash file prefix check", path)
        return False

    content = content.replace(old_check, new_check)
    write_file(path, content, dry_run=dry_run)
    action = "would modify" if dry_run else "modified"
    log.info("  [%s] %s (crash file prefix check)", action, path)
    return True


def patch_main_crash_handler(zed_dir: Path, *, dry_run: bool = False) -> bool:
    """Patch zed/src/main.rs crash handler to detect binary name at runtime."""
    path = zed_dir / "crates" / "zed" / "src" / "main.rs"
    content = read_file(path)
    if content is None:
        return False

    old_binary = 'binary: "zed".to_string(),'
    new_binary = (
        'binary: std::env::current_exe().ok()'
        '.and_then(|p| p.file_stem().and_then(|s| s.to_str().map(|s| s.to_owned())))'
        '.unwrap_or_else(|| "zed".to_string()),'
    )

    # Check if the crash handler binary field already uses runtime detection.
    # Look for current_exe() near the binary: field assignment (not at the top of the function).
    if old_binary not in content:
        # The old pattern is gone -- check if it was replaced with runtime detection.
        if re.search(r'binary:\s*std::env::current_exe\(\)', content):
            log.info("  [already patched] %s (crash handler binary already uses runtime detection)", path)
            return True
        log.warning("  Pattern not found in %s for crash handler binary name", path)
        return False

    content = content.replace(old_binary, new_binary)
    write_file(path, content, dry_run=dry_run)
    action = "would modify" if dry_run else "modified"
    log.info("  [%s] %s (crash handler binary name)", action, path)
    return True


def apply_category_1(zed_dir: Path, *, dry_run: bool = False) -> None:
    """Category 1: SSH/Remote -- Runtime binary name detection."""
    log.info("Category 1: SSH/Remote runtime binary name detection")
    patch_get_zed_cli_path(zed_dir, dry_run=dry_run)
    patch_remote_server_crash_files(zed_dir, dry_run=dry_run)
    patch_main_crash_handler(zed_dir, dry_run=dry_run)


# ---------------------------------------------------------------------------
# Category 2: Windows AppxManifest files
# ---------------------------------------------------------------------------

def apply_category_2(zed_dir: Path, *, dry_run: bool = False) -> None:
    """Category 2: Windows AppxManifest files."""
    log.info("Category 2: Windows AppxManifest files")
    manifest_files = [
        zed_dir / "crates" / "explorer_command_injector" / "AppxManifest.xml",
        zed_dir / "crates" / "explorer_command_injector" / "AppxManifest-Preview.xml",
        zed_dir / "crates" / "explorer_command_injector" / "AppxManifest-Nightly.xml",
    ]

    replacements = [
        # Identity Name (but NOT PublisherDisplayName>Zed Industries)
        ('Name="ZedIndustries.Zed"', 'Name="ZedIndustries.ZedG"'),
        # DisplayName in Properties
        ("<DisplayName>Zed</DisplayName>", "<DisplayName>ZedG</DisplayName>"),
        ("<DisplayName>Zed Preview</DisplayName>", "<DisplayName>ZedG Preview</DisplayName>"),
        ("<DisplayName>Zed Nightly</DisplayName>", "<DisplayName>ZedG Nightly</DisplayName>"),
        # Application Id
        ('Application Id="Zed"', 'Application Id="ZedG"'),
        # Executable
        ('Executable="Zed.exe"', 'Executable="ZedG.exe"'),
        # VisualElements DisplayName
        ('DisplayName="Zed"', 'DisplayName="ZedG"'),
        ('DisplayName="Zed Preview"', 'DisplayName="ZedG Preview"'),
        ('DisplayName="Zed Nightly"', 'DisplayName="ZedG Nightly"'),
        # Description
        ('Description="Zed explorer command injector"', 'Description="ZedG explorer command injector"'),
        ('Description="Zed Preview explorer command injector"', 'Description="ZedG Preview explorer command injector"'),
        ('Description="Zed Nightly explorer command injector"', 'Description="ZedG Nightly explorer command injector"'),
        # Verb Id
        ('Id="OpenWithZed"', 'Id="OpenWithZedG"'),
        # SurrogateServer DisplayName
        ('DisplayName="Zed"', 'DisplayName="ZedG"'),
        ('DisplayName="Zed Preview"', 'DisplayName="ZedG Preview"'),
        ('DisplayName="Zed Nightly"', 'DisplayName="ZedG Nightly"'),
    ]

    for manifest_path in manifest_files:
        apply_replacements(manifest_path, replacements, dry_run=dry_run, description="AppxManifest")


# ---------------------------------------------------------------------------
# Category 3: IPC Protocol Scheme
# ---------------------------------------------------------------------------

def apply_category_3(zed_dir: Path, *, dry_run: bool = False) -> None:
    """Category 3: IPC Protocol Scheme (zed-cli:// and zed-dock-action://)."""
    log.info("Category 3: IPC Protocol Scheme")

    # zed-cli:// replacements
    cli_protocol_files = [
        zed_dir / "crates" / "cli" / "src" / "main.rs",
        zed_dir / "crates" / "zed" / "src" / "main.rs",
        zed_dir / "crates" / "zed" / "src" / "zed" / "windows_only_instance.rs",
        zed_dir / "crates" / "zed" / "src" / "zed" / "open_listener.rs",
        zed_dir / "crates" / "zed" / "src" / "zed" / "open_url_modal.rs",
    ]

    for file_path in cli_protocol_files:
        apply_replacements(
            file_path,
            [("zed-cli://", "zedg-cli://")],
            dry_run=dry_run,
            description="zed-cli:// protocol",
        )

    # zed-dock-action:// replacements
    dock_protocol_files = [
        zed_dir / "crates" / "zed" / "src" / "zed" / "windows_only_instance.rs",
        zed_dir / "crates" / "zed" / "src" / "zed" / "open_listener.rs",
    ]

    for file_path in dock_protocol_files:
        apply_replacements(
            file_path,
            [("zed-dock-action://", "zedg-dock-action://")],
            dry_run=dry_run,
            description="zed-dock-action:// protocol",
        )


# ---------------------------------------------------------------------------
# Category 4: Windows App Identifiers
# ---------------------------------------------------------------------------

def apply_category_4(zed_dir: Path, *, dry_run: bool = False) -> None:
    """Category 4: Windows App Identifiers in release_channel."""
    log.info("Category 4: Windows App Identifiers")

    path = zed_dir / "crates" / "release_channel" / "src" / "lib.rs"
    replacements = [
        ('"Zed-Editor-Dev"', '"ZedG-Editor-Dev"'),
        ('"Zed-Editor-Nightly"', '"ZedG-Editor-Nightly"'),
        ('"Zed-Editor-Preview"', '"ZedG-Editor-Preview"'),
        ('"Zed-Editor-Stable"', '"ZedG-Editor-Stable"'),
    ]
    apply_replacements(path, replacements, dry_run=dry_run, description="app_identifier()")


# ---------------------------------------------------------------------------
# Category 5: Windows build resources
# ---------------------------------------------------------------------------

def apply_category_5(zed_dir: Path, *, dry_run: bool = False) -> None:
    """Category 5: Windows build resources (build.rs)."""
    log.info("Category 5: Windows build resources")

    path = zed_dir / "crates" / "zed" / "build.rs"
    replacements = [
        ('res.set("FileDescription", "Zed")', 'res.set("FileDescription", "ZedG")'),
        ('res.set("ProductName", "Zed")', 'res.set("ProductName", "ZedG")'),
    ]
    apply_replacements(path, replacements, dry_run=dry_run, description="build.rs")


# ---------------------------------------------------------------------------
# Category 6: Windows installer and bundle scripts
# ---------------------------------------------------------------------------

def patch_zed_iss(zed_dir: Path, *, dry_run: bool = False) -> None:
    """Patch zed.iss (Inno Setup script)."""
    path = zed_dir / "crates" / "zed" / "resources" / "windows" / "zed.iss"
    content = read_file(path)
    if content is None:
        return

    original = content

    # Replace the Source line for Zed.exe -> ZedG.exe
    content = content.replace(
        'Source: "{#ResourcesDir}\\Zed.exe"',
        'Source: "{#ResourcesDir}\\ZedG.exe"',
    )

    # URI scheme registry: {app}\Zed.exe -> {app}\{#AppExeName}.exe
    content = content.replace(
        'ValueData: "{app}\\Zed.exe,1"',
        'ValueData: "{app}\\{#AppExeName}.exe,1"',
    )
    content = content.replace(
        'ValueData: """{app}\\Zed.exe"" ""%1"""',
        'ValueData: """{app}\\{#AppExeName}.exe"" ""%1"""',
    )

    if content == original:
        log.info("  [no change] %s (zed.iss)", path)
        return

    write_file(path, content, dry_run=dry_run)
    action = "would modify" if dry_run else "modified"
    log.info("  [%s] %s (zed.iss)", action, path)


def patch_zed_sh(zed_dir: Path, *, dry_run: bool = False) -> None:
    """Patch zed.sh WSL bridge script."""
    path = zed_dir / "crates" / "zed" / "resources" / "windows" / "zed.sh"
    replacements = [
        ("zed.exe", "zedg.exe"),
    ]
    apply_replacements(path, replacements, dry_run=dry_run, description="zed.sh WSL bridge")


def patch_bundle_windows(zed_dir: Path, *, dry_run: bool = False) -> None:
    """Patch script/bundle-windows.ps1."""
    path = zed_dir / "script" / "bundle-windows.ps1"
    content = read_file(path)
    if content is None:
        return

    original = content

    # -- Channel-specific variable assignments --

    # Stable channel
    content = content.replace('$appName = "Zed"', '$appName = "ZedG"')
    content = content.replace('$appDisplayName = "Zed"', '$appDisplayName = "ZedG"')
    content = content.replace('$appMutex = "Zed-Stable-Instance-Mutex"', '$appMutex = "ZedG-Editor-Stable-Instance-Mutex"')
    content = content.replace('$appExeName = "Zed"', '$appExeName = "ZedG"')
    content = content.replace('$regValueName = "Zed"', '$regValueName = "ZedG"')
    content = content.replace('$appUserId = "ZedIndustries.Zed"', '$appUserId = "ZedIndustries.ZedG"')
    content = content.replace('$appShellNameShort = "Z&ed"', '$appShellNameShort = "Z&edG"')
    content = content.replace(
        '$appAppxFullName = "ZedIndustries.Zed_1.0.0.0_neutral__japxn1gcva8rg"',
        '$appAppxFullName = "ZedIndustries.ZedG_1.0.0.0_neutral__japxn1gcva8rg"',
    )

    # Preview channel
    content = content.replace('$appName = "Zed Preview"', '$appName = "ZedG Preview"')
    content = content.replace('$appDisplayName = "Zed Preview"', '$appDisplayName = "ZedG Preview"')
    content = content.replace('$appSetupName = "Zed-$Architecture"', '$appSetupName = "ZedG-$Architecture"', 4)
    content = content.replace('$appMutex = "Zed-Preview-Instance-Mutex"', '$appMutex = "ZedG-Editor-Preview-Instance-Mutex"')
    content = content.replace('$regValueName = "ZedPreview"', '$regValueName = "ZedGPreview"')
    content = content.replace('$appUserId = "ZedIndustries.Zed.Preview"', '$appUserId = "ZedIndustries.ZedG.Preview"')
    content = content.replace('$appShellNameShort = "Z&ed Preview"', '$appShellNameShort = "Z&edG Preview"')
    content = content.replace(
        '$appAppxFullName = "ZedIndustries.Zed.Preview_1.0.0.0_neutral__japxn1gcva8rg"',
        '$appAppxFullName = "ZedIndustries.ZedG.Preview_1.0.0.0_neutral__japxn1gcva8rg"',
    )

    # Nightly channel
    content = content.replace('$appName = "Zed Nightly"', '$appName = "ZedG Nightly"')
    content = content.replace('$appDisplayName = "Zed Nightly"', '$appDisplayName = "ZedG Nightly"')
    content = content.replace('$appMutex = "Zed-Nightly-Instance-Mutex"', '$appMutex = "ZedG-Editor-Nightly-Instance-Mutex"')
    content = content.replace('$regValueName = "ZedNightly"', '$regValueName = "ZedGNightly"')
    content = content.replace('$appUserId = "ZedIndustries.Zed.Nightly"', '$appUserId = "ZedIndustries.ZedG.Nightly"')
    content = content.replace('$appShellNameShort = "Z&ed Editor Nightly"', '$appShellNameShort = "Z&edG Editor Nightly"')
    content = content.replace(
        '$appAppxFullName = "ZedIndustries.Zed.Nightly_1.0.0.0_neutral__japxn1gcva8rg"',
        '$appAppxFullName = "ZedIndustries.ZedG.Nightly_1.0.0.0_neutral__japxn1gcva8rg"',
    )

    # Dev channel
    content = content.replace('$appName = "Zed Dev"', '$appName = "ZedG Dev"')
    content = content.replace('$appDisplayName = "Zed Dev"', '$appDisplayName = "ZedG Dev"')
    content = content.replace('$appMutex = "Zed-Dev-Instance-Mutex"', '$appMutex = "ZedG-Editor-Dev-Instance-Mutex"')
    content = content.replace('$regValueName = "ZedDev"', '$regValueName = "ZedGDev"')
    content = content.replace('$appUserId = "ZedIndustries.Zed.Dev"', '$appUserId = "ZedIndustries.ZedG.Dev"')
    content = content.replace('$appShellNameShort = "Z&ed Dev"', '$appShellNameShort = "Z&edG Dev"')
    content = content.replace(
        '$appAppxFullName = "ZedIndustries.Zed.Dev_1.0.0.0_neutral__japxn1gcva8rg"',
        '$appAppxFullName = "ZedIndustries.ZedG.Dev_1.0.0.0_neutral__japxn1gcva8rg"',
    )

    # -- Build function: Copy and Sign lines --
    # Copy-Item line: "Zed.exe" -> "ZedG.exe"
    content = content.replace(
        'Copy-Item -Path ".\\$CargoOutDir\\zed.exe" -Destination "$innoDir\\Zed.exe" -Force',
        'Copy-Item -Path ".\\$CargoOutDir\\zed.exe" -Destination "$innoDir\\ZedG.exe" -Force',
    )
    # Sign line: "Zed.exe" in the files list
    content = content.replace(
        '$files = "$innoDir\\Zed.exe,',
        '$files = "$innoDir\\ZedG.exe,',
    )

    # -- CollectFiles function --
    # bin\zed.exe -> bin\zedg.exe (CLI -> bin)
    content = content.replace(
        'Move-Item -Path "$innoDir\\cli.exe" -Destination "$innoDir\\bin\\zed.exe" -Force',
        'Move-Item -Path "$innoDir\\cli.exe" -Destination "$innoDir\\bin\\zedg.exe" -Force',
    )
    # zed.sh -> zed (WSL bridge, the destination name stays as "zed" since it's the shell script name)
    # Actually, the WSL bridge script's destination filename is just "zed" (no extension).
    # This line keeps the destination the same - the WSL bridge is invoked as "zed" in bin/.

    if content == original:
        log.info("  [no change] %s (bundle-windows.ps1)", path)
        return

    write_file(path, content, dry_run=dry_run)
    action = "would modify" if dry_run else "modified"
    log.info("  [%s] %s (bundle-windows.ps1)", action, path)


def apply_category_6(zed_dir: Path, *, dry_run: bool = False) -> None:
    """Category 6: Windows installer and bundle scripts."""
    log.info("Category 6: Windows installer and bundle scripts")
    patch_zed_iss(zed_dir, dry_run=dry_run)
    patch_zed_sh(zed_dir, dry_run=dry_run)
    patch_bundle_windows(zed_dir, dry_run=dry_run)


# ---------------------------------------------------------------------------
# Category 7: Auto-update redirect to ZedG GitHub releases
# ---------------------------------------------------------------------------

def apply_category_7(zed_dir: Path, *, dry_run: bool = False) -> None:
    """Category 7: Auto-update redirect to GitHub releases."""
    log.info("Category 7: Auto-update redirect to GitHub releases")

    auto_update = zed_dir / "crates" / "auto_update" / "src" / "auto_update.rs"
    content = read_file(auto_update)
    if content is None:
        return

    original = content

    # 7a. Add import for github module (idempotent check)
    if "latest_github_release" not in content:
        pat = r'(use\s+http_client::\{[^}]*HttpClientWithUrl[^}]*\};)'
        repl = r'\1\nuse http_client::github::latest_github_release;'
        new_content = re.sub(pat, repl, content, count=1)
        if new_content == content:
            log.warning("  Pattern not matched for github import in %s", auto_update)
        else:
            content = new_content
            log.info("  [patched] %s (add github import)", auto_update)
    else:
        log.info("  [already patched] %s (github import)", auto_update)

    # 7b. Add ZedG constants (idempotent check)
    if "ZEDG_GITHUB_REPO" not in content:
        pat = r'(const\s+SHOULD_SHOW_UPDATE_NOTIFICATION_KEY:\s*&str\s*=\s*"auto-updater-should-show-updated-notification";)'
        repl = (
            r'\1\n'
            r'const ZEDG_GITHUB_REPO: &str = "x6nux/zed-globalization";' '\n'
            r'const ZEDG_LANG: &str = "zh-cn";'
        )
        new_content = re.sub(pat, repl, content, count=1)
        if new_content == content:
            log.warning("  Pattern not matched for ZedG constants in %s", auto_update)
        else:
            content = new_content
            log.info("  [patched] %s (add ZedG constants)", auto_update)
    else:
        log.info("  [already patched] %s (ZedG constants)", auto_update)

    # 7c. Dispatch app updates to GitHub in get_release_asset() (idempotent check)
    if "get_release_asset_from_github" not in content:
        # Match: `let client = this.read_with(cx, ...)` followed by
        #        `let (system_id, metrics_id, is_staff) = ...`
        # Use regex to tolerate whitespace/formatting changes between these two statements.
        pat = (
            r'(\s*)'                                          # capture leading indent
            r'(let\s+client\s*=\s*this\.read_with\(cx,\s*\|this,\s*_\|\s*this\.client\.clone\(\)\);)'
            r'(\s*)'                                          # flexible whitespace between
            r'(let\s+\(system_id,\s*metrics_id,\s*is_staff\)\s*=\s*if\s+client\.telemetry\(\)\.metrics_enabled\(\))'
        )

        def _insert_github_dispatch(m: re.Match) -> str:
            indent = m.group(1)
            client_line = m.group(2)
            sep = m.group(3)
            destructure_line = m.group(4)
            dispatch_block = (
                f"{indent}// For ZedG app self-updates, use GitHub releases\n"
                f"{indent}if asset == \"zed\" {{\n"
                f"{indent}    let http: Arc<dyn HttpClient> =\n"
                f"{indent}        this.read_with(cx, |this, _| this.client.http_client());\n"
                f"{indent}    return Self::get_release_asset_from_github(os, arch, http).await;\n"
                f"{indent}}}\n"
            )
            return f"{dispatch_block}\n{indent}{client_line}{sep}{destructure_line}"

        new_content = re.sub(pat, _insert_github_dispatch, content, count=1)
        if new_content == content:
            log.warning("  Pattern not matched for GitHub dispatch in %s", auto_update)
        else:
            content = new_content

        # 7d. Insert get_release_asset_from_github() function before update()
        pat_update_fn = r'(\n)([ \t]*)(async\s+fn\s+update\s*\(\s*this:\s*Entity<Self>.*?\)\s*->\s*Result<\(\)>\s*\{)'
        github_fn = (
            "    async fn get_release_asset_from_github(\n"
            "        os: &str,\n"
            "        arch: &str,\n"
            "        http: Arc<dyn HttpClient>,\n"
            "    ) -> Result<ReleaseAsset> {\n"
            '        let asset_prefix = format!("zedg-{}-{}-{}-", ZEDG_LANG, os, arch);\n'
            "\n"
            "        let release =\n"
            "            match latest_github_release(ZEDG_GITHUB_REPO, true, false, http.clone()).await {\n"
            "                Ok(r) => r,\n"
            "                Err(_) => latest_github_release(ZEDG_GITHUB_REPO, true, true, http)\n"
            "                    .await\n"
            '                    .context("failed to fetch any GitHub release")?,\n'
            "            };\n"
            "\n"
            "        let matched_asset = release\n"
            "            .assets\n"
            "            .iter()\n"
            "            .find(|a| a.name.starts_with(&asset_prefix))\n"
            "            .with_context(|| {\n"
            "                format!(\n"
            "                    \"no matching asset for prefix '{}' in release '{}'\",\n"
            "                    asset_prefix, release.tag_name\n"
            "                )\n"
            "            })?;\n"
            "\n"
            "        let tag = release.tag_name.strip_prefix('v').unwrap_or(&release.tag_name);\n"
            "        let version = tag\n"
            "            .split('-')\n"
            "            .next()\n"
            "            .unwrap_or(tag)\n"
            "            .splitn(4, '.')\n"
            "            .take(3)\n"
            "            .collect::<Vec<_>>()\n"
            '            .join(".");\n'
            "\n"
            "        Ok(ReleaseAsset {\n"
            "            version,\n"
            "            url: matched_asset.browser_download_url.clone(),\n"
            "        })\n"
            "    }\n"
        )

        def _insert_github_fn(m: re.Match) -> str:
            return f"\n\n{github_fn}\n{m.group(2)}{m.group(3)}"

        new_content2 = re.sub(pat_update_fn, _insert_github_fn, content, count=1)
        if new_content2 == content:
            log.warning("  Pattern not matched for update() function in %s", auto_update)
        else:
            content = new_content2

        log.info("  [patched] %s (dispatch + new function)", auto_update)
    else:
        log.info("  [already patched] %s (GitHub dispatch + function)", auto_update)

    # 7e. Windows target path: Zed.exe -> ZedG.msi
    if '"windows" => Ok("Zed.exe"),' in content:
        content = content.replace(
            '"windows" => Ok("Zed.exe"),',
            '"windows" => Ok("ZedG.msi"),',
        )
        log.info("  [patched] %s (Windows target path)", auto_update)
    else:
        log.info("  [already patched] %s (Windows target path)", auto_update)

    # 7f. Windows install: replace entire install_release_windows function body
    if "get_release_asset_from_github" in content and 'new_command("msiexec")' not in content:
        # Match the full function: signature through closing brace, using lookahead
        # to stop at the next function definition or end of impl block.
        pat_install = (
            r'(?P<sig>async\s+fn\s+install_release_windows\s*\(\s*downloaded_installer:\s*&Path\s*\)'
            r'\s*->\s*Result<Option<PathBuf>>\s*\{)'
            r'(?P<body>.*?)'
            r'(?P<close>\n[ \t]*\})'
            r'(?=\s*(?:async\s+fn|pub\s|fn\s|\}))'  # lookahead: next function or end of impl
        )
        replacement_body = (
            r'\g<sig>\n'
            '    let mut cmd = new_command("msiexec");\n'
            '    cmd.args(["/quiet", "/i"])\n'
            '        .arg(downloaded_installer);\n'
            '    let output = cmd.output().await?;\n'
            '    anyhow::ensure!(\n'
            '        output.status.success(),\n'
            '        "failed to run msiexec: {:?}",\n'
            '        String::from_utf8_lossy(&output.stderr)\n'
            '    );\n'
            '    Ok(None)\n'
            r'\g<close>'
        )
        new_content = re.sub(pat_install, replacement_body, content, count=1, flags=re.DOTALL)
        if new_content == content:
            log.warning("  Pattern not matched for install_release_windows in %s", auto_update)
        else:
            content = new_content
            log.info("  [patched] %s (Windows MSI installer)", auto_update)
    elif 'new_command("msiexec")' in content:
        log.info("  [already patched] %s (Windows MSI installer)", auto_update)

    # 7g. macOS DMG mount path
    pat_mount = r'(let\s+mount_path\s*=\s*temp_dir\.path\(\)\.join\()"Zed"(\))'
    if re.search(pat_mount, content):
        content = re.sub(pat_mount, r'\1"ZedG"\2', content, count=1)
        log.info("  [patched] %s (macOS DMG mount path)", auto_update)
    else:
        log.info("  [already patched] %s (macOS DMG mount path)", auto_update)

    # Write all changes at once
    if content != original:
        write_file(auto_update, content, dry_run=dry_run)
    else:
        log.info("  [no change] %s", auto_update)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply ZedG rebrand transformations to the Zed source tree."
    )
    parser.add_argument(
        "--zed-dir",
        type=str,
        default="./zed",
        help="Path to the Zed source directory (default: ./zed)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without modifying files",
    )
    args = parser.parse_args()

    zed_dir = Path(args.zed_dir).resolve()
    if not zed_dir.is_dir():
        log.error("Zed directory does not exist: %s", zed_dir)
        return 1

    log.info("Zed source directory: %s", zed_dir)
    if args.dry_run:
        log.info("DRY RUN mode -- no files will be modified")
    log.info("")

    categories = [
        apply_category_1,
        apply_category_2,
        apply_category_3,
        apply_category_4,
        apply_category_5,
        apply_category_6,
        apply_category_7,
    ]

    class WarningCounter(logging.Handler):
        count = 0
        def emit(self, record: logging.LogRecord) -> None:
            if record.levelno >= logging.WARNING:
                self.count += 1

    counter = WarningCounter()
    logging.root.addHandler(counter)

    for fn in categories:
        fn(zed_dir, dry_run=args.dry_run)
        log.info("")

    logging.root.removeHandler(counter)

    if counter.count > 0:
        log.error("Done with %d warning(s) — some patches may not have been applied.", counter.count)
        return 1

    log.info("Done — all patches applied successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
