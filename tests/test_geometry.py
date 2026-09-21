"""Geometry tests. These MUST run inside Blender:

    blender --background --python tests/run_in_blender.py

They are written as plain functions (no pytest dependency inside Blender's
bundled Python) and collected by the runner.
"""

from __future__ import annotations

import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from blender.environment import terrain as terrain_mod  # noqa: E402
from blender.environment import vegetation as vegetation_mod  # noqa: E402
from blender.geometry import common, generator  # noqa: E402
from blender.geometry import roof as roof_mod  # noqa: E402
from blender.geometry import wall as wall_mod  # noqa: E402
from blender.materials import palette  # noqa: E402
from blender.model import Door, Floor, House, Room, Window  # noqa: E402

EXAMPLES = os.path.join(REPO, "examples")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def reset_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def world_bounds(obj):
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    lo = Vector(tuple(min(c[i] for c in corners) for i in range(3)))
    hi = Vector(tuple(max(c[i] for c in corners) for i in range(3)))
    return lo, hi


def mesh_volume(obj) -> float:
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)
    volume = bm.calc_volume(signed=True)
    bm.free()
    return abs(volume)


def objects_of_type(kind):
    return [obj for obj in bpy.data.objects if obj.get("aig_type") == kind]


def approx(a, b, tol=1e-4):
    assert abs(a - b) <= tol, f"expected {b}, got {a} (tol {tol})"


# ---------------------------------------------------------------------------
# walls
# ---------------------------------------------------------------------------


def test_single_room_generates_four_wall_objects():
    reset_scene()
    house = House.simple(width=10, depth=8)
    house.floor(0).doors.clear()
    house.floor(0).windows.clear()
    generator.generate_house(house, environment=False)
    walls = objects_of_type("wall")
    assert len(walls) == 4, f"expected 4 walls, got {len(walls)}"


def test_wall_object_length_matches_model():
    reset_scene()
    house = House.simple(width=10, depth=8)
    house.floor(0).doors.clear()
    house.floor(0).windows.clear()
    generator.generate_house(house, environment=False)

    by_id = {obj["aig_wall_id"]: obj for obj in objects_of_type("wall")}
    for wall in house.all_walls():
        obj = by_id[wall.id]
        lo, hi = world_bounds(obj)
        span = max(hi.x - lo.x, hi.y - lo.y)
        approx(span, wall.length, tol=1e-3)


def test_wall_height_matches_storey():
    reset_scene()
    house = House.simple(width=10, depth=8, height=3.4)
    house.floor(0).doors.clear()
    house.floor(0).windows.clear()
    generator.generate_house(house, environment=False)
    for obj in objects_of_type("wall"):
        lo, hi = world_bounds(obj)
        approx(hi.z - lo.z, 3.4, tol=1e-3)


def test_shared_wall_generates_one_object():
    """Two adjacent rooms must produce ONE wall object between them."""
    reset_scene()
    floor = Floor(level=0, rooms=[Room("a", 0, 0, 6, 5), Room("b", 6, 0, 4, 5)])
    house = House(name="t", width=10, depth=5, floors=[floor])
    generator.generate_house(house, environment=False)
    walls = objects_of_type("wall")
    assert len(walls) == 7, f"expected 7 walls (8 edges - 1 shared), got {len(walls)}"
    shared = [obj for obj in walls if not obj["aig_exterior"]]
    assert len(shared) == 1, f"expected 1 shared wall, got {len(shared)}"


def test_upper_floor_walls_sit_on_lower_ones():
    reset_scene()
    house = House.simple(width=8, depth=6, floors=2, height=2.5)
    for storey in house.floors:
        storey.doors.clear()
        storey.windows.clear()
    generator.generate_house(house, environment=False)

    zs = sorted({round(world_bounds(obj)[0].z, 3) for obj in objects_of_type("wall")})
    assert zs == [0.0, 2.5], f"expected wall bases at 0.0 and 2.5, got {zs}"


# ---------------------------------------------------------------------------
# openings cut real holes
# ---------------------------------------------------------------------------


def test_opening_cut_leaves_a_hole():
    """The boolean must actually remove volume from the wall mesh."""
    reset_scene()
    house = House.simple(width=10, depth=8)
    house.floor(0).doors.clear()
    house.floor(0).windows.clear()
    generator.generate_house(house, environment=False)
    solid = {
        obj["aig_wall_id"]: mesh_volume(obj) for obj in objects_of_type("wall")
    }

    reset_scene()
    house = House.simple(width=10, depth=8)
    ground = house.floor(0)
    ground.doors.clear()
    ground.windows.clear()
    window = Window(wall="L0_main:south", position=0.5, width=1.4, height=1.2)
    ground.windows.append(window)
    generator.generate_house(house, environment=False)
    holed = {
        obj["aig_wall_id"]: mesh_volume(obj) for obj in objects_of_type("wall")
    }

    wall = house.floor(0).wall_map()["L0_main:south"]
    expected_cut = 1.4 * 1.2 * wall.thickness
    actual_cut = solid["L0_main:south"] - holed["L0_main:south"]
    approx(actual_cut, expected_cut, tol=1e-3)

    # walls without openings are untouched
    for wall_id in ("L0_main:north", "L0_main:east", "L0_main:west"):
        approx(holed[wall_id], solid[wall_id], tol=1e-6)


