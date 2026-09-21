"""Basic environment: ground + a few trees.

Milestone 1 scope only. Procedural terrain with paths, rocks and a full
vegetation ruleset is Milestone 2 (README sections 14-15).
"""

from . import terrain, vegetation  # noqa: F401

__all__ = ["terrain", "vegetation"]
