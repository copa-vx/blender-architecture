"""Pure-Python tests for the house model. No Blender required.

    python3 -m pytest tests/test_house.py -v
"""

from __future__ import annotations

import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from blender.model.house import (  # noqa: E402
    Door,
    Floor,
    House,
    Roof,
    Room,
    ValidationError,
    Window,
    create_house,
)

EXAMPLES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples"
)


# ---------------------------------------------------------------------------
# construction
# ---------------------------------------------------------------------------


def test_create_house_readme_example():
    """README section 7: create_house({"width": 10, "depth": 8})."""
    house = create_house({"width": 10, "depth": 8})
    assert house.width == 10
    assert house.depth == 8
    assert len(house.floors) == 1
    assert house.area == pytest.approx(80.0)


def test_simple_house_has_four_walls_one_door_two_windows():
    """README section 26's MVP: door + two windows."""
    house = House.simple(width=10, depth=8)
    assert len(house.all_walls()) == 4
    ground = house.floor(0)
    assert len(ground.doors) == 1
    assert len(ground.windows) == 2


def test_multi_storey_stacks_base_z():
    house = House.simple(width=8, depth=6, floors=3, height=2.5)
    assert house.base_z(0) == pytest.approx(0.0)
    assert house.base_z(1) == pytest.approx(2.5)
    assert house.base_z(2) == pytest.approx(5.0)
    assert house.total_height == pytest.approx(7.5)


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("width,depth", [(0, 8), (-3, 8), (10, 0), (10, -1)])
def test_non_positive_dimensions_rejected(width, depth):
    with pytest.raises(ValidationError):
        House.simple(width=width, depth=depth)


def test_room_outside_footprint_rejected():
    floor = Floor(level=0, rooms=[Room("bedroom", x=8, y=0, width=6, depth=4)])
    house = House(width=10, depth=8, floors=[floor])
    with pytest.raises(ValidationError, match="outside the house footprint"):
        house.validate()


def test_overlapping_rooms_rejected():
    floor = Floor(
        level=0,
        rooms=[Room("a", 0, 0, 6, 5), Room("b", 4, 0, 6, 5)],
    )
    house = House(width=10, depth=5, floors=[floor])
    with pytest.raises(ValidationError, match="overlap"):
        house.validate()


def test_touching_rooms_are_not_overlapping():
    """Sharing an edge is how adjacency works - it must stay legal."""
    floor = Floor(level=0, rooms=[Room("a", 0, 0, 6, 5), Room("b", 6, 0, 4, 5)])
    House(width=10, depth=5, floors=[floor]).validate()


def test_duplicate_room_names_rejected():
    floor = Floor(level=0, rooms=[Room("a", 0, 0, 4, 4), Room("a", 4, 0, 4, 4)])
    with pytest.raises(ValidationError, match="duplicate room name"):
        House(width=8, depth=4, floors=[floor]).validate()


def test_house_without_floors_rejected():
    with pytest.raises(ValidationError, match="no floors"):
        House(width=10, depth=8, floors=[]).validate()


def test_unsupported_roof_type_rejected():
    house = House.simple(width=10, depth=8)
    house.roof = Roof(type="hip")
    with pytest.raises(ValidationError, match="not supported yet"):
        house.validate()


@pytest.mark.parametrize("pitch", [0, -10, 90, 120])
def test_impossible_roof_pitch_rejected(pitch):
    house = House.simple(width=10, depth=8)
    house.roof.pitch = pitch
    with pytest.raises(ValidationError, match="pitch"):
        house.validate()


# ---------------------------------------------------------------------------
# openings
# ---------------------------------------------------------------------------


def test_opening_on_unknown_wall_rejected():
    house = House.simple(width=10, depth=8)
    house.floor(0).windows.append(Window(wall="L0_nope:north"))
    with pytest.raises(ValidationError, match="unknown wall"):
        house.validate()