def test_holed_wall_has_more_geometry_than_a_plain_box():
    reset_scene()
    house = House.simple(width=10, depth=8)
    generator.generate_house(house, environment=False)
    by_id = {obj["aig_wall_id"]: obj for obj in objects_of_type("wall")}
    # south has the door, west has nothing
    assert len(by_id["L0_main:south"].data.vertices) > 8
    assert len(by_id["L0_main:west"].data.vertices) == 8


def test_two_openings_on_one_wall_cut_both():
    reset_scene()
    house = House.simple(width=12, depth=8)
    ground = house.floor(0)
    ground.doors.clear()
    ground.windows.clear()
    generator.generate_house(house, environment=False)
    solid = mesh_volume(
        {o["aig_wall_id"]: o for o in objects_of_type("wall")}["L0_main:south"]
    )

    reset_scene()
    house = House.simple(width=12, depth=8)
    ground = house.floor(0)
    ground.doors.clear()
    ground.windows.clear()
    ground.windows.append(Window(wall="L0_main:south", position=0.25, width=1.4, height=1.2))
    ground.windows.append(Window(wall="L0_main:south", position=0.75, width=1.4, height=1.2))
    generator.generate_house(house, environment=False)
    holed = mesh_volume(
        {o["aig_wall_id"]: o for o in objects_of_type("wall")}["L0_main:south"]
    )
    wall = house.floor(0).wall_map()["L0_main:south"]
    approx(solid - holed, 2 * 1.4 * 1.2 * wall.thickness, tol=1e-3)


def test_window_produces_frame_and_glass():
    reset_scene()
    house = House.simple(width=10, depth=8)
    ground = house.floor(0)
    ground.doors.clear()
    ground.windows.clear()
    ground.windows.append(Window(wall="L0_main:south", position=0.5))
    generator.generate_house(house, environment=False)
    assert len(objects_of_type("window_frame")) == 4
    assert len(objects_of_type("window_glass")) == 1


def test_door_produces_jambs_and_leaf():
    reset_scene()
    house = House.simple(width=10, depth=8)
    ground = house.floor(0)
    ground.doors.clear()
    ground.windows.clear()
    ground.doors.append(Door(wall="L0_main:south", position=0.5))
    generator.generate_house(house, environment=False)
    assert len(objects_of_type("door_frame")) == 3
    assert len(objects_of_type("door_leaf")) == 1


def test_opening_is_positioned_from_normalised_position():
    """Section 11: the same model at two sizes puts the window proportionally."""
    for width, expected_x in ((10.0, 2.5), (20.0, 5.0)):
        reset_scene()
        house = House.simple(width=width, depth=8)
        ground = house.floor(0)
        ground.doors.clear()
        ground.windows.clear()
        ground.windows.append(Window(wall="L0_main:south", position=0.25, width=1.2))
        generator.generate_house(house, environment=False)
        glass = objects_of_type("window_glass")[0]
        # Measure the bounding-box centre, NOT matrix_world.translation: the
        # offset within the wall is baked into the mesh vertices, so the
        # object's origin sits at the wall centre for every opening.
        lo, hi = world_bounds(glass)
        approx((lo.x + hi.x) / 2.0, expected_x, tol=1e-3)


def test_door_sits_on_the_floor():
    reset_scene()
    house = House.simple(width=10, depth=8)
    ground = house.floor(0)
    ground.doors.clear()
    ground.windows.clear()
    ground.doors.append(Door(wall="L0_main:south", position=0.5, height=2.1))
    generator.generate_house(house, environment=False)
    leaf = objects_of_type("door_leaf")[0]
    lo, _ = world_bounds(leaf)
    assert lo.z < 0.15, f"door leaf should start near z=0, got {lo.z}"


# ---------------------------------------------------------------------------
# roof
# ---------------------------------------------------------------------------


