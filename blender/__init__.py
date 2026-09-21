"""AI GLADE - procedural house builder for Blender.

This package is intentionally split in two halves:

* ``blender.model``  - pure Python, **no** ``bpy`` import. It is the parametric
  description of the house and can be unit tested with plain pytest.
* everything else (``geometry``, ``materials``, ``environment``, ``addon``) -
  the Blender side that turns the model into scene objects.

See README.md section 3: "La casa no sera una simple malla".
"""

__version__ = "0.1.0"
