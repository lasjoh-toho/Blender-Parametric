# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the installable extension ZIP into dist/.

Equivalent to ``blender --command extension build`` but needs no Blender,
so it also runs in CI. Usage: python scripts/build_extension.py
"""

import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "parametric_design")
EXCLUDE_DIRS = {"__pycache__", ".git"}
EXCLUDE_EXT = {".pyc", ".blend1"}


def manifest_value(key):
    with open(os.path.join(PKG, "blender_manifest.toml"), encoding="utf-8") as f:
        for line in f:
            m = re.match(rf'^{key}\s*=\s*"([^"]*)"', line.strip())
            if m:
                return m.group(1)
    raise SystemExit(f"{key} missing in blender_manifest.toml")


def main():
    ext_id = manifest_value("id")
    version = manifest_value("version")
    out_dir = os.path.join(ROOT, "dist")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{ext_id}-{version}.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for base, dirs, files in os.walk(PKG):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
            for name in sorted(files):
                if os.path.splitext(name)[1] in EXCLUDE_EXT:
                    continue
                path = os.path.join(base, name)
                zf.write(path, os.path.relpath(path, PKG))
    print(out)
    return out


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
