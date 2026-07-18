#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
WORKSPACE="$(mktemp -d "${TMPDIR:-/tmp}/polyscope-nginx-helper.XXXXXX")"
trap 'rm -rf "$WORKSPACE"' EXIT

python3 -B - "$REPO_ROOT" "$WORKSPACE" <<'PY'
import copy
import importlib.util
import json
import os
import pathlib
import subprocess
import sys

repo_root = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
library_path = repo_root / "scripts" / "polyscope_nginx.py"
helper_path = repo_root / "scripts" / "secpal-polyscope-nginx-apply.py"

library_spec = importlib.util.spec_from_file_location("polyscope_nginx", library_path)
library = importlib.util.module_from_spec(library_spec)
assert library_spec.loader is not None
sys.modules["polyscope_nginx"] = library
library_spec.loader.exec_module(library)

helper_spec = importlib.util.spec_from_file_location("secpal_polyscope_nginx_apply", helper_path)
helper = importlib.util.module_from_spec(helper_spec)
assert helper_spec.loader is not None
helper_spec.loader.exec_module(helper)

manifest = {
    "version": 1,
    "preview_domain": "preview.secpal.dev",
    "clone_root": "/home/secpal/.polyscope/clones",
    "repositories": {
        "api": "d35c0cdc",
        "frontend": "b6624c93",
        "GuardGuide": "8fadd2fb",
        "secpal.app": "c46a8454",
        "guardguide.de": "3d0fcf01",
        "changelog": "0a40ecd7",
    },
    "php_upstream": {
        "kind": "unix",
        "path": "/run/php/php8.4-fpm-secpal-preview.sock",
    },
    "nginx_http2_syntax": "modern",
}


def write_manifest(path: pathlib.Path, payload: object, mode: int = 0o600) -> None:
    path.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    path.chmod(mode)


manifest_path = workspace / "manifest.json"
write_manifest(manifest_path, manifest)
loaded = library.load_manifest(manifest_path, expected_uid=os.getuid())
rendered = library.render_nginx_config(loaded)
assert "preview\\.secpal\\.dev" in rendered
assert "d35c0cdc" in rendered
assert "fastcgi_pass unix:/run/php/php8.4-fpm-secpal-preview.sock;" in rendered

invalid_payloads = []
for key, value in (
    ("unexpected", True),
    ("raw_nginx", "load_module /tmp/evil.so;"),
):
    payload = copy.deepcopy(manifest)
    payload[key] = value
    invalid_payloads.append(payload)

payload = copy.deepcopy(manifest)
payload["preview_domain"] = "preview.secpal.dev; include /tmp/evil.conf"
invalid_payloads.append(payload)
payload = copy.deepcopy(manifest)
payload["php_upstream"] = {"kind": "tcp", "host": "203.0.113.7", "port": 9000}
invalid_payloads.append(payload)
for port in (0, 65536, "9000"):
    payload = copy.deepcopy(manifest)
    payload["php_upstream"] = {"kind": "tcp", "host": "127.0.0.1", "port": port}
    invalid_payloads.append(payload)
payload = copy.deepcopy(manifest)
payload["repositories"]["api"] = "../../etc"
invalid_payloads.append(payload)

for index, payload in enumerate(invalid_payloads):
    candidate = workspace / f"invalid-{index}.json"
    write_manifest(candidate, payload)
    try:
        library.load_manifest(candidate, expected_uid=os.getuid())
    except ValueError:
        pass
    else:
        raise AssertionError(payload)

unsafe_mode = workspace / "unsafe-mode.json"
write_manifest(unsafe_mode, manifest, mode=0o644)
try:
    library.load_manifest(unsafe_mode, expected_uid=os.getuid())
except ValueError as error:
    assert "mode" in str(error).lower(), error
else:
    raise AssertionError("unsafe manifest mode accepted")

wrong_owner = workspace / "wrong-owner.json"
write_manifest(wrong_owner, manifest)
try:
    library.load_manifest(wrong_owner, expected_uid=os.getuid() + 1)
except ValueError as error:
    assert "owner" in str(error).lower(), error
else:
    raise AssertionError("wrong manifest owner accepted")

symlink_manifest = workspace / "manifest-link.json"
symlink_manifest.symlink_to(manifest_path.name)
try:
    library.load_manifest(symlink_manifest, expected_uid=os.getuid())
except ValueError as error:
    assert "symbolic link" in str(error).lower(), error
else:
    raise AssertionError("symlink manifest accepted")

fifo_manifest = workspace / "manifest-fifo.json"
os.mkfifo(fifo_manifest, 0o600)
try:
    library.load_manifest(fifo_manifest, expected_uid=os.getuid())
except ValueError as error:
    assert "regular file" in str(error).lower(), error
else:
    raise AssertionError("FIFO manifest accepted")

oversized = workspace / "oversized.json"
oversized.write_bytes(b"{" + b" " * (library.MAX_MANIFEST_BYTES + 1) + b"}")
oversized.chmod(0o600)
try:
    library.load_manifest(oversized, expected_uid=os.getuid())
except ValueError as error:
    assert "size" in str(error).lower(), error
else:
    raise AssertionError("oversized manifest accepted")

malformed = workspace / "malformed.json"
malformed.write_text("{not-json\n")
malformed.chmod(0o600)
try:
    library.load_manifest(malformed, expected_uid=os.getuid())
