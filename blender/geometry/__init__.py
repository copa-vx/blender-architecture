"""Blender-side generators: model -> mesh objects.

Nothing in here holds state. Every generator takes plain model objects and a
target collection, and returns the created object(s). That keeps the
"regenerate from the model" path (see :mod:`blender.geometry.generator`) a
simple clear-and-rebuild.
"""

from . import common, door, generator, roof, room, wall, window  # noqa: F401

__all__ = ["common", "door", "generator", "roof", "room", "wall", "window"]
