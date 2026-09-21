"""Parametric house model (pure Python, no bpy).

Import surface kept small on purpose - this is the contract the generator,
the CLI, the tests and (later) MCP all talk to.
"""

from .house import (
    Door,
    Floor,
    House,
    Roof,
    Room,
    ValidationError,
    Wall,
    Window,
)

__all__ = [
    "Door",
    "Floor",
    "House",
    "Roof",
    "Room",
    "ValidationError",
    "Wall",
    "Window",
]
