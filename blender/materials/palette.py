"""The visual language: STONE, WOOD, PLASTER, ROOF, GLASS, GROUND, GRASS.

``get_or_create`` semantics: calling it twice with the same key returns the
same ``bpy.types.Material``, which is what makes house regeneration idempotent
(we never leak a "Material.001" trail).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import bpy

#: Prefix so our materials never collide with the user's own.
PREFIX = "AIG_"


@dataclass(frozen=True)
class MaterialSpec:
    key: str
    color: Tuple[float, float, float, float]
    roughness: float = 0.8
    metallic: float = 0.0
    #: 0 = opaque, 1 = fully transmissive (glass)
    transmission: float = 0.0
    alpha: float = 1.0


PALETTE: Dict[str, MaterialSpec] = {
    "STONE": MaterialSpec("STONE", (0.62, 0.60, 0.55, 1.0), roughness=0.90),
    "WOOD": MaterialSpec("WOOD", (0.36, 0.22, 0.12, 1.0), roughness=0.75),
    "PLASTER": MaterialSpec("PLASTER", (0.90, 0.87, 0.80, 1.0), roughness=0.95),
    "ROOF": MaterialSpec("ROOF", (0.42, 0.17, 0.14, 1.0), roughness=0.70),
    "GLASS": MaterialSpec(
        "GLASS", (0.55, 0.72, 0.80, 1.0), roughness=0.08, transmission=0.85, alpha=0.35
    ),
    "GROUND": MaterialSpec("GROUND", (0.38, 0.30, 0.20, 1.0), roughness=1.0),
    "GRASS": MaterialSpec("GRASS", (0.25, 0.45, 0.18, 1.0), roughness=1.0),
    # supporting colours used by frames / foliage / trunks
    "FRAME": MaterialSpec("FRAME", (0.28, 0.17, 0.10, 1.0), roughness=0.65),
    "FOLIAGE": MaterialSpec("FOLIAGE", (0.16, 0.36, 0.15, 1.0), roughness=1.0),
}


def get_palette() -> Dict[str, MaterialSpec]:
    return dict(PALETTE)


def _set_input(node: "bpy.types.Node", name: str, value) -> bool:
    """Set a Principled BSDF socket if this Blender version exposes it.

    Socket names moved around between 3.x / 4.x / 5.x (``Transmission`` became
    ``Transmission Weight``), so we probe instead of assuming.
    """
    socket = node.inputs.get(name)
    if socket is None:
        return False
    socket.default_value = value
    return True


def get_or_create(key: str) -> "bpy.types.Material":
    """Return the material for ``key``, creating it on first use.

    Unknown keys fall back to PLASTER rather than raising, so a hand-written
    JSON with a typo still renders something.
    """
    spec = PALETTE.get(key.upper(), PALETTE["PLASTER"])
    name = f"{PREFIX}{spec.key}"

    existing = bpy.data.materials.get(name)
    if existing is not None:
        return existing

    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    mat.diffuse_color = spec.color  # viewport / Workbench colour

    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        _set_input(bsdf, "Base Color", spec.color)
        _set_input(bsdf, "Roughness", spec.roughness)
        _set_input(bsdf, "Metallic", spec.metallic)
        if spec.transmission > 0.0:
            # 4.x/5.x name first, then the legacy one.
            if not _set_input(bsdf, "Transmission Weight", spec.transmission):
                _set_input(bsdf, "Transmission", spec.transmission)
            _set_input(bsdf, "Alpha", spec.alpha)
            mat.blend_method = "BLEND" if hasattr(mat, "blend_method") else mat.blend_method

    return mat


def assign(obj: "bpy.types.Object", key: str) -> "bpy.types.Material":
    """Replace ``obj``'s material slots with the single palette material."""
    mat = get_or_create(key)
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    return mat


def reset_cache() -> None:
    """Delete every material this module created (used by tests / Clear)."""
    for mat in list(bpy.data.materials):
        if mat.name.startswith(PREFIX):
            bpy.data.materials.remove(mat)
