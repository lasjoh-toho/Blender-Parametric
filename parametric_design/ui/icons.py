# SPDX-License-Identifier: GPL-3.0-or-later
"""Two-colour tool icons (PNG files in ../icons), loaded as previews."""

import os

import bpy
import bpy.utils.previews

_collection = [None]
ICON_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "icons")


def get(name):
    """Return the icon id for ``name`` (0 if it does not exist)."""
    pcoll = _collection[0]
    if pcoll is None:
        return 0
    item = pcoll.get(name)
    return item.icon_id if item is not None else 0


def register():
    pcoll = bpy.utils.previews.new()
    if os.path.isdir(ICON_DIR):
        for filename in sorted(os.listdir(ICON_DIR)):
            if filename.endswith(".png"):
                pcoll.load(filename[:-4], os.path.join(ICON_DIR, filename), "IMAGE")
    _collection[0] = pcoll


def unregister():
    if _collection[0] is not None:
        bpy.utils.previews.remove(_collection[0])
        _collection[0] = None
