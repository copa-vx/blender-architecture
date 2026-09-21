#!/usr/bin/env python3
"""Headless house builder.

    blender --background --python build_house.py -- examples/small_house.json \
        --out out/small_house.blend --render out/small_house.png

Loads a house JSON, generates the geometry, optionally saves a .blend and
renders a preview. Everything after ``--`` is parsed by this script; Blender
ignores it.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

# Make the repo importable no matter where Blender was launched from.
REPO = os.path.dirname(os.path.abspath(__file__))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import bpy  # noqa: E402

from blender.geometry import common, generator  # noqa: E402
from blender.model import House, ValidationError  # noqa: E402


def parse_args(argv=None):
    argv = argv if argv is not None else sys.argv
    args = argv[argv.index("--") + 1 :] if "--" in argv else []

    parser = argparse.ArgumentParser(prog="build_house.py")
    parser.add_argument("model", help="path to a house JSON file")
    parser.add_argument("--out", help="save the result as a .blend here")
    parser.add_argument("--render", help="render a preview PNG here")
    parser.add_argument(
        "--engine",
        default="EEVEE",
        help=(
            "render engine: EEVEE (auto-detects the right identifier for this "
            "Blender version), WORKBENCH, CYCLES, or a raw identifier"
        ),
    )
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=960)
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument(
        "--camera-angle",
        type=float,
        default=30.0,
        help="camera elevation in degrees (diorama 3/4 view)",
    )
    parser.add_argument(
        "--no-environment",
        action="store_true",
        help="skip terrain and vegetation",
    )
    parser.add_argument(
        "--resize",
        nargs=2,
        type=float,
        metavar=("WIDTH", "DEPTH"),
        help="resize the house before generating (proves regeneration)",
    )
    return parser.parse_args(args)


#: EEVEE's identifier moved around: BLENDER_EEVEE (<=4.1), BLENDER_EEVEE_NEXT
#: (4.2-4.5), BLENDER_EEVEE again in 5.x. Try them all rather than assume.
ENGINE_ALIASES = {
    "EEVEE": ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"),
    "WORKBENCH": ("BLENDER_WORKBENCH",),
    "CYCLES": ("CYCLES",),
}


def set_engine(scene, engine: str, samples: int) -> str:
    """Set the render engine, falling back to Workbench if unavailable."""
    available = {
        item.identifier
        for item in scene.bl_rna.properties["render"].fixed_type.bl_rna.properties[
            "engine"
        ].enum_items
    }
    candidates = ENGINE_ALIASES.get(engine.upper(), (engine,))
    chosen = next((name for name in candidates if name in available), None)
    if chosen is None:
        print(
            f"[build_house] engine {engine} not available "
            f"(tried {list(candidates)}); options: {sorted(available)}"
        )
        chosen = "BLENDER_WORKBENCH"
    engine = chosen
    scene.render.engine = engine

    if engine.startswith("BLENDER_EEVEE"):
        eevee = scene.eevee
        for attr in ("taa_render_samples", "taa_samples"):
            if hasattr(eevee, attr):
                setattr(eevee, attr, samples)
    elif engine == "CYCLES":
        scene.cycles.samples = samples
    return engine


def main() -> int:
    args = parse_args()
    started = time.time()

    model_path = args.model
    if not os.path.isabs(model_path):
        model_path = os.path.join(REPO, model_path)
    if not os.path.exists(model_path):
        print(f"[build_house] ERROR: no such model file: {model_path}")
        return 2

    # Start from a genuinely empty scene so object counts are meaningful.
    bpy.ops.wm.read_factory_settings(use_empty=True)

    try:
        house = House.load(model_path)
        if args.resize:
            house.resize(args.resize[0], args.resize[1])
        house.validate()
    except ValidationError as exc:
        print(f"[build_house] INVALID MODEL: {exc}")
        return 3

    print(f"[build_house] {house.summary()}")

    scene = bpy.context.scene
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False

    created = generator.generate_house(
        house, scene=scene, environment=not args.no_environment
    )
    for kind, objects in created.items():
        print(f"[build_house]   {kind:12s} {len(objects):4d} object(s)")
    print(f"[build_house]   {'TOTAL':12s} {len(bpy.data.objects):4d} object(s)")

    rig = generator.setup_camera_and_light(house, scene=scene, angle_deg=args.camera_angle)
    print(
        f"[build_house] camera at "
        f"({rig['camera'].location.x:.2f}, {rig['camera'].location.y:.2f}, "
        f"{rig['camera'].location.z:.2f})"
    )

    if args.out:
        out = args.out if os.path.isabs(args.out) else os.path.join(REPO, args.out)
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=out)
        print(f"[build_house] saved {out}")

    if args.render:
        png = args.render if os.path.isabs(args.render) else os.path.join(REPO, args.render)
        os.makedirs(os.path.dirname(png) or ".", exist_ok=True)
        engine = set_engine(scene, args.engine, args.samples)
        scene.render.filepath = png
        scene.render.image_settings.file_format = "PNG"
        print(f"[build_house] rendering with {engine} -> {png}")
        bpy.ops.render.render(write_still=True)
        if os.path.exists(png):
            print(f"[build_house] wrote {png} ({os.path.getsize(png)} bytes)")
        else:
            print(f"[build_house] ERROR: render produced no file at {png}")
            return 4

    print(f"[build_house] done in {time.time() - started:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
