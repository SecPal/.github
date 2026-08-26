#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Start the preview container with narrowly writable API runtime storage."""

from __future__ import annotations

import argparse
import importlib.util
import os
import pathlib
import re


SAFE_NAME = re.compile(r"^[A-Za-z0-9._:@/+-]+$")


def load_renderer(renderer_path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("polyscope_preview_renderer", renderer_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load preview renderer: {renderer_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_command(
    *,
    renderer_path: pathlib.Path,
    db_path: pathlib.Path,
    clone_root: pathlib.Path,
    repository_root: pathlib.Path,
    caddyfile: pathlib.Path,
    image: str,
    network: str,
    preview_port: int,
) -> list[str]:
    renderer = load_renderer(renderer_path)
    identifiers = renderer.repository_ids(db_path, repository_root)
    api_repository_id = identifiers.get("SecPal/api")
    command = [
        "/usr/bin/podman",
        "run",
        "--replace",
        "--rm",
        "--name",
        "polyscope-preview",
        "--network",
        network,
        "-e",
        "DB_HOST=polyscope-postgresql-proxy",
        "-e",
        "DB_PORT=5432",
        "-p",
        f"127.0.0.1:{preview_port}:18080",
        "-v",
        f"{caddyfile}:/etc/frankenphp/Caddyfile:ro",
        "-v",
        f"{clone_root}:/workspaces:ro",
        "-v",
        f"{clone_root}:{clone_root}:ro",
    ]
    if api_repository_id is not None:
        repository_clone_root = renderer._resolved(clone_root / api_repository_id)
        for _logical_workspace, physical_workspace in renderer.active_workspaces(
            db_path, api_repository_id, clone_root, "public"
        ):
            physical_worktree = renderer._resolved(
                clone_root / api_repository_id / physical_workspace
            )
            storage_path = physical_worktree / "storage"
            if storage_path.is_symlink() or not storage_path.is_dir():
                raise RuntimeError(
                    f"writable API runtime directory is unavailable: {storage_path}"
                )
            storage = renderer._resolved(storage_path)
            if not storage.is_dir() or storage.parent != physical_worktree:
                raise RuntimeError(
                    f"writable API runtime directory is unavailable: {storage_path}"
                )
            if physical_worktree.parent != repository_clone_root:
                raise RuntimeError(f"active API worktree escapes its clone root: {physical_worktree}")
            target = pathlib.PurePosixPath(
                "/workspaces", api_repository_id, physical_workspace, "storage"
            )
            command.extend(["-v", f"{storage}:{target}:rw"])
    command.extend(
        [
            "--entrypoint",
            "/usr/local/bin/frankenphp",
            image,
            "run",
            "--config",
            "/etc/frankenphp/Caddyfile",
            "--adapter",
            "caddyfile",
        ]
    )
    return command


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--renderer", required=True, type=pathlib.Path)
    parser.add_argument("--db-path", required=True, type=pathlib.Path)
    parser.add_argument("--clone-root", required=True, type=pathlib.Path)
    parser.add_argument("--repository-root", required=True, type=pathlib.Path)
    parser.add_argument("--caddyfile", required=True, type=pathlib.Path)
    parser.add_argument("--image", required=True)
    parser.add_argument("--network", required=True)
    parser.add_argument("--preview-port", required=True, type=int)
    args = parser.parse_args()
    for path in (
        args.renderer,
        args.db_path,
        args.clone_root,
        args.repository_root,
        args.caddyfile,
    ):
        if not path.is_absolute():
            parser.error(f"path must be absolute: {path}")
    if SAFE_NAME.fullmatch(args.image) is None or SAFE_NAME.fullmatch(args.network) is None:
        parser.error("image or network contains unsupported characters")
    if not 1 <= args.preview_port <= 65535:
        parser.error("preview port must be between 1 and 65535")
    command = build_command(
        renderer_path=args.renderer,
        db_path=args.db_path,
        clone_root=args.clone_root,
        repository_root=args.repository_root,
        caddyfile=args.caddyfile,
        image=args.image,
        network=args.network,
        preview_port=args.preview_port,
    )
    os.execv(command[0], command)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
