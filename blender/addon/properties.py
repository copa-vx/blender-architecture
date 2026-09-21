"""Scene property group driving the panel.

These are the *authoring* parameters (README section 26's ``create_house``).
They are deliberately a small subset - the full model is richer than what the
panel exposes, which is why Load JSON exists.
"""

from __future__ import annotations

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    StringProperty,
)
from bpy.types import PropertyGroup, Scene


class AIG_HouseProperties(PropertyGroup):
    name: StringProperty(
        name="Name",
        description="Name of the house",
        default="house",
    )
    width: FloatProperty(
        name="Width",
        description="House footprint along X, in metres",
        default=10.0,
        min=2.0,
        soft_max=40.0,
        unit="LENGTH",
    )
    depth: FloatProperty(
        name="Depth",
        description="House footprint along Y, in metres",
        default=8.0,
        min=2.0,
        soft_max=40.0,
        unit="LENGTH",
    )
    floors: IntProperty(
        name="Floors",
        description="Number of storeys",
        default=1,
        min=1,
        max=4,
    )
    floor_height: FloatProperty(
        name="Floor Height",
        description="Height of one storey, in metres",
        default=2.8,
        min=2.0,
        soft_max=5.0,
        unit="LENGTH",
    )
    wall_thickness: FloatProperty(
        name="Wall Thickness",
        default=0.25,
        min=0.05,
        soft_max=1.0,
        unit="LENGTH",
    )
    roof_type: EnumProperty(
        name="Roof",
        description="Roof style (Milestone 1 implements gable only)",
        items=[("gable", "Gable (dos aguas)", "Two sloped planes meeting at a ridge")],
        default="gable",
    )
    roof_pitch: FloatProperty(
        name="Pitch",
        description="Roof pitch in degrees",
        default=35.0,
        min=5.0,
        max=85.0,
    )
    roof_overhang: FloatProperty(
        name="Overhang",
        default=0.5,
        min=0.0,
        soft_max=2.0,
        unit="LENGTH",
    )
    style: EnumProperty(
        name="Style",
        items=[
            ("cottage", "Cottage", "Stone walls"),
            ("medieval", "Medieval", "Stone walls"),
            ("modern", "Modern", "Plaster walls"),
        ],
        default="cottage",
    )
    stone_walls: BoolProperty(
        name="Stone Scatter",
        description=(
            "Add the experimental Geometry Nodes stone scatter to walls "
            "(Milestone 2 preview - off by default)"
        ),
        default=False,
    )
    environment: BoolProperty(
        name="Environment",
        description="Also generate terrain and trees",
        default=True,
    )
    tree_count: IntProperty(name="Trees", default=6, min=0, max=60)
    seed: IntProperty(name="Seed", default=0, min=0)
    json_path: StringProperty(
        name="JSON",
        description="House JSON file to load or save",
        subtype="FILE_PATH",
        default="",
    )


_CLASSES = (AIG_HouseProperties,)


def register() -> None:
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    Scene.aig_house = bpy.props.PointerProperty(type=AIG_HouseProperties)


def unregister() -> None:
    if hasattr(Scene, "aig_house"):
        del Scene.aig_house
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
