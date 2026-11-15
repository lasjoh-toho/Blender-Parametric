# SPDX-License-Identifier: GPL-3.0-or-later
"""Scene units."""


def mm_per_unit(scene):
    """How many millimetres one Blender unit is in this scene."""
    units = scene.unit_settings
    if units.system == "NONE":
        return 1.0  # unitless scenes are treated as millimetres
    return units.scale_length * 1000.0
