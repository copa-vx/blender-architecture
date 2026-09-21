"""N-panel in the 3D viewport sidebar (README section 22 mockup)."""

from __future__ import annotations

import bpy
from bpy.types import Panel


class AIG_PT_base:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI GLADE"


class AIG_PT_house(AIG_PT_base, Panel):
    bl_idname = "AIG_PT_house"
    bl_label = "AI GLADE"

    def draw(self, context):
        layout = self.layout
        props = context.scene.aig_house

        col = layout.column(align=True)
        col.prop(props, "name")

        box = layout.box()
        box.label(text="House", icon="HOME")
        grid = box.column(align=True)
        grid.prop(props, "width")
        grid.prop(props, "depth")
        grid.prop(props, "floors")
        grid.prop(props, "floor_height")
        grid.prop(props, "wall_thickness")

        box = layout.box()
        box.label(text="Roof", icon="MESH_CONE")
        grid = box.column(align=True)
        grid.prop(props, "roof_type")
        grid.prop(props, "roof_pitch")
        grid.prop(props, "roof_overhang")

        layout.separator()
        row = layout.row()
        row.scale_y = 1.4
        row.operator("aig.generate_house", icon="MOD_BUILD")
        layout.operator("aig.clear_house", icon="TRASH")


class AIG_PT_style(AIG_PT_base, Panel):
    bl_idname = "AIG_PT_style"
    bl_parent_id = "AIG_PT_house"
    bl_label = "Style & Environment"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        props = context.scene.aig_house
        col = layout.column(align=True)
        col.prop(props, "style")
        col.prop(props, "stone_walls")
        layout.separator()
        col = layout.column(align=True)
        col.prop(props, "environment")
        sub = col.column(align=True)
        sub.enabled = props.environment
        sub.prop(props, "tree_count")
        sub.prop(props, "seed")


class AIG_PT_io(AIG_PT_base, Panel):
    bl_idname = "AIG_PT_io"
    bl_parent_id = "AIG_PT_house"
    bl_label = "Model I/O"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        props = context.scene.aig_house
        layout.prop(props, "json_path")
        row = layout.row(align=True)
        row.operator("aig.load_json", icon="IMPORT")
        row.operator("aig.save_json", icon="EXPORT")
        layout.label(text="Rooms beyond the panel come from JSON", icon="INFO")


_CLASSES = (AIG_PT_house, AIG_PT_style, AIG_PT_io)


def register() -> None:
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
