"""A handful of low-poly trees (README section 15, minimal).

Each tree is a cone (foliage) on a cylinder (trunk). The meshes are created
ONCE and every tree after the first re-uses the same mesh datablock, so N
trees cost N objects but only 2 meshes - the cheap form of instancing, and a
stepping stone to the Geometry Nodes scatter of Milestone 2.

Trees are placed on a deterministic ring around the house so the layout is
reproducible from ``house.seed``.
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

import bmesh
import bpy
from mathutils import Vector

from ..materials import palette
from ..geometry import common

TRUNK_R = 0.13
TRUNK_H = 1.4
CROWN_R = 0.95
CROWN_H = 2.6


def _shared_mesh(name: str, builder) -> "bpy.types.Mesh":
    existing = bpy.data.meshes.get(name)
    if existing is not None:
        return existing
    bm = builder()
    mesh = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    return mesh


def _trunk_mesh() -> "bpy.types.Mesh":
    def build():
        bm = bmesh.new()
        bmesh.ops.create_cone(
            bm,
            cap_ends=True,
            cap_tris=False,
            segments=6,
            radius1=TRUNK_R,
            radius2=TRUNK_R * 0.8,
            depth=TRUNK_H,
        )
        bmesh.ops.translate(bm, vec=Vector((0, 0, TRUNK_H / 2.0)), verts=bm.verts)
        return bm

    return _shared_mesh("AIG_tree_trunk_mesh", build)


def _crown_mesh() -> "bpy.types.Mesh":
    def build():
        bm = bmesh.new()
        bmesh.ops.create_cone(
            bm,
            cap_ends=True,
            cap_tris=False,
            segments=7,
            radius1=CROWN_R,
            radius2=0.0,
            depth=CROWN_H,
        )
        bmesh.ops.translate(bm, vec=Vector((0, 0, CROWN_H / 2.0)), verts=bm.verts)
        return bm

    return _shared_mesh("AIG_tree_crown_mesh", build)


def _positions(house) -> List[Tuple[float, float, float]]:
    """Deterministic ring of tree positions outside the building pad."""
    x0, y0, x1, y1 = house.footprint()
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    base = max(x1 - x0, y1 - y0) / 2.0
    margin = float(house.terrain_margin)
    count = max(0, int(house.tree_count))

    out = []
    for i in range(count):
        # golden-angle spread keeps the trees from lining up
        a = (i * 2.399963 + house.seed * 0.7) % (2 * math.pi)
        wobble = ((i * 37 + house.seed * 13) % 100) / 100.0
        radius = base + 1.8 + wobble * max(1.0, margin - 2.5)
        scale = 0.75 + wobble * 0.6
        out.append((cx + math.cos(a) * radius, cy + math.sin(a) * radius, scale))
    return out


def build_vegetation(
    house,
    coll: Optional["bpy.types.Collection"] = None,
) -> List["bpy.types.Object"]:
    coll = coll or common.get_subcollection("Environment")
    trunk_mesh = _trunk_mesh()
    crown_mesh = _crown_mesh()
    wood = palette.get_or_create("WOOD")
    leaves = palette.get_or_create("FOLIAGE")
    if not trunk_mesh.materials:
        trunk_mesh.materials.append(wood)
    if not crown_mesh.materials:
        crown_mesh.materials.append(leaves)

    objects: List["bpy.types.Object"] = []
    for index, (x, y, scale) in enumerate(_positions(house)):
        trunk = bpy.data.objects.new(f"AIG_tree_{index}_trunk", trunk_mesh)
        trunk.location = (x, y, 0.0)
        trunk.scale = (scale, scale, scale)
        coll.objects.link(trunk)

        crown = bpy.data.objects.new(f"AIG_tree_{index}_crown", crown_mesh)
        crown.location = (x, y, TRUNK_H * scale * 0.8)
        crown.scale = (scale, scale, scale)
        coll.objects.link(crown)

        for obj in (trunk, crown):
            obj["aig_type"] = "tree"
            obj["aig_tree_index"] = index
            objects.append(obj)

    return objects
