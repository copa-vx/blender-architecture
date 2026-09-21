"""Low level mesh helpers shared by every generator.

Everything is built with ``bmesh`` rather than ``bpy.ops`` because operators
depend on the current context/selection, which is fragile in background mode.
"""

from __future__ import annotations

import math
from typing import Iterable, List, Optional, Sequence, Tuple

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

#: Everything we generate lives under this collection, so "clear the house"
#: is one unlink and the user's own objects are never touched.
HOUSE_COLLECTION = "AIG_House"
#: Sub-collections, in creation order.
SUBCOLLECTIONS = ("Walls", "Floors", "Roof", "Openings", "Environment", "Staging")


# ---------------------------------------------------------------------------
# collections
# ---------------------------------------------------------------------------


def get_house_collection(scene: Optional["bpy.types.Scene"] = None) -> "bpy.types.Collection":
    scene = scene or bpy.context.scene
    coll = bpy.data.collections.get(HOUSE_COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(HOUSE_COLLECTION)
    if coll.name not in {c.name for c in scene.collection.children}:
        scene.collection.children.link(coll)
    return coll


def get_subcollection(name: str, scene: Optional["bpy.types.Scene"] = None) -> "bpy.types.Collection":
    parent = get_house_collection(scene)
    full = f"AIG_{name}"
    coll = bpy.data.collections.get(full)
    if coll is None:
        coll = bpy.data.collections.new(full)
    if coll.name not in {c.name for c in parent.children}:
        parent.children.link(coll)
    return coll


def _purge_collection(coll: "bpy.types.Collection") -> int:
    removed = 0
    for child in list(coll.children):
        removed += _purge_collection(child)
        bpy.data.collections.remove(child)
    for obj in list(coll.objects):
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        # Mesh data is not auto-removed when it still has a fake/extra user.
        if isinstance(data, bpy.types.Mesh) and data.users == 0:
            bpy.data.meshes.remove(data)
        removed += 1
    return removed


def clear_house(scene: Optional["bpy.types.Scene"] = None) -> int:
    """Delete every generated object. Returns the number of objects removed.

    This is what makes regeneration idempotent: generate() always clears
    first, so running it twice yields exactly the same scene.
    """
    scene = scene or bpy.context.scene
    coll = bpy.data.collections.get(HOUSE_COLLECTION)
    if coll is None:
        return 0
    removed = _purge_collection(coll)
    bpy.data.collections.remove(coll)
    return removed


def link(obj: "bpy.types.Object", coll: "bpy.types.Collection") -> "bpy.types.Object":
    for existing in list(obj.users_collection):
        existing.objects.unlink(obj)
    coll.objects.link(obj)
    return obj


# ---------------------------------------------------------------------------
# mesh building
# ---------------------------------------------------------------------------


def new_mesh_object(
    name: str,
    bm: "bmesh.types.BMesh",
    coll: "bpy.types.Collection",
) -> "bpy.types.Object":
    """Consume a bmesh into a fresh object linked to ``coll``."""
    mesh = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    coll.objects.link(obj)
    return obj


def box_bmesh(size: Sequence[float], centre: Sequence[float] = (0.0, 0.0, 0.0)) -> "bmesh.types.BMesh":
    """Axis aligned box of full dimensions ``size`` centred on ``centre``."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    bmesh.ops.translate(bm, vec=Vector(centre), verts=bm.verts)
    return bm


def make_box(
    name: str,
    size: Sequence[float],
    centre: Sequence[float],
    coll: "bpy.types.Collection",
) -> "bpy.types.Object":
    return new_mesh_object(name, box_bmesh(size, centre), coll)


def prism_bmesh(
    profile: Sequence[Tuple[float, float]],
    extrude: float,
) -> "bmesh.types.BMesh":
    """Build a closed prism from a 2D profile in the YZ plane.

    The profile is extruded symmetrically along X by ``extrude`` (total
    length). Used for the gable end walls.
    """
    bm = bmesh.new()
    half = extrude / 2.0
    verts = [bm.verts.new((-half, y, z)) for y, z in profile]
    face = bm.faces.new(verts)
    result = bmesh.ops.extrude_face_region(bm, geom=[face])
    moved = [v for v in result["geom"] if isinstance(v, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=Vector((extrude, 0.0, 0.0)), verts=moved)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


# ---------------------------------------------------------------------------
# modifiers
# ---------------------------------------------------------------------------


def apply_modifiers(obj: "bpy.types.Object") -> "bpy.types.Object":
    """Bake every modifier into the mesh, without ``bpy.ops``.

    ``bpy.ops.object.modifier_apply`` needs an active object and a valid
    context override; evaluating the depsgraph does the same job and works
    identically in ``--background``.
    """
    if not obj.modifiers:
        return obj
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    baked = bpy.data.meshes.new_from_object(evaluated)
    old = obj.data
    obj.modifiers.clear()
    obj.data = baked
    baked.name = old.name
    if old.users == 0:
        bpy.data.meshes.remove(old)
    return obj


def boolean_difference(
    target: "bpy.types.Object",
    cutters: Sequence["bpy.types.Object"],
) -> "bpy.types.Object":
    """Subtract ``cutters`` from ``target`` and bake the result."""
    for index, cutter in enumerate(cutters):
        mod = target.modifiers.new(name=f"AIG_cut_{index}", type="BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.object = cutter
        # EXACT is the robust solver; FAST fails on coplanar faces, which is
        # exactly what a window flush with a wall face produces.
        if hasattr(mod, "solver"):
            mod.solver = "EXACT"
    apply_modifiers(target)
    return target


def shade_flat(obj: "bpy.types.Object") -> None:
    """Stylised diorama look: no smoothing anywhere."""
    for polygon in obj.data.polygons:
        polygon.use_smooth = False


# ---------------------------------------------------------------------------
# transforms
# ---------------------------------------------------------------------------


def wall_matrix(wall) -> Matrix:
    """World matrix of a :class:`blender.model.Wall`'s local frame.

    Local frame: origin at the wall centre on its base, +X along the wall
    (start -> end), +Y across the thickness, +Z up. Every wall-relative
    computation (openings, frames) happens in this frame, which is what lets
    an opening be stored as a normalised position.
    """
    cx, cy = wall.centre
    return Matrix.Translation(Vector((cx, cy, wall.base_z))) @ Euler(
        (0.0, 0.0, wall.angle), "XYZ"
    ).to_matrix().to_4x4()


def wall_local_to_world(wall, local: Sequence[float]) -> Vector:
    return wall_matrix(wall) @ Vector(local)


def opening_local_centre(wall, opening) -> Vector:
    """Centre of an opening in the wall's local frame.

    ``position`` is normalised, so ``u`` is recomputed from the wall's current
    length every time - resize the wall and the opening follows (README 11).
    """
    u_min, u_max = opening.span(wall.length)
    z_min, z_max = opening.z_span()
    return Vector(
        (
            (u_min + u_max) / 2.0 - wall.length / 2.0,
            0.0,
            (z_min + z_max) / 2.0,
        )
    )


def frame_scene(
    objects: Iterable["bpy.types.Object"],
) -> Tuple[Vector, Vector, Vector]:
    """Return ``(minimum, maximum, centre)`` world bounds of ``objects``."""
    lo = Vector((math.inf,) * 3)
    hi = Vector((-math.inf,) * 3)
    found = False
    for obj in objects:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            world = obj.matrix_world @ Vector(corner)
            lo = Vector((min(lo[i], world[i]) for i in range(3)))
            hi = Vector((max(hi[i], world[i]) for i in range(3)))
            found = True
    if not found:
        lo = Vector((0.0, 0.0, 0.0))
        hi = Vector((1.0, 1.0, 1.0))
    return lo, hi, (lo + hi) / 2.0