except ValueError as error:
    assert "utf-8 json" in str(error).lower(), error
else:
    raise AssertionError("malformed manifest accepted")

fake_bin = workspace / "fake-bin"
fake_bin.mkdir()
command_log = workspace / "commands.log"
nginx_bin = fake_bin / "nginx"
systemctl_bin = fake_bin / "systemctl"
nginx_bin.write_text(
    "#!/usr/bin/env bash\n"
    "printf 'nginx:%s\\n' \"$*\" >>\"$HELPER_COMMAND_LOG\"\n"
    "if [[ ${FAIL_NGINX_TEST:-0} == 1 ]]; then exit 41; fi\n"
)
systemctl_bin.write_text(
    "#!/usr/bin/env bash\n"
    "printf 'systemctl:%s\\n' \"$*\" >>\"$HELPER_COMMAND_LOG\"\n"
    "if [[ ${FAIL_RELOAD_ONCE:-0} == 1 && ! -e ${RELOAD_FAILURE_MARKER} ]]; then\n"
    "  : >\"$RELOAD_FAILURE_MARKER\"\n"
    "  exit 42\n"
    "fi\n"
)
nginx_bin.chmod(0o755)
systemctl_bin.chmod(0o755)
os.environ["HELPER_COMMAND_LOG"] = str(command_log)
os.environ["RELOAD_FAILURE_MARKER"] = str(workspace / "reload-failed-once")

target = workspace / "preview.secpal.dev"
target.write_text("old valid config\n")
target.chmod(0o644)

helper.apply_manifest(
    manifest_path=manifest_path,
    target=target,
    nginx_bin=nginx_bin,
    systemctl_bin=systemctl_bin,
    expected_uid=os.getuid(),
)
assert target.read_text() == rendered
log_lines = command_log.read_text().splitlines()
assert log_lines == ["nginx:-t", "systemctl:reload nginx"], log_lines
assert not list(workspace.glob("*.bak-*"))
assert not list(workspace.glob(".*.tmp-*"))

target.write_text("rollback sentinel\n")
command_log.write_text("")
os.environ["FAIL_NGINX_TEST"] = "1"
try:
    helper.apply_manifest(
        manifest_path=manifest_path,
        target=target,
        nginx_bin=nginx_bin,
        systemctl_bin=systemctl_bin,
        expected_uid=os.getuid(),
    )
except subprocess.CalledProcessError:
    pass
else:
    raise AssertionError("nginx validation failure succeeded")
assert target.read_text() == "rollback sentinel\n"
assert "systemctl:" not in command_log.read_text()
os.environ.pop("FAIL_NGINX_TEST")

target.write_text("reload rollback sentinel\n")
command_log.write_text("")
os.environ["FAIL_RELOAD_ONCE"] = "1"
try:
    helper.apply_manifest(
        manifest_path=manifest_path,
        target=target,
        nginx_bin=nginx_bin,
        systemctl_bin=systemctl_bin,
        expected_uid=os.getuid(),
    )
except subprocess.CalledProcessError:
    pass
else:
    raise AssertionError("reload failure succeeded")
assert target.read_text() == "reload rollback sentinel\n"
assert command_log.read_text().splitlines() == [
    "nginx:-t",
    "systemctl:reload nginx",
    "nginx:-t",
    "systemctl:reload nginx",
]
os.environ.pop("FAIL_RELOAD_ONCE")

symlink_target = workspace / "symlink-target"
symlink_target.write_text("do not replace\n")
symlink_path = workspace / "symlink-nginx-target"
symlink_path.symlink_to(symlink_target.name)
try:
    helper.apply_manifest(
        manifest_path=manifest_path,
        target=symlink_path,
        nginx_bin=nginx_bin,
        systemctl_bin=systemctl_bin,
        expected_uid=os.getuid(),
    )
except RuntimeError as error:
    assert "symbolic-link nginx target" in str(error), error
else:
    raise AssertionError("symbolic-link nginx target accepted")
assert symlink_target.read_text() == "do not replace\n"

fifo_target = workspace / "fifo-nginx-target"
os.mkfifo(fifo_target)
try:
    helper.apply_manifest(
        manifest_path=manifest_path,
        target=fifo_target,
        nginx_bin=nginx_bin,
        systemctl_bin=systemctl_bin,
        expected_uid=os.getuid(),
    )
except RuntimeError as error:
    assert "non-regular nginx target" in str(error), error
else:
    raise AssertionError("non-regular nginx target accepted")

before_check = target.read_bytes()
helper.check_helper_components(
    nginx_bin=nginx_bin,
    systemctl_bin=systemctl_bin,
    helper_paths=(),
    require_root_ownership=False,
)
helper.check_environment(
    manifest_path=manifest_path,
    nginx_bin=nginx_bin,
    systemctl_bin=systemctl_bin,
    expected_uid=os.getuid(),
    helper_paths=(),
    require_root_ownership=False,
)
assert target.read_bytes() == before_check

bad_cli = subprocess.run([sys.executable, str(helper_path), "--unexpected"], capture_output=True, text=True)
assert bad_cli.returncode != 0
assert "unrecognized arguments" in bad_cli.stderr

print("Polyscope nginx helper security tests passed.")
PY
