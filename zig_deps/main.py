#!/usr/bin/env python3

"""Tool to check if a zig project's dependencies are up to date.

Can also update them, and check for sub-projects recursively.
"""

# TODO?: async library to invoke comands - may lead to data races or something

from __future__ import annotations

import argparse
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from ._version import version

HASH_DISPLAY_LEN = 7
ZON = "build.zig.zon"
NAME = Path(__file__).parent.name

Dependencies = defaultdict[Path, list[str]]


def directory(raw: str) -> Path:
    """Parse a directory argument."""
    path = Path(raw)
    if path.is_dir():
        return path

    msg = f"'{raw}' is not a directory."
    raise argparse.ArgumentTypeError(msg)


def _find_dependencies(
    file: Path,
    dependencies: Dependencies,
) -> None:
    folder = file.parent
    with file.open() as f:
        for raw in f.readlines():
            line = raw.strip()

            if line.startswith("//"):
                continue

            # FIXME: very stupid logic, may not handle stuff like
            # .dependency = .{ .url ... }
            # .url = "foo\"bar"
            # but should be good enough for most cases
            if line.startswith(".url"):
                dependencies[folder].append(line.split('"')[1])


def _collect_dependencies(
    directory: Path,
    dependencies: Dependencies,
    *,
    recursive: bool,
) -> None:
    for child in directory.iterdir():
        if child.is_dir() and recursive:
            _collect_dependencies(child, dependencies, recursive=recursive)
        elif child.is_file() and child.name == ZON:
            _find_dependencies(child, dependencies)


def get_dependencies(
    root: Path,
    *,
    recursive: bool,
) -> Dependencies:
    """Given a folder, get all of the dependency URLs in it."""
    dependencies: Dependencies = defaultdict(list)
    _collect_dependencies(root, dependencies, recursive=recursive)
    return dependencies


def get_hash(url: str) -> str:
    """Given a package's URL, get its hash."""
    return subprocess.run(  # noqa: S603  # it is not attacker-controlled input
        [  # noqa: S607  # do not force user to have zig on a specific path
            "zig",
            "fetch",
            url,
        ],
        capture_output=True,
        check=True,
    ).stdout.decode()


def get_base(url: str) -> str:
    """Get base URL from a complete one."""
    base, *parts = url.split("#")
    if len(parts) == 0:
        msg = "Unsupported URL format"
        raise RuntimeError(msg)

    return base


def update_package(folder: Path, url: str) -> None:
    """Given a package's URL, and the folder where it is listed, update it."""
    base = get_base(url)

    subprocess.run(  # noqa: S603  # it is not attacker-controlled input
        [  # noqa: S607  # do not force user to have zig on a specific path
            "zig",
            "fetch",
            "--save",
            base,
        ],
        cwd=folder,
        capture_output=True,
        check=True,
    )


def main() -> int:
    """Entrypoint of the tool."""
    parser = argparse.ArgumentParser(
        prog=NAME,
        description=__doc__,
    )

    parser.add_argument(
        "root",
        help="root of the project (build.zig's location). defaults to current dir",
        type=directory,
        nargs=argparse.OPTIONAL,
        default=Path.cwd(),
    )

    parser.add_argument(
        "-r",
        "--recursive",
        help="scan subdirectories for other .zon files",
        action="store_true",
    )

    parser.add_argument(
        "-u",
        "--update",
        help="update dependencies to their latest version",
        action="store_true",
    )

    parser.add_argument(
        "-V",
        "--version",
        help="show tool's version and exit",
        action="version",
        version=version,
    )

    args = parser.parse_args()

    dependencies = get_dependencies(args.root, recursive=args.recursive)
    if not dependencies:
        sys.stdout.write(
            f"no {ZON} file found (or no URLs in it)."
            " did you run the command from the wrong directory?",
        )
        return 0

    for folder, urls in dependencies.items():
        for url in urls:
            base = get_base(url)
            current, latest = get_hash(url), get_hash(base)

            if current == latest:
                sys.stdout.write(f"[{base}] already up to date\n")
            elif args.update:
                update_package(folder, url)
                sys.stdout.write(
                    f"[{base}] updated {current[:HASH_DISPLAY_LEN]}"
                    f" -> {latest[:HASH_DISPLAY_LEN]}\n",
                )
            else:
                sys.stdout.write(f"[{base}] out of date\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
