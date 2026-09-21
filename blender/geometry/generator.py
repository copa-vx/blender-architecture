"""The model -> scene entry point.

    House (pure data)  ->  generate_house()  ->  Blender objects

``generate_house`` always calls :func:`blender.geometry.common.clear_house`
first, so it is idempotent: running it twice with the same model produces the
same scene, and running it with a modified model regenerates everything from
the new parameters instead of patching meshes.

The model itself is stashed as JSON on the scene (``scene["aig_house"]``) so
the .blend round-trips: reopen the file and you still have the parametric
description, not just the mesh.
"""

from __future__ import annotations

import json
import math
from typing import Dict, List, Optional

import bpy
from mathutils import Euler, Matrix, Vector

from ..environment import terrain as terrain_mod
from ..environment import vegetation as vegetation_mod
from ..materials import palette
from . import common, door, roof as roof_mod, room as room_mod, wall as wall_mod

SCENE_KEY = "aig_house"


def store_model(house, scene: Optional["bpy.types.Scene"] = None) -> None:
    scene = scene or bpy.context.scene
    scene[SCENE_KEY] = house.to_json()


def load_model(scene: Optional["bpy.types.Scene"] = None):
    """Read back the model stored on the scene, or ``None``."""
    from ..model import House

    scene = scene or bpy.context.scene
    raw = scene.get(SCENE_KEY)
    if not raw:
        return None
    return House.from_json(raw)


def generate_house(
    house,
    scene: Optional["bpy.types.Scene"] = None,
    environment: bool = True,
    validate: bool = True,
) -> Dict[str, List["bpy.types.Object"]]:
    """Build the whole house. Returns the created objects grouped by kind."""
    scene = scene or bpy.context.scene
    if validate:
        house.validate()

    common.clear_house(scene)

    walls_coll = common.get_subcollection("Walls", scene)
    floors_coll = common.get_subcollection("Floors", scene)
    roof_coll = common.get_subcollection("Roof", scene)
    openings_coll = common.get_subcollection("Openings", scene)
    staging = common.get_subcollection("Staging", scene)

    created: Dict[str, List["bpy.types.Object"]] = {
        "walls": [],
        "floors": [],
        "roof": [],
        "openings": [],
        "environment": [],
    }

    wall_material = "STONE" if house.style in ("medieval", "cottage") else "PLASTER"

    for storey in sorted(house.floors, key=lambda f: f.level):
        base_z = house.base_z(storey.level)

        created["floors"].extend(
            room_mod.build_floor_slabs(storey, base_z=base_z, coll=floors_coll)
        )

        for w in storey.walls(base_z=base_z):
            openings = storey.openings_for(w.id)
            created["walls"].append(
                wall_mod.build_wall(
                    w,
                    openings=openings,
                    coll=walls_coll,
                    staging=staging,
                    material=wall_material,
                    stone=bool(house.stone_walls),
                )
            )
            for opening in openings:
                if opening.kind == "door":
                    created["openings"].extend(
                        door.build_door(w, opening, coll=openings_coll)
                    )
                else:
                    from . import window as window_mod

                    created["openings"].extend(
                        window_mod.build_window(w, opening, coll=openings_coll)
                    )

    created["roof"].extend(roof_mod.build_roof(house, coll=roof_coll))

    if environment:
        created["environment"].append(terrain_mod.build_terrain(house))
        created["environment"].extend(vegetation_mod.build_vegetation(house))

    # staging is only used for boolean cutters; it should be empty now
    if not staging.objects:
        parent = common.get_house_collection(scene)
        if staging.name in {c.name for c in parent.children}:
            parent.children.unlink(staging)
        bpy.data.collections.remove(staging)

    store_model(house, scene)
    return created


# ---------------------------------------------------------------------------
# camera + light, so a render is one call away
# ---------------------------------------------------------------------------


def setup_camera_and_light(
    house,
    scene: Optional["bpy.types.Scene"] = None,
    angle_deg: float = 42.0,
) -> Dict[str, "bpy.types.Object"]:
    """Diorama-ish 3/4 view framing the whole house, plus a sun.

    The camera is pushed back along the view direction until the house's
    bounding sphere fits inside the (narrower) vertical FOV, with a margin.
    """
    scene = scene or bpy.context.scene
    coll = common.get_subcollection("Environment", scene)

    house_coll = bpy.data.collections.get(common.HOUSE_COLLECTION)
    objects = []
    if house_coll is not None:
        for sub in house_coll.children:
            if sub.name.endswith("Environment"):
                continue  # frame the building, not the terrain
            objects.extend(sub.objects)
    lo, hi, centre = common.frame_scene(objects)
    radius = max((hi - lo).length / 2.0, 1.0)

    # -- camera -------------------------------------------------------------
    cam_data = bpy.data.cameras.get("AIG_Camera") or bpy.data.cameras.new("AIG_Camera")
    cam_data.lens = 50.0
    cam = bpy.data.objects.get("AIG_Camera")
    if cam is None:
        cam = bpy.data.objects.new("AIG_Camera", cam_data)
    common.link(cam, coll)

    fov = 2.0 * math.atan(cam_data.sensor_width / 2.0 / cam_data.lens)
    aspect = scene.render.resolution_y / max(1, scene.render.resolution_x)
    vfov = 2.0 * math.atan(math.tan(fov / 2.0) * aspect)
    distance = radius / math.tan(min(fov, vfov) / 2.0) * 1.25

    azimuth = math.radians(-125.0)     # looking from the south-east
    elevation = math.radians(angle_deg)
    direction = Vector(
        (
            math.cos(elevation) * math.cos(azimuth),
            math.cos(elevation) * math.sin(azimuth),
            math.sin(elevation),
        )
    )
    cam.location = centre + direction * distance
    # point the camera's -Z at the centre
    cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam

    # -- sun ----------------------------------------------------------------
    sun_data = bpy.data.lights.get("AIG_Sun") or bpy.data.lights.new("AIG_Sun", type="SUN")
    sun_data.energy = 4.0
    if hasattr(sun_data, "angle"):
        sun_data.angle = math.radians(2.0)  # slightly soft shadows
    sun = bpy.data.objects.get("AIG_Sun")
    if sun is None:
        sun = bpy.data.objects.new("AIG_Sun", sun_data)
    common.link(sun, coll)
    sun.location = centre + Vector((-radius, -radius * 0.6, radius * 2.2))
    sun.rotation_euler = Euler((math.radians(52.0), 0.0, math.radians(35.0)), "XYZ")

    # a plain sky so EEVEE has ambient light
    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("AIG_World")
        scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs[0].default_value = (0.55, 0.70, 0.90, 1.0)
        bg.inputs[1].default_value = 1.0

    return {"camera": cam, "sun": sun}
