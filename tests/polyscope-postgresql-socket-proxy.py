#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import importlib.util
import pathlib
import socket
import subprocess
import sys
import tempfile
import threading
import time


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PROXY_SCRIPT = REPO_ROOT / "scripts" / "polyscope-postgresql-socket-proxy.py"


def wait_for_socket(path: pathlib.Path) -> None:
    for _attempt in range(100):
        if path.is_socket():
            return
        time.sleep(0.01)
    raise AssertionError(f"proxy socket was not created: {path}")


def reserve_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
        reservation.bind(("127.0.0.1", 0))
        return int(reservation.getsockname()[1])


def wait_for_tcp(port: int) -> socket.socket:
    for _attempt in range(100):
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            client.connect(("127.0.0.1", port))
            return client
        except ConnectionRefusedError:
            client.close()
            time.sleep(0.01)
    raise AssertionError(f"TCP proxy did not listen on port {port}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="polyscope-postgresql-proxy.") as temporary:
        root = pathlib.Path(temporary)
        upstream_path = root / "upstream.sock"
        listen_path = root / "proxy" / ".s.PGSQL.5432"

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as upstream:
            upstream.bind(str(upstream_path))
            upstream.listen(1)

            def echo_once() -> None:
                connection, _address = upstream.accept()
                with connection:
                    payload = connection.recv(4096)
                    connection.sendall(payload[::-1])

            echo_thread = threading.Thread(target=echo_once)
            echo_thread.start()
            proxy = subprocess.Popen(
                [
                    sys.executable,
                    str(PROXY_SCRIPT),
                    "--listen",
                    str(listen_path),
                    "--upstream",
                    str(upstream_path),
                ]
            )
            try:
                wait_for_socket(listen_path)
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                    client.connect(str(listen_path))
                    client.sendall(b"postgres-wire-test")
                    client.shutdown(socket.SHUT_WR)
                    assert client.recv(4096) == b"postgres-wire-test"[::-1]
                echo_thread.join(timeout=2)
                assert not echo_thread.is_alive()
                assert (listen_path.parent.stat().st_mode & 0o777) == 0o700
                assert (listen_path.stat().st_mode & 0o777) == 0o600
            finally:
                proxy.terminate()
                proxy.wait(timeout=2)

        unsafe_path = root / "not-a-socket"
        unsafe_path.write_text("preserve me")
        spec = importlib.util.spec_from_file_location("proxy_module", PROXY_SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        try:
            module.remove_stale_socket(unsafe_path)
        except RuntimeError as error:
            assert "refusing to replace non-socket path" in str(error)
        else:
            raise AssertionError("non-socket path was accepted")
        assert unsafe_path.read_text() == "preserve me"

        tcp_upstream_path = root / "tcp-upstream.sock"
        tcp_port = reserve_tcp_port()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as upstream:
            upstream.bind(str(tcp_upstream_path))
            upstream.listen(1)

            def echo_tcp_once() -> None:
                connection, _address = upstream.accept()
                with connection:
                    payload = connection.recv(4096)
                    connection.sendall(payload.upper())

            echo_thread = threading.Thread(target=echo_tcp_once)
            echo_thread.start()
            proxy = subprocess.Popen(
                [
                    sys.executable,
                    str(PROXY_SCRIPT),
                    "--listen-host",
                    "127.0.0.1",
                    "--listen-port",
                    str(tcp_port),
                    "--upstream",
                    str(tcp_upstream_path),
                ]
            )
            try:
                with wait_for_tcp(tcp_port) as client:
                    client.sendall(b"postgres-network-test")
                    client.shutdown(socket.SHUT_WR)
                    assert client.recv(4096) == b"POSTGRES-NETWORK-TEST"
                echo_thread.join(timeout=2)
                assert not echo_thread.is_alive()
            finally:
                proxy.terminate()
                proxy.wait(timeout=2)


if __name__ == "__main__":
    main()
