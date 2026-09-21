"""Tests for rooms and the room -> wall derivation. No Blender required.

    python3 -m pytest tests/test_rooms.py -v
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from blender.model.house import (  # noqa: E402
    Floor,
    House,
    Room,
    ValidationError,
    Window,
)


def make_floor(*rooms: Room, **kwargs) -> Floor:
    return Floor(level=kwargs.pop("level", 0), rooms=list(rooms), **kwargs)


# ---------------------------------------------------------------------------
# room basics
# ---------------------------------------------------------------------------


def test_room_area_and_bounds():
    room = Room("living_room", x=1, y=2, width=6, depth=5)
    assert room.area == 30
    assert room.bounds == (1, 2, 7, 7)
    assert room.centre == (4.0, 4.5)


def test_room_rejects_non_positive_size():
    for bad in (Room("a", 0, 0, 0, 5), Room("a", 0, 0, 5, -2)):
        with pytest.raises(ValidationError):
            bad.validate()


def test_room_rejects_empty_name():
    with pytest.raises(ValidationError):
        Room("  ", 0, 0, 4, 4).validate()


def test_room_too_small_for_its_walls_rejected():
    floor = make_floor(Room("closet", 0, 0, 0.4, 4), wall_thickness=0.25)
    with pytest.raises(ValidationError, match="too small for wall thickness"):
        floor.validate()


def test_overlap_detection():
    a = Room("a", 0, 0, 6, 5)
    assert a.overlaps(Room("b", 3, 0, 6, 5))
    assert not a.overlaps(Room("b", 6, 0, 6, 5))   # edge-to-edge
    assert not a.overlaps(Room("b", 10, 10, 2, 2))


# ---------------------------------------------------------------------------
# wall derivation (README section 10)
# ---------------------------------------------------------------------------


def test_single_room_yields_four_walls():
    floor = make_floor(Room("main", 0, 0, 6, 5))
    walls = floor.walls()
    assert len(walls) == 4
    assert all(wall.exterior for wall in walls)
    assert {round(w.length, 3) for w in walls} == {6.0, 5.0}


def test_wall_ids_are_stable_and_named_after_room_and_side():
    floor = make_floor(Room("main", 0, 0, 6, 5))
    ids = {wall.id for wall in floor.walls()}
    assert ids == {
        "L0_main:south",
        "L0_main:north",
        "L0_main:west",
        "L0_main:east",
    }
    # deriving twice gives the same ids - this is what openings rely on
    assert [w.id for w in floor.walls()] == [w.id for w in floor.walls()]


def test_wall_ids_carry_the_floor_level():
    floor = make_floor(Room("solar", 0, 0, 6, 5), level=2)
    assert all(wall.id.startswith("L2_") for wall in floor.walls())


def test_two_adjacent_rooms_share_one_wall():
    """Section 10: the wall between two rooms must be generated ONCE."""
    floor = make_floor(Room("living", 0, 0, 6, 5), Room("kitchen", 6, 0, 4, 5))
    walls = floor.walls()
    # 4 + 4 = 8 edges, but the shared one is deduplicated -> 7
    assert len(walls) == 7
    shared = [wall for wall in walls if not wall.exterior]
    assert len(shared) == 1
    assert set(shared[0].rooms) == {"living", "kitchen"}
    assert shared[0].start == (6.0, 0.0)
    assert shared[0].end == (6.0, 5.0)


def test_shared_wall_is_not_duplicated_in_the_object_list():
    floor = make_floor(Room("a", 0, 0, 4, 4), Room("b", 4, 0, 4, 4))
    positions = [(wall.start, wall.end) for wall in floor.walls()]
    assert len(positions) == len(set(positions))


def test_three_rooms_readme_layout():
    """The ASCII layout in section 10: two rooms on top, one wide below."""
    floor = make_floor(
        Room("salon", 0, 4, 7, 4),
        Room("cocina", 7, 4, 5, 4),
        Room("dormitorio", 0, 0, 12, 4),
    )
    floor.validate()
    walls = floor.walls()
    shared = [wall for wall in walls if not wall.exterior]
    # salon|cocina vertical, plus dormitorio's top edge split under both rooms
    assert len(shared) == 3
    for wall in shared:
        assert len(wall.rooms) == 2


def test_partially_overlapping_edge_is_split_into_segments():
    """A small room against a big one splits the big room's wall in two."""
    floor = make_floor(Room("big", 0, 0, 10, 6), Room("small", 10, 0, 4, 3))
    walls = floor.walls()
    east_side = [
        wall
        for wall in walls
        if wall.start[0] == 10.0 and wall.end[0] == 10.0
    ]
    # the big room's east edge becomes: shared bottom half + exterior top half
    assert len(east_side) == 2
    shared = [wall for wall in east_side if not wall.exterior]
    exterior = [wall for wall in east_side if wall.exterior]
    assert len(shared) == 1 and len(exterior) == 1
    assert shared[0].length == pytest.approx(3.0)
    assert exterior[0].length == pytest.approx(3.0)


