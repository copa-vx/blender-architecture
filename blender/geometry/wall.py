"""Wall generator (README section 9).

One mesh per wall - never one object per stone. The optional stone look is a
Geometry Nodes scatter *on that same mesh* so the object count stays flat
regardless of how detailed the wall is.

Openings: we build the wall as a solid box and subtract a cutter box per
opening with an EXACT boolean, then bake the modifier.
Why boolean rather than authoring the holed mesh directly with bmesh:

* the wall stays a single closed manifold, so the roof boolean and any later
  modifier keep working;
* it generalises for free to openings that are not axis aligned in the wall
  (arched tops, corner windows) which is where this is going in Milestone 2;
* cost is negligible at this scale (a wall has < 10 openings).

The cutters are built in the wall's local frame and are deliberately longer
than the wall is thick, so the cut is clean on both faces instead of leaving
coplanar geometry.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

import bmesh
import bpy
from mathutils import Vector

from ..materials import palette
from . import common

#: Extra depth added to each side of an opening cutter.
CUT_BLEED = 0.05


def _cutter(wall, opening, coll: "bpy.types.Collection") -> "bpy.types.Object":
    centre = common.opening_local_centre(wall, opening)
    size = (
        float(opening.width),
        float(wall.thickness) + 2 * CUT_BLEED,
        float(opening.height),
    )
    obj = common.make_box(f"AIG_cut_{wall.id}_{opening.kind}", size, centre, coll)
    obj.matrix_world = common.wall_matrix(wall) @ obj.matrix_world
    return obj


def build_wall(
    wall,
    openings: Sequence = (),
    coll: Optional["bpy.types.Collection"] = None,
    staging: Optional["bpy.types.Collection"] = None,
    material: str = "STONE",
    stone: bool = False,
) -> "bpy.types.Object":
    """Create one wall object, with its openings already cut out."""
    coll = coll or common.get_subcollection("Walls")
    staging = staging or common.get_subcollection("Staging")

    obj = common.make_box(
        f"AIG_wall_{wall.id}",
        (wall.length, float(wall.thickness), float(wall.height)),
        (0.0, 0.0, float(wall.height) / 2.0),
        coll,
    )
    obj.matrix_world = common.wall_matrix(wall)

    cutters: List["bpy.types.Object"] = [_cutter(wall, op, staging) for op in openings]
    if cutters:
        common.boolean_difference(obj, cutters)
        for cutter in cutters:
            mesh = cutter.data
            bpy.data.objects.remove(cutter, do_unlink=True)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)

    palette.assign(obj, material)
    common.shade_flat(obj)

    obj["aig_type"] = "wall"
    obj["aig_wall_id"] = wall.id
    obj["aig_exterior"] = wall.exterior
    obj["aig_length"] = wall.length

    if stone:
        add_stone_nodes(obj, seed=abs(hash(wall.id)) % 9973)
    return obj


def build_walls(
    floor,
    base_z: float = 0.0,
    coll: Optional["bpy.types.Collection"] = None,
    material: str = "STONE",
    stone: bool = False,
) -> List["bpy.types.Object"]:
    coll = coll or common.get_subcollection("Walls")
    objects = []
    for wall in floor.walls(base_z=base_z):
        objects.append(
            build_wall(
                wall,
                openings=floor.openings_for(wall.id),
                coll=coll,
                material=material,
                stone=stone,
            )
        )
    return objects


# ---------------------------------------------------------------------------
# optional stone scatter (off by default - full stone look is Milestone 2)
# ---------------------------------------------------------------------------

STONE_NODEGROUP = "AIG_StoneScatter"


def _stone_nodegroup() -> "bpy.types.GeometryNodeTree":
    """Small GN tree: scatter small cubes on the wall faces and realise them.

    Node identifiers verified against Blender 5.1
    (``GeometryNodeDistributePointsOnFaces``, ``GeometryNodeInstanceOnPoints``,
    ``GeometryNodeRealizeInstances``, ``GeometryNodeMeshCube``). The result is
    still ONE mesh - realise happens inside the modifier, no extra objects.
    """
    existing = bpy.data.node_groups.get(STONE_NODEGROUP)
    if existing is not None:
        return existing

    tree = bpy.data.node_groups.new(STONE_NODEGROUP, "GeometryNodeTree")
    # Blender 4.x/5.x interface API (the 3.x `tree.inputs` collection is gone).
    tree.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    tree.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    density = tree.interface.new_socket(
        "Density", in_out="INPUT", socket_type="NodeSocketFloat"
    )
    density.default_value = 8.0
    size = tree.interface.new_socket("Size", in_out="INPUT", socket_type="NodeSocketFloat")
    size.default_value = 0.22
    seed = tree.interface.new_socket("Seed", in_out="INPUT", socket_type="NodeSocketInt")
    seed.default_value = 0

    nodes = tree.nodes
    links = tree.links

    group_in = nodes.new("NodeGroupInput")
    group_in.location = (-600, 0)
    group_out = nodes.new("NodeGroupOutput")
    group_out.location = (600, 0)

    scatter = nodes.new("GeometryNodeDistributePointsOnFaces")
    scatter.location = (-320, 120)
    cube = nodes.new("GeometryNodeMeshCube")
    cube.location = (-320, -220)
    instance = nodes.new("GeometryNodeInstanceOnPoints")
    instance.location = (-40, 60)
    realize = nodes.new("GeometryNodeRealizeInstances")
    realize.location = (200, 60)
    join = nodes.new("GeometryNodeJoinGeometry")
    join.location = (400, 0)

    links.new(group_in.outputs["Geometry"], scatter.inputs["Mesh"])
    links.new(group_in.outputs["Density"], scatter.inputs["Density"])
    links.new(group_in.outputs["Seed"], scatter.inputs["Seed"])
    links.new(scatter.outputs["Points"], instance.inputs["Points"])
    links.new(cube.outputs["Mesh"], instance.inputs["Instance"])
    links.new(instance.outputs["Instances"], realize.inputs["Geometry"])
    links.new(realize.outputs["Geometry"], join.inputs["Geometry"])
    links.new(group_in.outputs["Geometry"], join.inputs["Geometry"])
    links.new(join.outputs["Geometry"], group_out.inputs["Geometry"])

    # cube size driven by the group input
    combine = nodes.new("ShaderNodeCombineXYZ")
    combine.location = (-520, -260)
    links.new(group_in.outputs["Size"], combine.inputs["X"])
    links.new(group_in.outputs["Size"], combine.inputs["Y"])
    links.new(group_in.outputs["Size"], combine.inputs["Z"])
    links.new(combine.outputs["Vector"], cube.inputs["Size"])

    return tree


def add_stone_nodes(obj: "bpy.types.Object", seed: int = 0) -> "bpy.types.Modifier":
    """Attach the stone scatter as a live modifier (not baked, so it stays cheap)."""
    mod = obj.modifiers.new(name="AIG_Stone", type="NODES")
    mod.node_group = _stone_nodegroup()
    # Socket identifiers are Socket_2, Socket_3... in declaration order.
    for item in mod.node_group.interface.items_tree:
        if getattr(item, "in_out", None) == "INPUT" and item.name == "Seed":
            try:
                mod[item.identifier] = int(seed)
            except (KeyError, TypeError):
                pass
    return mod
