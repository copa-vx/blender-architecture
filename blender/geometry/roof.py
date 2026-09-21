"""Roof generator - gable only (README section 12, V1).

Two slabs meeting at a ridge, plus a triangular gable wall at each end so the
loft is closed. The roof is anchored at the top of the walls: the ridge rises
``(span/2) * tan(pitch)`` above the wall plate and the overhang continues the
same slope outwards, hanging ``overhang * tan(pitch)`` below it.
"""

from __future__ import annotations

import math
from typing import List, Optional

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

from ..materials import palette
from . import common


def build_roof(
    house,
    coll: Optional["bpy.types.Collection"] = None,
) -> List["bpy.types.Object"]:
    coll = coll or common.get_subcollection("Roof")
    roof = house.roof
    x0, y0, x1, y1 = house.footprint()
    width = x1 - x0
    depth = y1 - y0
    axis = roof.resolved_ridge_axis(width, depth)

    eave_z = house.total_height          # top of the walls
    ridge_z = eave_z + roof.height_for(width, depth)
    run = roof.slope_run(width, depth)   # ridge -> overhang edge, horizontal
    drop = roof.eave_drop()              # how far below eave_z the edge sits
    thickness = float(roof.thickness)
    overhang = float(roof.overhang)

    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    # length of the ridge itself, extended by the overhang at the gable ends
    ridge_len = (width if axis == "x" else depth) + 2 * overhang

    objects: List["bpy.types.Object"] = []

    # -- the two sloped slabs ----------------------------------------------
    # Built from explicit world-space corners rather than a rotated box: the
    # Euler signs for "tilt away from the ridge" flip with the ridge axis and
    # are easy to get backwards (a V instead of a roof). Naming the four
    # corners makes the shape self-evident and matches what the tests assert.
    angle = math.radians(float(roof.pitch))
    # NOTE: distinct from `eave_z` (the wall top). This is the outer edge of
    # the overhang, which hangs `overhang * tan(pitch)` BELOW the wall top.
    # Reusing the name here silently dropped the gable triangles by that much.
    overhang_z = ridge_z - run * math.tan(angle)
    half_ridge = ridge_len / 2.0

    for side in (-1, 1):
        if axis == "x":
            # ridge runs along X; the slab falls away along Y
            top = [
                Vector((cx - half_ridge, cy, ridge_z)),
                Vector((cx + half_ridge, cy, ridge_z)),
                Vector((cx + half_ridge, cy + side * run, overhang_z)),
                Vector((cx - half_ridge, cy + side * run, overhang_z)),
            ]
        else:
            # ridge runs along Y; the slab falls away along X
            top = [
                Vector((cx, cy - half_ridge, ridge_z)),
                Vector((cx, cy + half_ridge, ridge_z)),
                Vector((cx + side * run, cy + half_ridge, overhang_z)),
                Vector((cx + side * run, cy - half_ridge, overhang_z)),
            ]

        bm = bmesh.new()
        verts = [bm.verts.new(p) for p in top]
        face = bm.faces.new(verts)
        bm.normal_update()
        # Thicken downwards along the face normal so the slab has a soffit.
        normal = face.normal.copy()
        if normal.z < 0:
            bmesh.ops.reverse_faces(bm, faces=[face])
            bm.normal_update()
            normal = face.normal.copy()
        # Extrude UPWARD: the rafter plane becomes the slab's underside and the
        # tiles sit on top of it, like real construction. Extruding downward
        # instead would make the slab's TOP face coplanar with the gable
        # triangle's sloped edge, which z-fights into a white line at the eave.
        result = bmesh.ops.extrude_face_region(bm, geom=[face])
        moved = [v for v in result["geom"] if isinstance(v, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, vec=normal * thickness, verts=moved)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

        obj = common.new_mesh_object(
            f"AIG_roof_slab_{'a' if side < 0 else 'b'}", bm, coll
        )
        palette.assign(obj, roof.material)
        common.shade_flat(obj)
        obj["aig_type"] = "roof_slab"
        obj["aig_slab_side"] = side
        objects.append(obj)

    # -- gable end walls ----------------------------------------------------
    # Triangle profile in the plane perpendicular to the ridge, from the wall
    # top up to the ridge. Built as a prism so it has thickness.
    half_span = (depth if axis == "x" else width) / 2.0
    profile = [
        (-half_span, eave_z),
        (half_span, eave_z),
        (0.0, ridge_z),
    ]
    gable_t = float(house.floors[0].wall_thickness)
    for side in (-1, 1):
        bm = common.prism_bmesh(profile, gable_t)
        obj = common.new_mesh_object(
            f"AIG_roof_gable_{'a' if side < 0 else 'b'}", bm, coll
        )
        # prism_bmesh builds in (x=thickness, y=span, z=height) - place it at
        # the correct end of the ridge and rotate if the ridge runs along Y.
        if axis == "x":
            loc = Vector((cx + side * (width / 2.0) - side * gable_t / 2.0, cy, 0.0))
            obj.matrix_world = Matrix.Translation(loc)
        else:
            loc = Vector((cx, cy + side * (depth / 2.0) - side * gable_t / 2.0, 0.0))
            obj.matrix_world = Matrix.Translation(loc) @ Euler(
                (0.0, 0.0, math.radians(90.0)), "XYZ"
            ).to_matrix().to_4x4()
        palette.assign(obj, "PLASTER")
        common.shade_flat(obj)
        obj["aig_type"] = "roof_gable"
        objects.append(obj)

    for obj in objects:
        obj["aig_ridge_z"] = ridge_z
        obj["aig_eave_z"] = eave_z
    return objects