def test_opening_wider_than_wall_rejected():
    house = House.simple(width=10, depth=8)
    house.floor(0).windows.append(
        Window(wall="L0_main:west", position=0.5, width=20.0)
    )
    with pytest.raises(ValidationError, match="sticks out of the wall"):
        house.validate()


def test_opening_at_wall_end_rejected():
    """position=1.0 with a finite width must overflow the wall end."""
    house = House.simple(width=10, depth=8)
    house.floor(0).windows.append(Window(wall="L0_main:west", position=1.0, width=1.4))
    with pytest.raises(ValidationError, match="sticks out"):
        house.validate()


def test_opening_taller_than_wall_rejected():
    house = House.simple(width=10, depth=8, height=2.8)
    house.floor(0).windows.append(
        Window(wall="L0_main:west", position=0.5, height=3.0, sill=0.5)
    )
    with pytest.raises(ValidationError, match="taller than the wall"):
        house.validate()


def test_door_with_nonzero_sill_rejected():
    with pytest.raises(ValidationError, match="sit on the floor"):
        Door(wall="L0_main:south", sill=0.5).validate()


def test_overlapping_openings_on_same_wall_rejected():
    house = House.simple(width=10, depth=8)
    ground = house.floor(0)
    ground.windows.append(Window(wall="L0_main:west", position=0.5, width=1.4))
    ground.windows.append(Window(wall="L0_main:west", position=0.55, width=1.4))
    with pytest.raises(ValidationError, match="[Oo]verlapping openings"):
        house.validate()


@pytest.mark.parametrize("position", [-0.1, 1.5])
def test_position_outside_unit_range_rejected(position):
    with pytest.raises(ValidationError, match=r"position must be in \[0, 1\]"):
        Window(wall="L0_main:west", position=position).validate()


def test_normalised_position_survives_resize():
    """README section 11: the opening keeps its place when the wall changes."""
    house = House.simple(width=10, depth=8)
    wall_id = "L0_main:south"
    window = Window(wall=wall_id, position=0.25, width=1.4)
    house.floor(0).windows.append(window)
    house.validate()

    before = house.floor(0).wall_map()[wall_id]
    centre_before = window.span(before.length)
    assert sum(centre_before) / 2 == pytest.approx(2.5)  # 25% of 10 m

    house.resize(20, 16)
    house.validate()
    after = house.floor(0).wall_map()[wall_id]
    assert after.length == pytest.approx(20.0)
    centre_after = window.span(after.length)
    # still a quarter along the wall, in absolute terms twice as far
    assert sum(centre_after) / 2 == pytest.approx(5.0)
    assert window.position == 0.25


# ---------------------------------------------------------------------------
# roof maths
# ---------------------------------------------------------------------------


def test_roof_height_is_function_of_pitch():
    house = House.simple(width=10, depth=8)
    # ridge runs along the longer side (x), so it spans the depth (8 m)
    assert house.roof.resolved_ridge_axis(10, 8) == "x"
    for pitch in (15.0, 35.0, 55.0):
        house.roof.pitch = pitch
        expected = 4.0 * math.tan(math.radians(pitch))
        assert house.roof_height() == pytest.approx(expected)


def test_steeper_pitch_is_strictly_taller():
    house = House.simple(width=10, depth=8)
    heights = []
    for pitch in (20.0, 35.0, 50.0, 65.0):
        house.roof.pitch = pitch
        heights.append(house.roof_height())
    assert heights == sorted(heights)
    assert len(set(heights)) == len(heights)


def test_ridge_axis_auto_follows_longer_side():
    assert Roof().resolved_ridge_axis(12, 8) == "x"
    assert Roof().resolved_ridge_axis(8, 12) == "y"
    assert Roof(ridge_axis="y").resolved_ridge_axis(12, 8) == "y"


