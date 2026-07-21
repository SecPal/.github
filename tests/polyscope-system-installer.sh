#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
INSTALLER="$REPO_ROOT/scripts/install-polyscope-system-components.sh"
YAML_CHECK="$REPO_ROOT/scripts/verify-js-yaml-package.cjs"
WORKSPACE="$(mktemp -d "${TMPDIR:-/tmp}/polyscope-system-installer.XXXXXX")"
trap 'rm -rf "$WORKSPACE"' EXIT

node "$YAML_CHECK" "$REPO_ROOT/node_modules/js-yaml"

missing_yaml_entry="$WORKSPACE/missing-yaml-entry/js-yaml"
mkdir -p "$(dirname -- "$missing_yaml_entry")"
cp -R "$REPO_ROOT/node_modules/js-yaml" "$missing_yaml_entry"
missing_yaml_module="$(node -e \
    'process.stdout.write(require.resolve(process.argv[1]))' \
    "$missing_yaml_entry")"
rm "$missing_yaml_module"
if node "$YAML_CHECK" "$missing_yaml_entry"; then
    echo "js-yaml verification must reject a missing declared entry point" >&2
    exit 1
fi

invalid_yaml_api="$WORKSPACE/invalid-yaml-api/js-yaml"
mkdir -p "$invalid_yaml_api"
cat >"$invalid_yaml_api/package.json" <<'JSON'
{
  "name": "js-yaml",
  "main": "index.cjs"
}
JSON
cat >"$invalid_yaml_api/index.cjs" <<'JS'
module.exports = {};
JS
if node "$YAML_CHECK" "$invalid_yaml_api"; then
    echo "js-yaml verification must reject a package without yaml.load" >&2
    exit 1
fi

if [[ "$(id -u)" -ne 0 ]]; then
    if "$INSTALLER" >"$WORKSPACE/non-root.out" 2>"$WORKSPACE/non-root.err"; then
        echo "system installer must require an interactive root invocation" >&2
        exit 1
    fi
    grep -q 'must be run as root' "$WORKSPACE/non-root.err"
fi

real_id_bin="$(command -v id)"
fake_id_dir="$WORKSPACE/fake-id"
mkdir -p "$fake_id_dir"
cat >"$fake_id_dir/id" <<'STUB'
#!/usr/bin/env bash
if [[ "${1:-}" == "-u" && "${2:-}" == "secpal" ]]; then
    echo "stage-only must not inspect the target service account" >&2
    exit 67
fi
exec "$REAL_ID_BIN" "$@"
STUB
chmod +x "$fake_id_dir/id"

REAL_ID_BIN="$real_id_bin" PATH="$fake_id_dir:$PATH" \
    DESTDIR="$WORKSPACE/stage" "$INSTALLER" --stage-only

custom_node_dir="$WORKSPACE/user-node/bin"
custom_node="$custom_node_dir/node"
mkdir -p "$custom_node_dir"
cat >"$custom_node" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB
chmod +x "$custom_node"
REAL_ID_BIN="$real_id_bin" PATH="$fake_id_dir:$PATH" \
    DESTDIR="$WORKSPACE/node-stage" "$INSTALLER" --stage-only --node-bin "$custom_node"
grep -q "^Environment=PATH=$custom_node_dir:" \
    "$WORKSPACE/node-stage/etc/systemd/system/polyscope-server.service.d/zz-secpal-runtime.conf"
if REAL_ID_BIN="$real_id_bin" PATH="$fake_id_dir:$PATH" \
    DESTDIR="$WORKSPACE/unsafe-node-stage" "$INSTALLER" --stage-only --node-bin relative/node \
    >"$WORKSPACE/unsafe-node.out" 2>"$WORKSPACE/unsafe-node.err"; then
    echo "system installer must reject a relative Node.js path" >&2
    exit 1
fi
grep -q 'absolute executable path' "$WORKSPACE/unsafe-node.err"
test ! -e "$WORKSPACE/unsafe-node-stage/etc/systemd/system/polyscope-server.service.d/zz-secpal-runtime.conf"

helper="$WORKSPACE/stage/usr/local/libexec/secpal-polyscope-nginx-apply"
library="$WORKSPACE/stage/usr/local/libexec/polyscope_nginx.py"
rollout="$WORKSPACE/stage/usr/local/libexec/polyscope-rollout.py"
sudoers="$WORKSPACE/stage/etc/sudoers.d/secpal-polyscope-nginx"
dropin="$WORKSPACE/stage/etc/systemd/system/polyscope-server.service.d/zz-secpal-runtime.conf"

test -x "$helper"
test -f "$library"
test -f "$rollout"
test -f "$sudoers"
test -f "$dropin"
test "$(head -n 1 "$helper")" = '#!/usr/bin/python3'
test "$(stat -c '%a' "$helper")" = 755
test "$(stat -c '%a' "$library")" = 644
test "$(stat -c '%a' "$rollout")" = 644
test "$(stat -c '%a' "$sudoers")" = 440
test "$(stat -c '%a' "$dropin")" = 644

grep -qxF 'secpal ALL=(root) NOPASSWD: /usr/local/libexec/secpal-polyscope-nginx-apply ""' "$sudoers"
grep -qxF 'secpal ALL=(root) NOPASSWD: /usr/local/libexec/secpal-polyscope-nginx-apply --check' "$sudoers"
if cut -d: -f2- "$sudoers" | grep -Eq 'ALL[[:space:]]*$|\*|/(usr/)?bin/(ba)?sh([[:space:]]|$)|/(usr/)?bin/(python[^/[:space:]]*|systemctl|install|cp|mv|rm|tee)([[:space:]]|$)'; then
    echo "sudoers fixture grants a broad command" >&2
    exit 1
fi

grep -q '^User=secpal$' "$dropin"
grep -q '^Environment=SSH_AUTH_SOCK=/run/user/1000/openssh_agent$' "$dropin"
grep -q 'ExecStart=/home/secpal/.local/bin/polyscope-server serve --host 127.0.0.1 --port 4321' "$dropin"
grep -q 'exec /home/secpal/code/SecPal/.github/scripts/polyscope-rollout.py ' "$dropin"
if grep -qF 'exec /home/secpal/.local/bin/polyscope-secpal-rollout.py ' "$dropin"; then
    echo "system installer must not depend on a target created by the later user installer" >&2
    exit 1
fi
grep -q -- '--nginx-manifest-output /home/secpal/.local/state/polyscope/nginx-manifest.json --install-nginx' "$dropin"

if command -v visudo >/dev/null 2>&1; then
    visudo -c -f "$sudoers" >/dev/null
fi

echo "Polyscope system-component installer tests passed."
