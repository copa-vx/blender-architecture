"""The parametric house model.

IMPORTANT: this module must never import ``bpy``. It is the single source of
truth for "what the house is"; the Blender generator is only a renderer of
this data. That is what makes the house regenerable (README section 3) and
unit-testable outside Blender.

Coordinate system
-----------------
* ``x`` grows east, ``y`` grows north, ``z`` grows up (Blender convention).
* The house footprint lives in ``[0, width] x [0, depth]``.
* Rooms are axis-aligned rectangles placed on that footprint. This is the
  simplest reading of README section 10 ("habitaciones rectangulares") and is
  what Milestone 1 implements.

Walls are NOT authored by the user: they are *derived* from the rooms
(see :meth:`Floor.walls`). Openings (doors / windows) reference a wall by id
plus a normalised position in ``[0, 1]`` so they survive a wall resize
(README section 11).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Iterable, List, Sequence, Tuple

EPS = 1e-6
#: Coordinates are snapped to this many decimals before being used as dict
#: keys, so that 3.0000000001 and 2.9999999999 are the same wall line.
_ROUND = 5

SCHEMA_VERSION = 1


class ValidationError(ValueError):
    """Raised when a house model is geometrically or semantically invalid."""


def _round(value: float) -> float:
    return round(float(value), _ROUND)


def _require_positive(value: float, label: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValidationError(f"{label} must be a finite number, got {value!r}")
    if value <= 0:
        raise ValidationError(f"{label} must be > 0, got {value}")
    return value


# ---------------------------------------------------------------------------
# Openings
# ---------------------------------------------------------------------------


@dataclass
class Opening:
    """Base class for doors and windows.

    ``position`` is normalised along the wall (0 = start, 1 = end), so moving
    or resizing the wall keeps the opening proportionally in place.
    ``sill`` is the height of the bottom edge above the floor.
    """

    wall: str
    position: float = 0.5
    width: float = 1.0
    height: float = 1.2
    sill: float = 0.9

    kind: str = field(default="opening", init=False, repr=False)

    def validate(self) -> None:
        if not isinstance(self.wall, str) or not self.wall:
            raise ValidationError(f"{self.kind}: 'wall' must be a non-empty wall id")
        _require_positive(self.width, f"{self.kind} '{self.wall}' width")
        _require_positive(self.height, f"{self.kind} '{self.wall}' height")
        if not (0.0 <= float(self.position) <= 1.0):
            raise ValidationError(
                f"{self.kind} on wall '{self.wall}': position must be in [0, 1], "
                f"got {self.position}"
            )
        if float(self.sill) < -EPS:
            raise ValidationError(
                f"{self.kind} on wall '{self.wall}': sill must be >= 0, got {self.sill}"
            )

    # -- geometry helpers ---------------------------------------------------
    def span(self, wall_length: float) -> Tuple[float, float]:
        """Return ``(u_min, u_max)`` of the opening along the wall, in metres."""
        centre = float(self.position) * wall_length
        half = float(self.width) / 2.0
        return centre - half, centre + half

    def z_span(self) -> Tuple[float, float]:
        return float(self.sill), float(self.sill) + float(self.height)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.kind,
            "wall": self.wall,
            "position": _round(self.position),
            "width": _round(self.width),
            "height": _round(self.height),
            "sill": _round(self.sill),
        }


@dataclass
class Window(Opening):
    width: float = 1.4
    height: float = 1.2
    sill: float = 0.9
    kind: str = field(default="window", init=False, repr=False)


@dataclass
class Door(Opening):
    width: float = 0.9
    height: float = 2.1
    #: Doors always start at floor level; the field is kept so that Door and
    #: Window share one code path in the generator.
    sill: float = 0.0
    kind: str = field(default="door", init=False, repr=False)

    def validate(self) -> None:
        super().validate()
        if abs(float(self.sill)) > EPS:
            raise ValidationError(
                f"door on wall '{self.wall}': doors must sit on the floor (sill=0), "
                f"got {self.sill}"
            )


# ---------------------------------------------------------------------------
# Wall (derived, never authored directly)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Wall:
    """A single straight wall segment.

    Instances are produced by :meth:`Floor.walls`; they are a *view* over the
    room layout, not user data, and therefore are never serialised.
    """

    id: str
    start: Tuple[float, float]
    end: Tuple[float, float]
    height: float
    thickness: float
    level: int = 0
    base_z: float = 0.0
    #: Names of the rooms that own this wall. 2 owners => interior wall shared
    #: by two rooms (deduplicated), 1 owner => exterior wall.
    rooms: Tuple[str, ...] = ()

    @property
    def exterior(self) -> bool:
        return len(self.rooms) < 2

    @property
    def length(self) -> float:
        dx = self.end[0] - self.start[0]
        dy = self.end[1] - self.start[1]
        return math.hypot(dx, dy)

    @property
    def angle(self) -> float:
        """Rotation around Z, in radians, of the wall's local +X axis."""
        return math.atan2(self.end[1] - self.start[1], self.end[0] - self.start[0])

    @property
    def centre(self) -> Tuple[float, float]:
        return (
            (self.start[0] + self.end[0]) / 2.0,
            (self.start[1] + self.end[1]) / 2.0,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "start": [_round(self.start[0]), _round(self.start[1])],
            "end": [_round(self.end[0]), _round(self.end[1])],
            "height": _round(self.height),
            "thickness": _round(self.thickness),
            "level": self.level,
            "exterior": self.exterior,
            "rooms": list(self.rooms),
        }


