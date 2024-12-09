# This file is part of the faebryk project
# SPDX-License-Identifier: MIT

import logging

from faebryk.libs.util import (
    ConfigFlag,
    at_exit,
    global_lock,
    is_editable_install,
)

logger = logging.getLogger(__name__)


LEAK_WARNINGS = ConfigFlag("CPP_LEAK_WARNINGS", default=False)
DEBUG_BUILD = ConfigFlag("CPP_DEBUG_BUILD", default=False)
PRINTF_DEBUG = ConfigFlag("CPP_PRINTF_DEBUG", default=False)


def compile_and_load():
    """
    Forces C++ to compile into faebryk_core_cpp_editable module which is then loaded
    into _cpp.
    """
    import os
    import platform
    import shutil
    import sys
    from pathlib import Path

    from faebryk.libs.header import formatted_file_contents, get_header
    from faebryk.libs.util import run_live

    _thisfile = Path(__file__)
    _thisdir = _thisfile.parent
    _cmake_dir = _thisdir
    _build_dir = _cmake_dir / "build"
    pyi_source = _build_dir / "faebryk_core_cpp_editable.pyi"

    date_files = [pyi_source]
    dates = {k: os.path.getmtime(k) if k.exists() else 0 for k in date_files}

    # check for cmake binary existing
    if not shutil.which("cmake"):
        raise RuntimeError(
            "cmake not found, needed for compiling c++ code in editable mode"
        )

    # Force recompile
    # subprocess.run(["rm", "-rf", str(build_dir)], check=True)

    other_flags = []

    # On OSx we've had some issues with building for the right architecture
    if sys.platform == "darwin":  # macOS
        arch = platform.machine()
        if arch in ["arm64", "x86_64"]:
            other_flags += [f"-DCMAKE_OSX_ARCHITECTURES={arch}"]

    if DEBUG_BUILD:
        other_flags += ["-DCMAKE_BUILD_TYPE=Debug"]
    other_flags += [f"-DGLOBAL_PRINTF_DEBUG={int(bool(PRINTF_DEBUG))}"]

    with global_lock(_build_dir / "lock", timeout_s=60):
        run_live(
            [
                "cmake",
                "-S",
                str(_cmake_dir),
                "-B",
                str(_build_dir),
                "-DEDITABLE=1",
                "-DPython_EXECUTABLE=" + sys.executable,
                *other_flags,
            ],
            logger=logger,
        )
        run_live(
            [
                "cmake",
                "--build",
                str(_build_dir),
                "--",
                "-j",
            ],
            logger=logger,
        )

    if not _build_dir.exists():
        raise RuntimeError("build directory not found")

    # add build dir to sys path
    sys.path.append(str(_build_dir))

    modified = {k for k, v in dates.items() if os.path.getmtime(k) > v}

    # move autogenerated type stub file to source directory
    if pyi_source in modified:
        pyi_out = _thisfile.with_suffix(".pyi")
        pyi_out.write_text(
            formatted_file_contents(
                get_header()
                + "\n"
                + "# This file is auto-generated by nanobind.\n"
                + "# Do not edit this file directly; edit the corresponding\n"
                + "# C++ file instead.\n"
                # + "from typing import overload\n"
                + pyi_source.read_text(),
                is_pyi=True,
            )
        )
        run_live(
            [sys.executable, "-m", "ruff", "check", "--fix", pyi_out],
            logger=logger,
        )


# Re-export c++ with type hints provided by __init__.pyi
if is_editable_install():
    logger.warning("faebryk is installed as editable package, compiling c++ code")
    compile_and_load()
    from faebryk_core_cpp_editable import *  # type: ignore # noqa: E402, F403
else:
    from faebryk_core_cpp import *  # type: ignore # noqa: E402, F403


def cleanup():
    if LEAK_WARNINGS:
        print("\n--- Nanobind leakage analysis ".ljust(80, "-"))
        # nanobind automatically prints leaked objects at exit
    from faebryk.core.cpp import set_leak_warnings

    set_leak_warnings(bool(LEAK_WARNINGS))


at_exit(cleanup, on_exception=False)