def test_split_segments_get_unique_ids():
    floor = make_floor(Room("big", 0, 0, 10, 6), Room("small", 10, 0, 4, 3))
    ids = [wall.id for wall in floor.walls()]
    assert len(ids) == len(set(ids))


def test_wall_geometry_properties():
    floor = make_floor(Room("main", 0, 0, 6, 5))
    walls = floor.wall_map()
    south = walls["L0_main:south"]
    assert south.length == pytest.approx(6.0)
    assert south.angle == pytest.approx(0.0)
    assert south.centre == (3.0, 0.0)
    west = walls["L0_main:west"]
    assert west.length == pytest.approx(5.0)
    assert west.angle == pytest.approx(1.5707963, abs=1e-5)


def test_wall_inherits_floor_height_and_thickness():
    floor = make_floor(Room("main", 0, 0, 6, 5), height=3.2, wall_thickness=0.4)
    for wall in floor.walls():
        assert wall.height == pytest.approx(3.2)
        assert wall.thickness == pytest.approx(0.4)


def test_walls_sit_on_their_storey():
    house = House.simple(width=8, depth=6, floors=2, height=2.5)
    upper = [wall for wall in house.all_walls() if wall.level == 1]
    assert upper
    assert all(wall.base_z == pytest.approx(2.5) for wall in upper)


# ---------------------------------------------------------------------------
# rooms + openings together
# ---------------------------------------------------------------------------


def test_openings_resolve_against_derived_walls():
    floor = make_floor(Room("salon", 0, 0, 6, 5), Room("cocina", 6, 0, 4, 5))
    floor.windows.append(Window(wall="L0_salon:south", position=0.5))
    house = House(name="t", width=10, depth=5, floors=[floor])
    house.validate()
    assert floor.openings_for("L0_salon:south")
    assert not floor.openings_for("L0_cocina:north")


def test_window_on_shared_interior_wall_is_allowed():
    """An interior window (serving hatch) is geometrically legal."""
    floor = make_floor(Room("salon", 0, 0, 6, 5), Room("cocina", 6, 0, 4, 5))
    shared = next(wall for wall in floor.walls() if not wall.exterior)
    floor.windows.append(Window(wall=shared.id, position=0.5, width=1.0))
    House(name="t", width=10, depth=5, floors=[floor]).validate()


def test_floor_area_sums_rooms():
    floor = make_floor(Room("a", 0, 0, 6, 5), Room("b", 6, 0, 4, 5))
    assert floor.area == pytest.approx(50.0)


def test_floor_bounds_span_all_rooms():
    floor = make_floor(Room("a", 0, 0, 6, 5), Room("b", 6, 2, 4, 6))
    assert floor.bounds() == (0.0, 0.0, 10.0, 8.0)


def test_empty_floor_rejected():
    with pytest.raises(ValidationError, match="no rooms"):
        Floor(level=0, rooms=[]).validate()


def test_room_lookup_by_name():
    floor = make_floor(Room("salon", 0, 0, 6, 5))
    assert floor.room("salon").width == 6
    with pytest.raises(KeyError):
        floor.room("nope")