# ---------------------------------------------------------------------------
# Room
# ---------------------------------------------------------------------------


@dataclass
class Room:
    """An axis-aligned rectangular room on a floor."""

    name: str
    x: float = 0.0
    y: float = 0.0
    width: float = 4.0
    depth: float = 3.0

    def validate(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValidationError("room name must be a non-empty string")
        _require_positive(self.width, f"room '{self.name}' width")
        _require_positive(self.depth, f"room '{self.name}' depth")
        for label, value in (("x", self.x), ("y", self.y)):
            if not math.isfinite(float(value)):
                raise ValidationError(f"room '{self.name}' {label} must be finite")

    @property
    def area(self) -> float:
        return float(self.width) * float(self.depth)

    @property
    def bounds(self) -> Tuple[float, float, float, float]:
        """``(x_min, y_min, x_max, y_max)``."""
        return (
            float(self.x),
            float(self.y),
            float(self.x) + float(self.width),
            float(self.y) + float(self.depth),
        )

    @property
    def centre(self) -> Tuple[float, float]:
        x0, y0, x1, y1 = self.bounds
        return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)

    def overlaps(self, other: "Room") -> bool:
        ax0, ay0, ax1, ay1 = self.bounds
        bx0, by0, bx1, by1 = other.bounds
        return (
            min(ax1, bx1) - max(ax0, bx0) > EPS
            and min(ay1, by1) - max(ay0, by0) > EPS
        )

    # -- edges --------------------------------------------------------------
    def edges(self) -> List[Tuple[str, str, float, float, float]]:
        """Return the 4 edges as ``(side, orientation, fixed, a, b)``.

        ``orientation`` is ``"H"`` (runs along x, fixed y) or ``"V"``
        (runs along y, fixed x).
        """
        x0, y0, x1, y1 = self.bounds
        return [
            ("south", "H", y0, x0, x1),
            ("north", "H", y1, x0, x1),
            ("west", "V", x0, y0, y1),
            ("east", "V", x1, y0, y1),
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "x": _round(self.x),
            "y": _round(self.y),
            "width": _round(self.width),
            "depth": _round(self.depth),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Room":
        return cls(
            name=data["name"],
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            width=float(data.get("width", 4.0)),
            depth=float(data.get("depth", 3.0)),
        )


# ---------------------------------------------------------------------------
# Floor
# ---------------------------------------------------------------------------


@dataclass
class Floor:
    """One storey: a set of rooms plus the openings cut into its walls."""

    level: int = 0
    height: float = 2.8
    wall_thickness: float = 0.25
    rooms: List[Room] = field(default_factory=list)
    doors: List[Door] = field(default_factory=list)
    windows: List[Window] = field(default_factory=list)

    # -- basic validation ---------------------------------------------------
    def validate(self) -> None:
        _require_positive(self.height, f"floor {self.level} height")
        _require_positive(self.wall_thickness, f"floor {self.level} wall_thickness")
        if not self.rooms:
            raise ValidationError(f"floor {self.level} has no rooms")

        seen: set = set()
        for room in self.rooms:
            room.validate()
            if room.name in seen:
                raise ValidationError(
                    f"floor {self.level}: duplicate room name '{room.name}'"
                )
            seen.add(room.name)
            smallest = min(float(room.width), float(room.depth))
            if smallest <= float(self.wall_thickness) * 2:
                raise ValidationError(
                    f"room '{room.name}' ({room.width} x {room.depth}) is too small "
                    f"for wall thickness {self.wall_thickness}"
                )

        for i, a in enumerate(self.rooms):
            for b in self.rooms[i + 1 :]:
                if a.overlaps(b):
                    raise ValidationError(
                        f"floor {self.level}: rooms '{a.name}' and '{b.name}' overlap"
                    )

    @property
    def openings(self) -> List[Opening]:
        return [*self.doors, *self.windows]

    @property
    def area(self) -> float:
        return sum(room.area for room in self.rooms)

    def bounds(self) -> Tuple[float, float, float, float]:
        if not self.rooms:
            return (0.0, 0.0, 0.0, 0.0)
        xs0, ys0, xs1, ys1 = zip(*(room.bounds for room in self.rooms))
        return (min(xs0), min(ys0), max(xs1), max(ys1))

    def room(self, name: str) -> Room:
        for room in self.rooms:
            if room.name == name:
                return room
        raise KeyError(f"no room named '{name}' on floor {self.level}")

    # -- wall derivation ----------------------------------------------------
    def walls(self, base_z: float = 0.0) -> List[Wall]:
        """Derive the wall segments of this floor from its rooms.

        Algorithm (README section 10, "conexiones con otras habitaciones"):

        1. Every room contributes its 4 edges.
        2. Edges are grouped by (orientation, fixed coordinate) - i.e. all the
           edges that sit on the same infinite line.
        3. Inside a group, every segment is split at *all* endpoints found in
           that group. This turns partially overlapping edges (rooms of
           different sizes sharing part of a wall) into atomic intervals.
        4. Identical atomic intervals are merged: a single :class:`Wall` with
           two owner rooms. That is the shared-wall deduplication - two
           adjacent rooms produce ONE wall, not two touching walls.

        Wall ids are derived from the alphabetically-first owning room plus the
        side of that room, so they stay stable when the house is resized
        (which is what lets normalised opening positions survive - section 11).
        """
        # step 1 + 2
        groups: Dict[Tuple[str, float], List[Tuple[str, str, float, float]]] = {}
        for room in self.rooms:
            for side, orient, fixed, a, b in room.edges():
                key = (orient, _round(fixed))
                groups.setdefault(key, []).append((room.name, side, _round(a), _round(b)))

        atomic: Dict[Tuple[str, float, float, float], List[Tuple[str, str]]] = {}
        for (orient, fixed), segments in groups.items():
            breaks = sorted({value for _, _, a, b in segments for value in (a, b)})
            for room_name, side, a, b in segments:
                inner = [v for v in breaks if a - EPS <= v <= b + EPS]
                for lo, hi in zip(inner, inner[1:]):
                    if hi - lo <= EPS:
                        continue
                    # step 3 + 4: same key => same physical wall
                    atomic.setdefault((orient, fixed, lo, hi), []).append(
                        (room_name, side)
                    )

        walls: List[Wall] = []
        # Deterministic ordering so that regeneration is reproducible.
        for (orient, fixed, lo, hi) in sorted(atomic):
            owners = sorted(atomic[(orient, fixed, lo, hi)])
            primary_room, primary_side = owners[0]
            if orient == "H":
                start = (lo, fixed)
                end = (hi, fixed)
            else:
                start = (fixed, lo)
                end = (fixed, hi)
            walls.append(
                Wall(
                    id="",  # assigned below, needs the per-room ordering
                    start=start,
                    end=end,
                    height=float(self.height),
                    thickness=float(self.wall_thickness),
                    level=self.level,
                    base_z=float(base_z),
                    rooms=tuple(name for name, _ in owners),
                )
            )
            walls[-1] = replace(walls[-1], id=f"{primary_room}:{primary_side}")

        # Disambiguate: one room side may have been split into several atomic
        # walls by a neighbour. Append an index in that case (stable order).
        counts: Dict[str, int] = {}
        for wall in walls:
            counts[wall.id] = counts.get(wall.id, 0) + 1
        running: Dict[str, int] = {}
        final: List[Wall] = []
        for wall in walls:
            if counts[wall.id] > 1:
                index = running.get(wall.id, 0)
                running[wall.id] = index + 1
                final.append(replace(wall, id=f"L{self.level}_{wall.id}_{index}"))
            else:
                final.append(replace(wall, id=f"L{self.level}_{wall.id}"))
        return final

    def wall_map(self, base_z: float = 0.0) -> Dict[str, Wall]:
        return {wall.id: wall for wall in self.walls(base_z=base_z)}

    def openings_for(self, wall_id: str) -> List[Opening]:
        return [op for op in self.openings if op.wall == wall_id]

    # -- serialisation ------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "height": _round(self.height),
            "wall_thickness": _round(self.wall_thickness),
            "rooms": [room.to_dict() for room in self.rooms],
            "doors": [door.to_dict() for door in self.doors],
            "windows": [window.to_dict() for window in self.windows],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Floor":
        return cls(
            level=int(data.get("level", 0)),
            height=float(data.get("height", 2.8)),
            wall_thickness=float(data.get("wall_thickness", 0.25)),
            rooms=[Room.from_dict(item) for item in data.get("rooms", [])],
            doors=[
                Door(
                    wall=item["wall"],
                    position=float(item.get("position", 0.5)),
                    width=float(item.get("width", 0.9)),
                    height=float(item.get("height", 2.1)),
                    sill=float(item.get("sill", 0.0)),
                )
                for item in data.get("doors", [])
            ],
            windows=[
                Window(
                    wall=item["wall"],
                    position=float(item.get("position", 0.5)),
                    width=float(item.get("width", 1.4)),
                    height=float(item.get("height", 1.2)),
                    sill=float(item.get("sill", 0.9)),
                )
                for item in data.get("windows", [])
            ],
        )


# ---------------------------------------------------------------------------
# Roof
# ---------------------------------------------------------------------------


@dataclass
class Roof:
    """Gable roof (README section 12, V1). Hip / flat / tower are Milestone 2+."""

    type: str = "gable"
    pitch: float = 35.0
    overhang: float = 0.5
    thickness: float = 0.15
    #: Axis the ridge runs along: ``"auto"`` picks the longer side of the
    #: footprint, which is what a real gable roof does.
    ridge_axis: str = "auto"
    material: str = "ROOF"

    SUPPORTED = ("gable",)

    def validate(self) -> None:
        if self.type not in self.SUPPORTED:
            raise ValidationError(
                f"roof type '{self.type}' is not supported yet "
                f"(Milestone 1 supports: {', '.join(self.SUPPORTED)})"
            )
        if not (0.0 < float(self.pitch) < 90.0):
            raise ValidationError(
                f"roof pitch must be in (0, 90) degrees, got {self.pitch}"
            )
        if float(self.overhang) < -EPS:
            raise ValidationError(f"roof overhang must be >= 0, got {self.overhang}")
        _require_positive(self.thickness, "roof thickness")
        if self.ridge_axis not in ("auto", "x", "y"):
            raise ValidationError(
                f"roof ridge_axis must be 'auto', 'x' or 'y', got {self.ridge_axis!r}"
            )

    def resolved_ridge_axis(self, width: float, depth: float) -> str:
        """Ridge runs along the longer footprint side when set to ``auto``."""
        if self.ridge_axis != "auto":
            return self.ridge_axis
        return "x" if float(width) >= float(depth) else "y"

    def span_for(self, width: float, depth: float) -> float:
        """Footprint side perpendicular to the ridge (the side the roof slopes down)."""
        axis = self.resolved_ridge_axis(width, depth)
        return float(depth) if axis == "x" else float(width)

    def height_for(self, width: float, depth: float) -> float:
        """Ridge height above the top of the walls.

        ``h = (span / 2) * tan(pitch)``.

        The roof plane is anchored at the wall top: rafters sit *on* the wall
        plate and continue outwards, so the overhang hangs BELOW the wall top
        (see :meth:`eave_drop`) instead of lifting the ridge. Folding the
        overhang into the ridge height would leave a triangular gap between
        the wall top and the roof at the gable ends.
        """
        span = self.span_for(width, depth)
        return (span / 2.0) * math.tan(math.radians(self.pitch))

    def eave_drop(self) -> float:
        """How far the overhang edge hangs below the wall top."""
        return float(self.overhang) * math.tan(math.radians(self.pitch))

    def slope_run(self, width: float, depth: float) -> float:
        """Horizontal run of one roof plane, ridge -> overhang edge."""
        return self.span_for(width, depth) / 2.0 + float(self.overhang)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "pitch": _round(self.pitch),
            "overhang": _round(self.overhang),
            "thickness": _round(self.thickness),
            "ridge_axis": self.ridge_axis,
            "material": self.material,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Roof":
        return cls(
            type=data.get("type", "gable"),
            pitch=float(data.get("pitch", 35.0)),
            overhang=float(data.get("overhang", 0.5)),
            thickness=float(data.get("thickness", 0.15)),
            ridge_axis=data.get("ridge_axis", "auto"),
            material=data.get("material", "ROOF"),
        )


# ---------------------------------------------------------------------------
# House
# ---------------------------------------------------------------------------


@dataclass
class House:
    """Top level parametric house.

    >>> house = House.simple(width=10, depth=8)
    >>> house.validate()
    >>> House.from_dict(house.to_dict()).to_dict() == house.to_dict()
    True
    """

    name: str = "house"
    width: float = 10.0
    depth: float = 8.0
    floors: List[Floor] = field(default_factory=list)
    roof: Roof = field(default_factory=Roof)
    style: str = "cottage"
    #: Optional Geometry-Nodes stone scatter on walls (off by default, see
    #: README section 9 - the full stone look is Phase 6 / Milestone 2).
    stone_walls: bool = False
    terrain_margin: float = 6.0
    tree_count: int = 6
    seed: int = 0

    # -- construction helpers ----------------------------------------------
    @classmethod
    def simple(
        cls,
        width: float = 10.0,
        depth: float = 8.0,
        floors: int = 1,
        height: float = 2.8,
        roof: str = "gable",
        pitch: float = 35.0,
        name: str = "house",
    ) -> "House":
        """``create_house({"width": 10, "depth": 8})`` from README section 7.

        Produces a one-room-per-floor house that fills the footprint, with a
        door on the south wall of the ground floor and a window on the north
        and east walls.
        """
        width = _require_positive(width, "house width")
        depth = _require_positive(depth, "house depth")
        if int(floors) < 1:
            raise ValidationError(f"house must have at least 1 floor, got {floors}")

        storeys: List[Floor] = []
        for level in range(int(floors)):
            room = Room(
                name="main" if level == 0 else f"upper_{level}",
                x=0.0,
                y=0.0,
                width=width,
                depth=depth,
            )
            storeys.append(Floor(level=level, height=height, rooms=[room]))

        house = cls(
            name=name,
            width=width,
            depth=depth,
            floors=storeys,
            roof=Roof(type=roof, pitch=pitch),
        )

        ground = storeys[0]
        wall_ids = {wall.id for wall in ground.walls()}
        south = f"L0_{ground.rooms[0].name}:south"
        north = f"L0_{ground.rooms[0].name}:north"
        east = f"L0_{ground.rooms[0].name}:east"
        if south in wall_ids:
            ground.doors.append(Door(wall=south, position=0.5))
        for wall_id in (north, east):
            if wall_id in wall_ids:
                ground.windows.append(Window(wall=wall_id, position=0.5))
        return house

    # -- derived ------------------------------------------------------------
    @property
    def total_height(self) -> float:
        """Top of the highest wall (eave line)."""
        return sum(float(floor.height) for floor in self.floors)

    @property
    def area(self) -> float:
        """Total built area over all floors, in m^2."""
        return sum(floor.area for floor in self.floors)

    def base_z(self, level: int) -> float:
        return sum(float(f.height) for f in self.floors if f.level < level)

    def floor(self, level: int) -> Floor:
        for storey in self.floors:
            if storey.level == level:
                return storey
        raise KeyError(f"no floor at level {level}")

    def all_walls(self) -> List[Wall]:
        walls: List[Wall] = []
        for storey in sorted(self.floors, key=lambda f: f.level):
            walls.extend(storey.walls(base_z=self.base_z(storey.level)))
        return walls

    def footprint(self) -> Tuple[float, float, float, float]:
        """Bounding box actually occupied by rooms (not the declared footprint)."""
        boxes = [floor.bounds() for floor in self.floors if floor.rooms]
        if not boxes:
            return (0.0, 0.0, float(self.width), float(self.depth))
        xs0, ys0, xs1, ys1 = zip(*boxes)
        return (min(xs0), min(ys0), max(xs1), max(ys1))

    def roof_height(self) -> float:
        x0, y0, x1, y1 = self.footprint()
        return self.roof.height_for(x1 - x0, y1 - y0)

    # -- validation ---------------------------------------------------------
    def validate(self) -> None:
        """Raise :class:`ValidationError` if the model could not be built."""
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValidationError("house name must be a non-empty string")
        _require_positive(self.width, "house width")
        _require_positive(self.depth, "house depth")
        if not self.floors:
            raise ValidationError("house has no floors")

        levels = [floor.level for floor in self.floors]
        if len(set(levels)) != len(levels):
            raise ValidationError(f"duplicate floor levels: {sorted(levels)}")

        self.roof.validate()

        for storey in self.floors:
            storey.validate()

            # rooms must stay inside the declared footprint
            for room in storey.rooms:
                x0, y0, x1, y1 = room.bounds
                if (
                    x0 < -EPS
                    or y0 < -EPS
                    or x1 > float(self.width) + EPS
                    or y1 > float(self.depth) + EPS
                ):
                    raise ValidationError(
                        f"room '{room.name}' ({x0}, {y0})-({x1}, {y1}) lies outside "
                        f"the house footprint {self.width} x {self.depth}"
                    )

            walls = storey.wall_map(base_z=self.base_z(storey.level))
            for opening in storey.openings:
                opening.validate()
                wall = walls.get(opening.wall)
                if wall is None:
                    raise ValidationError(
                        f"{opening.kind} references unknown wall '{opening.wall}'. "
                        f"Known walls on floor {storey.level}: "
                        f"{', '.join(sorted(walls)) or '(none)'}"
                    )
                u_min, u_max = opening.span(wall.length)
                if u_min < -EPS or u_max > wall.length + EPS:
                    raise ValidationError(
                        f"{opening.kind} on wall '{wall.id}' sticks out of the wall: "
                        f"span [{u_min:.3f}, {u_max:.3f}] vs length {wall.length:.3f}"
                    )
                z_min, z_max = opening.z_span()
                if z_max > float(storey.height) - EPS:
                    raise ValidationError(
                        f"{opening.kind} on wall '{wall.id}' is taller than the wall: "
                        f"top {z_max:.3f} vs height {storey.height:.3f}"
                    )

            # openings on the same wall must not overlap each other
            by_wall: Dict[str, List[Opening]] = {}
            for opening in storey.openings:
                by_wall.setdefault(opening.wall, []).append(opening)
            for wall_id, items in by_wall.items():
                wall = walls[wall_id]
                spans = sorted(item.span(wall.length) for item in items)
                for (_, a_max), (b_min, _) in zip(spans, spans[1:]):
                    if b_min < a_max - EPS:
                        raise ValidationError(
                            f"overlapping openings on wall '{wall_id}'"
                        )

    def is_valid(self) -> bool:
        try:
            self.validate()
        except ValidationError:
            return False
        return True

    # -- parametric edits (the point of the whole exercise) -----------------
    def resize(self, width: float, depth: float) -> "House":
        """Scale the whole layout to a new footprint, in place.

        Rooms keep their relative position/size, openings keep their normalised
        position, so the house regenerates coherently (README section 26,
        "segundo paso").
        """
        width = _require_positive(width, "house width")
        depth = _require_positive(depth, "house depth")
        fx = width / float(self.width)
        fy = depth / float(self.depth)
        for storey in self.floors:
            for room in storey.rooms:
                room.x = float(room.x) * fx
                room.y = float(room.y) * fy
                room.width = float(room.width) * fx
                room.depth = float(room.depth) * fy
        self.width = width
        self.depth = depth
        return self

    # -- serialisation ------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "house": {
                "name": self.name,
                "width": _round(self.width),
                "depth": _round(self.depth),
                "floors": len(self.floors),
                "style": self.style,
                "stone_walls": bool(self.stone_walls),
                "terrain_margin": _round(self.terrain_margin),
                "tree_count": int(self.tree_count),
                "seed": int(self.seed),
            },
            "floors": [floor.to_dict() for floor in self.floors],
            "roof": self.roof.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "House":
        if not isinstance(data, dict):
            raise ValidationError("house JSON must be an object")
        version = int(data.get("schema_version", SCHEMA_VERSION))
        if version > SCHEMA_VERSION:
            raise ValidationError(
                f"unsupported schema_version {version} (this build understands "
                f"up to {SCHEMA_VERSION})"
            )
        head = data.get("house", {})
        floors_data = data.get("floors")
        if floors_data is None:
            # Minimal form from README section 3: {"house": {...}, "rooms": [...]}
            rooms = [Room.from_dict(item) for item in data.get("rooms", [])]
            count = int(head.get("floors", 1))
            floors_data = [
                {"level": level, "rooms": [room.to_dict() for room in rooms] if level == 0 else []}
                for level in range(count)
            ]
            floors = [Floor.from_dict(item) for item in floors_data if item["rooms"]]
            if not floors:
                width = float(head.get("width", 10.0))
                depth = float(head.get("depth", 8.0))
                return cls.simple(width=width, depth=depth, floors=count)
        else:
            floors = [Floor.from_dict(item) for item in floors_data]

        return cls(
            name=head.get("name", "house"),
            width=float(head.get("width", 10.0)),
            depth=float(head.get("depth", 8.0)),
            floors=floors,
            roof=Roof.from_dict(data.get("roof", {})),
            style=head.get("style", "cottage"),
            stone_walls=bool(head.get("stone_walls", False)),
            terrain_margin=float(head.get("terrain_margin", 6.0)),
            tree_count=int(head.get("tree_count", 6)),
            seed=int(head.get("seed", 0)),
        )

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> "House":
        return cls.from_dict(json.loads(text))

    @classmethod
    def load(cls, path: str) -> "House":
        with open(path, "r", encoding="utf-8") as handle:
            return cls.from_dict(json.load(handle))

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(self.to_json())
            handle.write("\n")

    # -- misc ---------------------------------------------------------------
    def summary(self) -> str:
        walls = self.all_walls()
        openings = sum(len(floor.openings) for floor in self.floors)
        return (
            f"{self.name}: {self.width:g} x {self.depth:g} m, "
            f"{len(self.floors)} floor(s), {sum(len(f.rooms) for f in self.floors)} room(s), "
            f"{len(walls)} wall(s) ({sum(1 for w in walls if not w.exterior)} shared), "
            f"{openings} opening(s), {self.roof.type} roof at {self.roof.pitch:g} deg, "
            f"{self.area:.1f} m^2"
        )


def create_house(params: Dict[str, Any] | None = None, **kwargs: Any) -> House:
    """README section 7 entry point: ``create_house({"width": 10, "depth": 8})``."""
    merged: Dict[str, Any] = dict(params or {})
    merged.update(kwargs)
    house = House.simple(
        width=float(merged.get("width", 10.0)),
        depth=float(merged.get("depth", 8.0)),
        floors=int(merged.get("floors", 1)),
        height=float(merged.get("height", 2.8)),
        roof=str(merged.get("roof", "gable")),
        pitch=float(merged.get("pitch", 35.0)),
        name=str(merged.get("name", "house")),
    )
    house.validate()
    return house
