"""Run by Blender before build_house.py (--python render_progress.py --python build_house.py).

Blender 5.x prints no line for each sample in --background mode, so this prints the render
statistics ("... | Sample 12/24") for service/app/render.py to read. The handler is
persistent: build_house.py loads the factory settings, which drops the other handlers.
"""

import sys

import bpy
from bpy.app.handlers import persistent


@persistent
def _stats(text, *args):
    print("[progress] %s" % text, flush=True)
    sys.stdout.flush()


bpy.app.handlers.render_stats.append(_stats)
