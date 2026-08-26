#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Proxy PostgreSQL's trusted host socket into a private preview transport."""

from __future__ import annotations

import argparse
import os
import pathlib
import selectors
import signal
import socket
import stat


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    listen_group = parser.add_mutually_exclusive_group(required=True)
    listen_group.add_argument("--listen", type=pathlib.Path)
    listen_group.add_argument("--listen-host")
    parser.add_argument("--listen-port", type=int)
    parser.add_argument("--upstream", required=True, type=pathlib.Path)
    args = parser.parse_args()
    if (args.listen_host is None) != (args.listen_port is None):
        parser.error("--listen-host and --listen-port must be supplied together")
    return args


def remove_stale_socket(path: pathlib.Path) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISSOCK(metadata.st_mode):
        raise RuntimeError(f"refusing to replace non-socket path: {path}")
    path.unlink()


def relay(client: socket.socket, upstream_path: pathlib.Path) -> None:
    with client, socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as upstream:
        upstream.connect(str(upstream_path))
        selector = selectors.DefaultSelector()
        selector.register(client, selectors.EVENT_READ, upstream)
        selector.register(upstream, selectors.EVENT_READ, client)
        open_readers = 2
        try:
            while open_readers:
                for key, _events in selector.select():
                    source = key.fileobj
                    destination = key.data
                    chunk = source.recv(65536)
                    if chunk:
                        destination.sendall(chunk)
                        continue
                    selector.unregister(source)
                    open_readers -= 1
                    try:
                        destination.shutdown(socket.SHUT_WR)
                    except OSError:
                        # The peer may already have closed its write side.
                        pass
        finally:
            selector.close()


def accept_connections(listener: socket.socket, upstream_path: pathlib.Path) -> None:
    signal.signal(signal.SIGCHLD, signal.SIG_IGN)
    listener.listen(64)
    while True:
        client, _address = listener.accept()
        pid = os.fork()
        if pid == 0:
            listener.close()
            try:
                relay(client, upstream_path)
            finally:
                os._exit(0)
        client.close()


def serve_unix(listen_path: pathlib.Path, upstream_path: pathlib.Path) -> None:
    if not upstream_path.is_socket():
        raise RuntimeError(f"PostgreSQL upstream socket is unavailable: {upstream_path}")
    listen_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(listen_path.parent, 0o700)
    remove_stale_socket(listen_path)

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(str(listen_path))
        os.chmod(listen_path, 0o600)
        accept_connections(listener, upstream_path)


def serve_tcp(listen_host: str, listen_port: int, upstream_path: pathlib.Path) -> None:
    if not 1 <= listen_port <= 65535:
        raise RuntimeError(f"invalid listen port: {listen_port}")
    if not upstream_path.is_socket():
        raise RuntimeError(f"PostgreSQL upstream socket is unavailable: {upstream_path}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((listen_host, listen_port))
        accept_connections(listener, upstream_path)


def main() -> int:
    args = parse_args()
    if args.listen is not None:
        serve_unix(args.listen, args.upstream)
    else:
        serve_tcp(args.listen_host, args.listen_port, args.upstream)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
