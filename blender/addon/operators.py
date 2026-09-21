"""Operators: Generate, Load JSON, Save JSON, Clear."""

from __future__ import annotations

import os
import traceback

import bpy
from bpy.props import StringProperty
from bpy.types import Operator

from ..geometry import common, generator
from ..model import House, ValidationError
from . import scene_manager


class AIG_OT_generate_house(Operator):
    bl_idname = "aig.generate_house"
    bl_label = "Generate House"
    bl_description = "Rebuild the house from the current parameters"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.aig_house
        try:
            # Prefer a model already stored on the scene (e.g. loaded from
            # JSON with rooms the panel cannot express); fall back to the
            # simple panel-driven house.
            stored = generator.load_model(context.scene)
            if stored is not None and _matches_panel(stored, props):
                house = stored
            else:
                house = scene_manager.props_to_model(props)
            house.validate()
            created = generator.generate_house(
                house, scene=context.scene, environment=props.environment
            )
        except ValidationError as exc:
            self.report({"ERROR"}, f"Invalid house: {exc}")
            return {"CANCELLED"}
        except Exception as exc:  # pragma: no cover - defensive
            traceback.print_exc()
            self.report({"ERROR"}, f"Generation failed: {exc}")
            return {"CANCELLED"}

        total = sum(len(items) for items in created.values())
        self.report({"INFO"}, f"{house.summary()} -> {total} objects")
        return {"FINISHED"}


def _matches_panel(house: House, props) -> bool:
    """True if the stored model still corresponds to the panel values.

    Lets the user tweak width/pitch in the panel and have it win, while a
    multi-room model loaded from JSON survives a plain re-Generate.
    """
    return (
        abs(float(house.width) - float(props.width)) < 1e-6
        and abs(float(house.depth) - float(props.depth)) < 1e-6
        and len(house.floors) == int(props.floors)
        and abs(float(house.roof.pitch) - float(props.roof_pitch)) < 1e-6
        and abs(float(house.roof.overhang) - float(props.roof_overhang)) < 1e-6
    )


class AIG_OT_load_json(Operator):
    bl_idname = "aig.load_json"
    bl_label = "Load JSON"
    bl_description = "Load a house model from a JSON file and generate it"
    bl_options = {"REGISTER", "UNDO"}

    filepath: StringProperty(subtype="FILE_PATH")

    def execute(self, context):
        props = context.scene.aig_house
        path = bpy.path.abspath(self.filepath or props.json_path)
        if not path or not os.path.exists(path):
            self.report({"ERROR"}, f"No such file: {path or '(empty)'}")
            return {"CANCELLED"}
        try:
            house = House.load(path)
            house.validate()
        except (ValidationError, ValueError, OSError) as exc:
            self.report({"ERROR"}, f"Could not load {os.path.basename(path)}: {exc}")
            return {"CANCELLED"}

        props.json_path = path
        scene_manager.model_to_props(house, props)
        generator.generate_house(
            house, scene=context.scene, environment=props.environment
        )
        self.report({"INFO"}, f"Loaded {os.path.basename(path)}: {house.summary()}")
        return {"FINISHED"}

    def invoke(self, context, event):  # pragma: no cover - needs a window
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class AIG_OT_save_json(Operator):
    bl_idname = "aig.save_json"
    bl_label = "Save JSON"
    bl_description = "Write the current house model to a JSON file"
    bl_options = {"REGISTER"}

    filepath: StringProperty(subtype="FILE_PATH")

    def execute(self, context):
        props = context.scene.aig_house
        path = bpy.path.abspath(self.filepath or props.json_path)
        if not path:
            self.report({"ERROR"}, "Set a JSON path first")
            return {"CANCELLED"}
        if not path.lower().endswith(".json"):
            path += ".json"

        house = generator.load_model(context.scene)
        if house is None:
            house = scene_manager.props_to_model(props)
        try:
            house.validate()
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            house.save(path)
        except (ValidationError, OSError) as exc:
            self.report({"ERROR"}, f"Could not save: {exc}")
            return {"CANCELLED"}

        props.json_path = path
        self.report({"INFO"}, f"Saved {path}")
        return {"FINISHED"}

    def invoke(self, context, event):  # pragma: no cover - needs a window
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class AIG_OT_clear_house(Operator):
    bl_idname = "aig.clear_house"
    bl_label = "Clear"
    bl_description = "Delete every generated object"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        removed = common.clear_house(context.scene)
        context.scene.pop(generator.SCENE_KEY, None)
        self.report({"INFO"}, f"Removed {removed} object(s)")
        return {"FINISHED"}


_CLASSES = (
    AIG_OT_generate_house,
    AIG_OT_load_json,
    AIG_OT_save_json,
    AIG_OT_clear_house,
)


def register() -> None:
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