def test_roof_height_follows_pitch():
    """Ridge height = (span / 2) * tan(pitch), measured on the rafter plane.

    The slab is extruded along its normal, so its TOP surface at the ridge is
    a further ``thickness * cos(pitch)`` above that plane - accounted for here
    rather than fudged with a loose tolerance.
    """
    heights = []
    for pitch in (20.0, 35.0, 50.0):
        reset_scene()
        house = House.simple(width=10, depth=8, pitch=pitch)
        generator.generate_house(house, environment=False)
        top = max(world_bounds(obj)[1].z for obj in objects_of_type("roof_slab"))
        rafter_ridge = house.total_height + 4.0 * math.tan(math.radians(pitch))
        expected = rafter_ridge + house.roof.thickness * math.cos(math.radians(pitch))
        approx(top, expected, tol=1e-3)
        heights.append(top)
    assert heights == sorted(heights), f"steeper pitch must be taller: {heights}"


def test_roof_generates_two_slabs_and_two_gables():
    reset_scene()
    house = House.simple(width=10, depth=8)
    generator.generate_house(house, environment=False)
    assert len(objects_of_type("roof_slab")) == 2
    assert len(objects_of_type("roof_gable")) == 2


def test_roof_slabs_meet_at_the_ridge():
    reset_scene()
    house = House.simple(width=10, depth=8)
    generator.generate_house(house, environment=False)
    tops = [world_bounds(obj)[1].z for obj in objects_of_type("roof_slab")]
    approx(tops[0], tops[1], tol=1e-3)


def test_roof_overhang_extends_past_the_walls():
    reset_scene()
    house = House.simple(width=10, depth=8)
    house.roof.overhang = 0.8
    generator.generate_house(house, environment=False)
    wall_hi = max(world_bounds(obj)[1].y for obj in objects_of_type("wall"))
    roof_hi = max(world_bounds(obj)[1].y for obj in objects_of_type("roof_slab"))
    assert roof_hi > wall_hi + 0.5, f"roof {roof_hi} should overhang walls {wall_hi}"


def test_roof_sits_on_top_of_the_walls():
    reset_scene()
    house = House.simple(width=10, depth=8, floors=2, height=2.6)
    generator.generate_house(house, environment=False)
    wall_top = max(world_bounds(obj)[1].z for obj in objects_of_type("wall"))
    roof_bottom = min(world_bounds(obj)[0].z for obj in objects_of_type("roof_gable"))
    approx(roof_bottom, wall_top, tol=0.05)


def test_ridge_runs_along_the_longer_side():
    reset_scene()
    house = House.simple(width=14, depth=7)
    generator.generate_house(house, environment=False)
    slab = objects_of_type("roof_slab")[0]
    lo, hi = world_bounds(slab)
    assert (hi.x - lo.x) > (hi.y - lo.y), "ridge should run along X for a wide house"

    reset_scene()
    house = House.simple(width=7, depth=14)
    generator.generate_house(house, environment=False)
    slab = objects_of_type("roof_slab")[0]
    lo, hi = world_bounds(slab)
    assert (hi.y - lo.y) > (hi.x - lo.x), "ridge should run along Y for a deep house"


# ---------------------------------------------------------------------------
# floors, materials, environment
# ---------------------------------------------------------------------------


def test_each_room_gets_a_floor_slab():
    reset_scene()
    floor = Floor(level=0, rooms=[Room("a", 0, 0, 6, 5), Room("b", 6, 0, 4, 5)])
    house = House(name="t", width=10, depth=5, floors=[floor])
    generator.generate_house(house, environment=False)
    assert len(objects_of_type("floor")) == 2


def test_materials_are_reused_not_duplicated():
    reset_scene()
    house = House.simple(width=10, depth=8)
    generator.generate_house(house, environment=False)
    generator.generate_house(house, environment=False)
    names = [m.name for m in bpy.data.materials if m.name.startswith(palette.PREFIX)]
    assert len(names) == len(set(names)), f"duplicate materials: {names}"
    assert not any(".001" in name for name in names), names


def test_every_generated_mesh_has_a_material():
    reset_scene()
    house = House.simple(width=10, depth=8)
    generator.generate_house(house, environment=True)
    for obj in bpy.data.objects:
        if obj.type == "MESH" and obj.name.startswith("AIG_"):
            assert obj.data.materials, f"{obj.name} has no material"


def test_terrain_covers_the_house_with_margin():
    reset_scene()
    house = House.simple(width=10, depth=8)
    house.terrain_margin = 5.0
    generator.generate_house(house, environment=True)
    ground = objects_of_type("terrain")[0]
    lo, hi = world_bounds(ground)
    assert lo.x < 0 and lo.y < 0
    assert hi.x > 10 and hi.y > 8


def test_terrain_is_flat_under_the_house():
    reset_scene()
    house = House.simple(width=10, depth=8)
    generator.generate_house(house, environment=True)
    ground = objects_of_type("terrain")[0]
    for vert in ground.data.vertices:
        world = ground.matrix_world @ vert.co
        if 1.0 < world.x < 9.0 and 1.0 < world.y < 7.0:
            assert abs(world.z) < 1e-5, f"pad not flat at {world}"


