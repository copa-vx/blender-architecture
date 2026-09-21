"""Bridge between the panel properties and the parametric model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..model import House

if TYPE_CHECKING:  # pragma: no cover
    import bpy


def props_to_model(props) -> House:
    """Build a :class:`House` from the scene property group."""
    house = House.simple(
        width=float(props.width),
        depth=float(props.depth),
        floors=int(props.floors),
        height=float(props.floor_height),
        roof=str(props.roof_type),
        pitch=float(props.roof_pitch),
        name=str(props.name) or "house",
    )
    house.roof.overhang = float(props.roof_overhang)
    house.style = str(props.style)
    house.stone_walls = bool(props.stone_walls)
    house.tree_count = int(props.tree_count)
    house.seed = int(props.seed)
    for storey in house.floors:
        storey.wall_thickness = float(props.wall_thickness)
    return house


def model_to_props(house: House, props) -> None:
    """Push a loaded model back into the panel, so the UI stays in sync."""
    props.name = house.name
    props.width = float(house.width)
    props.depth = float(house.depth)
    props.floors = max(1, len(house.floors))
    if house.floors:
        props.floor_height = float(house.floors[0].height)
        props.wall_thickness = float(house.floors[0].wall_thickness)
    props.roof_type = house.roof.type
    props.roof_pitch = float(house.roof.pitch)
    props.roof_overhang = float(house.roof.overhang)
    if house.style in ("cottage", "medieval", "modern"):
        props.style = house.style
    props.stone_walls = bool(house.stone_walls)
    props.tree_count = int(house.tree_count)
    props.seed = int(house.seed)
