"""Stylized material palette (README section 13).

Milestone 1 keeps every material a single flat-ish Principled BSDF so the
render reads like a diorama without depending on textures. Procedural
variation (stone joints, wood grain, tile noise) is Milestone 2.
"""

from .palette import PALETTE, MaterialSpec, get_or_create, get_palette, reset_cache

__all__ = ["PALETTE", "MaterialSpec", "get_or_create", "get_palette", "reset_cache"]