def test_overhang_does_not_raise_the_ridge():
    """The overhang extends the slope outward/downward, it must not lift the ridge."""
    a = Roof(pitch=35, overhang=0.0).height_for(10, 8)
    b = Roof(pitch=35, overhang=1.5).height_for(10, 8)
    assert a == pytest.approx(b)
    # but it does make the slope run longer and hang lower
    assert Roof(pitch=35, overhang=1.5).slope_run(10, 8) > Roof(
        pitch=35, overhang=0.0
    ).slope_run(10, 8)
    assert Roof(pitch=35, overhang=1.5).eave_drop() > 0


# ---------------------------------------------------------------------------
# serialisation
# ---------------------------------------------------------------------------


def test_json_round_trip_is_stable():
    house = House.simple(width=12, depth=9, floors=2, pitch=42)
    once = House.from_dict(house.to_dict())
    twice = House.from_dict(once.to_dict())
    assert house.to_dict() == once.to_dict() == twice.to_dict()


def test_round_trip_preserves_openings():
    house = House.simple(width=10, depth=8)
    reloaded = House.from_json(house.to_json())
    original = house.floor(0)
    restored = reloaded.floor(0)
    assert len(restored.doors) == len(original.doors)
    assert len(restored.windows) == len(original.windows)
    assert restored.doors[0].wall == original.doors[0].wall
    assert restored.windows[0].position == original.windows[0].position


def test_round_trip_preserves_derived_walls():
    floor = Floor(level=0, rooms=[Room("a", 0, 0, 6, 5), Room("b", 6, 0, 4, 5)])
    house = House(name="t", width=10, depth=5, floors=[floor])
    house.validate()
    reloaded = House.from_json(house.to_json())
    assert [w.id for w in reloaded.all_walls()] == [w.id for w in house.all_walls()]


def test_minimal_readme_json_form_is_accepted():
    """README section 3 shows a reduced {"house": ..., "rooms": [...]} form."""
    data = {
        "house": {"width": 12, "depth": 10, "floors": 2},
        "rooms": [{"name": "living_room", "width": 6, "depth": 5}],
    }
    house = House.from_dict(data)
    assert house.width == 12
    assert house.floors


def test_future_schema_version_rejected():
    house = House.simple()
    data = house.to_dict()
    data["schema_version"] = 999
    with pytest.raises(ValidationError, match="unsupported schema_version"):
        House.from_dict(data)


def test_save_and_load_file(tmp_path):
    house = House.simple(width=11, depth=7, pitch=40)
    path = tmp_path / "h.json"
    house.save(str(path))
    assert House.load(str(path)).to_dict() == house.to_dict()


# ---------------------------------------------------------------------------
# shipped examples
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename", ["small_house.json", "cottage.json", "medieval_house.json"]
)
def test_example_files_are_valid(filename):
    house = House.load(os.path.join(EXAMPLES, filename))
    house.validate()
    assert house.all_walls()
    assert House.from_dict(house.to_dict()).to_dict() == house.to_dict()


def test_cottage_matches_readme_success_criterion():
    """README section 27: 12 x 10 m, salon + cocina, gable roof, 3+ windows."""
    house = House.load(os.path.join(EXAMPLES, "cottage.json"))
    assert (house.width, house.depth) == (12.0, 10.0)
    names = {room.name for floor in house.floors for room in floor.rooms}
    assert {"salon", "cocina"} <= names
    assert house.roof.type == "gable"
    assert sum(len(floor.windows) for floor in house.floors) >= 3


def test_resize_keeps_model_valid_and_regenerable():
    """README section 26 'segundo paso': resize and everything still works."""
    house = House.load(os.path.join(EXAMPLES, "cottage.json"))
    before = [w.id for w in house.all_walls()]
    house.resize(18, 15)
    house.validate()
    after = [w.id for w in house.all_walls()]
    # same topology, new dimensions
    assert before == after
    assert house.area == pytest.approx(120.0 * (18 / 12) * (15 / 10))
