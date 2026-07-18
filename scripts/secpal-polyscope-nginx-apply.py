#!/usr/bin/python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Apply the constrained SecPal Polyscope nginx manifest as root."""

from __future__ import annotations

import argparse
import os
import pathlib
import pwd
import stat
import subprocess
import sys
import tempfile

import polyscope_nginx


ALLOWED_USER = "secpal"
MANIFEST_PATH = pathlib.Path("/home/secpal/.local/state/polyscope/nginx-manifest.json")
TARGET_PATH = pathlib.Path("/etc/nginx/sites-available/preview.secpal.dev")
NGINX_BIN = pathlib.Path("/usr/sbin/nginx")
SYSTEMCTL_BIN = pathlib.Path("/usr/bin/systemctl")


def _safe_regular_root_file(path: pathlib.Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    return (
        stat.S_ISREG(metadata.st_mode)
        and metadata.st_uid == 0
        and stat.S_IMODE(metadata.st_mode) & 0o022 == 0
    )


def check_helper_components(
    *,
    nginx_bin: pathlib.Path,
    systemctl_bin: pathlib.Path,
    helper_paths: tuple[pathlib.Path, ...],
    require_root_ownership: bool,
) -> None:
    if require_root_ownership:
        for helper_path in helper_paths:
            if not _safe_regular_root_file(helper_path):
                raise RuntimeError(f"privileged helper component is not root-owned and mode-safe: {helper_path}")
    for executable in (nginx_bin, systemctl_bin):
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise RuntimeError(f"required fixed executable is missing or not executable: {executable}")


def check_environment(
    *,
    manifest_path: pathlib.Path,
    nginx_bin: pathlib.Path,
    systemctl_bin: pathlib.Path,
    expected_uid: int,
    helper_paths: tuple[pathlib.Path, ...],
    require_root_ownership: bool,
) -> dict[str, object]:
    check_helper_components(
        nginx_bin=nginx_bin,
        systemctl_bin=systemctl_bin,
        helper_paths=helper_paths,
        require_root_ownership=require_root_ownership,
    )
    return polyscope_nginx.load_manifest(manifest_path, expected_uid=expected_uid)


def _atomic_replace(path: pathlib.Path, content: bytes, mode: int) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.tmp-",
        dir=path.parent,
    )
    temporary_path = pathlib.Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def apply_manifest(
    *,
    manifest_path: pathlib.Path,
    target: pathlib.Path,
    nginx_bin: pathlib.Path,
    systemctl_bin: pathlib.Path,
    expected_uid: int,
) -> None:
    manifest = polyscope_nginx.load_manifest(manifest_path, expected_uid=expected_uid)
    rendered = polyscope_nginx.render_nginx_config(manifest).encode("utf-8")

    if target.is_symlink():
        raise RuntimeError(f"refusing to replace symbolic-link nginx target: {target}")
    if target.exists() and not target.is_file():
        raise RuntimeError(f"refusing to replace non-regular nginx target: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    previous_content = target.read_bytes() if target.exists() else None
    previous_mode = stat.S_IMODE(target.stat().st_mode) if target.exists() else 0o644
    if previous_content == rendered:
        return

    def restore() -> None:
        if previous_content is None:
            target.unlink(missing_ok=True)
        else:
            _atomic_replace(target, previous_content, previous_mode)

    _atomic_replace(target, rendered, 0o644)
    try:
        subprocess.run([str(nginx_bin), "-t"], check=True)
    except subprocess.CalledProcessError:
        restore()
        raise

    try:
        subprocess.run([str(systemctl_bin), "reload", "nginx"], check=True)
    except subprocess.CalledProcessError:
        restore()
        subprocess.run([str(nginx_bin), "-t"], check=True)
        subprocess.run([str(systemctl_bin), "reload", "nginx"], check=True)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply the fixed SecPal Polyscope nginx manifest.")
    parser.add_argument("--check", action="store_true", help="Validate the helper boundary without changing nginx.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    os.umask(0o077)
    os.environ["PATH"] = "/usr/sbin:/usr/bin"

    if os.geteuid() != 0:
        print("helper must run as root", file=sys.stderr)
        return 1
    sudo_user = os.environ.get("SUDO_USER", "")
    sudo_uid = os.environ.get("SUDO_UID", "")
    expected_user = pwd.getpwnam(ALLOWED_USER)
    if sudo_user != ALLOWED_USER or sudo_uid != str(expected_user.pw_uid):
        print(f"helper may only be invoked through sudo by {ALLOWED_USER}", file=sys.stderr)
        return 1

    helper_paths = (
        pathlib.Path(__file__).resolve(),
        pathlib.Path(polyscope_nginx.__file__).resolve(),
        pathlib.Path(__file__).with_name("polyscope-rollout.py").resolve(),
    )
    try:
        check_helper_components(
            nginx_bin=NGINX_BIN,
            systemctl_bin=SYSTEMCTL_BIN,
            helper_paths=helper_paths,
            require_root_ownership=True,
        )
        if not args.check:
            apply_manifest(
                manifest_path=MANIFEST_PATH,
                target=TARGET_PATH,
                nginx_bin=NGINX_BIN,
                systemctl_bin=SYSTEMCTL_BIN,
                expected_uid=expected_user.pw_uid,
            )
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Polyscope nginx helper failed: {error}", file=sys.stderr)
        return 1

    action = "check passed" if args.check else "configuration applied"
    print(f"Polyscope nginx helper {action}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