def test_trees_reuse_shared_meshes():
    reset_scene()
    house = House.simple(width=10, depth=8)
    house.tree_count = 8
    generator.generate_house(house, environment=True)
    trees = objects_of_type("tree")
    assert len(trees) == 16, f"8 trees = 16 objects, got {len(trees)}"
    meshes = {obj.data.name for obj in trees}
    assert len(meshes) == 2, f"expected 2 shared meshes, got {meshes}"


def test_tree_placement_is_deterministic():
    positions = []
    for _ in range(2):
        reset_scene()
        house = House.simple(width=10, depth=8)
        house.seed = 42
        generator.generate_house(house, environment=True)
        positions.append(
            sorted(tuple(round(v, 4) for v in o.location) for o in objects_of_type("tree"))
        )
    assert positions[0] == positions[1]


# ---------------------------------------------------------------------------
# regeneration / idempotency
# ---------------------------------------------------------------------------


def test_regeneration_is_idempotent():
    reset_scene()
    house = House.simple(width=10, depth=8)
    generator.generate_house(house, environment=True)
    first = sorted(obj.name for obj in bpy.data.objects)
    generator.generate_house(house, environment=True)
    second = sorted(obj.name for obj in bpy.data.objects)
    generator.generate_house(house, environment=True)
    third = sorted(obj.name for obj in bpy.data.objects)
    assert first == second == third, "object set changed across regenerations"
    assert not any(".001" in name for name in third), "leaked duplicate objects"


def test_json_round_trip_regenerates_identical_object_set():
    reset_scene()
    house = House.load(os.path.join(EXAMPLES, "cottage.json"))
    generator.generate_house(house, environment=True)
    before = sorted(obj.name for obj in bpy.data.objects)

    reset_scene()
    reloaded = House.from_json(house.to_json())
    generator.generate_house(reloaded, environment=True)
    after = sorted(obj.name for obj in bpy.data.objects)
    assert before == after, "JSON round-trip changed the generated scene"


def test_clear_removes_everything():
    reset_scene()
    house = House.simple(width=10, depth=8)
    generator.generate_house(house, environment=True)
    assert len(bpy.data.objects) > 0
    common.clear_house()
    assert len(bpy.data.objects) == 0
    assert common.HOUSE_COLLECTION not in bpy.data.collections


def test_model_is_stored_on_the_scene():
    reset_scene()
    house = House.simple(width=11, depth=9, pitch=40)
    generator.generate_house(house, environment=False)
    restored = generator.load_model()
    assert restored is not None
    assert restored.to_dict() == house.to_dict()


def test_resize_regenerates_the_whole_house():
    """README section 26 'segundo paso'."""
    reset_scene()
    house = House.simple(width=10, depth=8)
    generator.generate_house(house, environment=False)
    before = max(world_bounds(obj)[1].x for obj in objects_of_type("wall"))

    house.resize(16, 12)
    generator.generate_house(house, environment=False)
    after = max(world_bounds(obj)[1].x for obj in objects_of_type("wall"))
    approx(before, 10.0, tol=0.2)
    approx(after, 16.0, tol=0.2)


# ---------------------------------------------------------------------------
# examples + camera
# ---------------------------------------------------------------------------


def test_all_examples_generate():
    for filename in ("small_house.json", "cottage.json", "medieval_house.json"):
        reset_scene()
        house = House.load(os.path.join(EXAMPLES, filename))
        created = generator.generate_house(house, environment=True)
        assert created["walls"], f"{filename} produced no walls"
        assert created["roof"], f"{filename} produced no roof"
        expected_walls = len(house.all_walls())
        assert len(created["walls"]) == expected_walls, (
            f"{filename}: {len(created['walls'])} wall objects "
            f"vs {expected_walls} model walls"
        )


def test_camera_and_sun_are_created_and_frame_the_house():
    reset_scene()
    house = House.simple(width=10, depth=8)
    generator.generate_house(house, environment=True)
    rig = generator.setup_camera_and_light(house)
    assert bpy.context.scene.camera is rig["camera"]
    assert rig["sun"].data.type == "SUN"
    # camera must be outside the house and above ground
    assert rig["camera"].location.z > 0
    assert rig["camera"].location.length > 5


def test_stone_scatter_flag_adds_a_modifier_without_extra_objects():
    reset_scene()
    house = House.simple(width=10, depth=8)
    generator.generate_house(house, environment=False)
    plain = len(bpy.data.objects)

    reset_scene()
    house = House.simple(width=10, depth=8)
    house.stone_walls = True
    generator.generate_house(house, environment=False)
    assert len(bpy.data.objects) == plain, "stone scatter must not add objects"
    walls = objects_of_type("wall")
    assert all(
        any(mod.type == "NODES" for mod in obj.modifiers) for obj in walls
    ), "expected a Geometry Nodes modifier on every wall"
