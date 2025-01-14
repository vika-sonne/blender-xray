import os.path
import re

import bpy
import bpy.utils.previews
from bpy_extras import io_utils

from . import xray_inject
from .ops import BaseOperator as TestReadyOperator
from .ui import collapsible, motion_list
from .utils import (
    AppError, ObjectsInitializer, logger, execute_with_logger,
    execute_require_filepath, FilenameExtHelper, mk_export_context
)
from . import plugin_prefs
from . import registry
from .details import ops as det_ops
from .err import ops as err_ops
from .scene import ops as scene_ops
from .obj.exp import ops as object_exp_ops
from .obj.imp import ops as object_imp_ops
from .anm import ops as anm_ops
from .skl import ops as skl_ops
from .ogf import ops as ogf_ops


@registry.module_thing
class OpExportProject(TestReadyOperator):
    bl_idname = 'export_scene.xray'
    bl_label = 'Export XRay Project'

    filepath = bpy.props.StringProperty(subtype='DIR_PATH', options={'SKIP_SAVE'})
    use_selection = bpy.props.BoolProperty()

    @execute_with_logger
    def execute(self, context):
        from .obj.exp import export_file
        from bpy.path import abspath
        data = context.scene.xray
        export_context = mk_export_context(
            data.object_texture_name_from_image_path, data.fmt_version, data.object_export_motions
        )
        try:
            path = abspath(self.filepath if self.filepath else data.export_root)
            os.makedirs(path, exist_ok=True)
            for obj in OpExportProject.find_objects(context, self.use_selection):
                name = obj.name
                if not name.lower().endswith('.object'):
                    name += '.object'
                opath = path
                if obj.xray.export_path:
                    opath = os.path.join(opath, obj.xray.export_path)
                    os.makedirs(opath, exist_ok=True)
                export_file(obj, os.path.join(opath, name), export_context)
        except AppError as err:
            raise err
        return {'FINISHED'}

    @staticmethod
    def find_objects(context, use_selection=False):
        objects = context.selected_objects if use_selection else context.scene.objects
        return [o for o in objects if o.xray.isroot]


@registry.module_thing
class XRayImportMenu(bpy.types.Menu):
    bl_idname = 'INFO_MT_xray_import'
    bl_label = 'X-Ray'

    def draw(self, context):
        layout = self.layout

        layout.operator(
            object_imp_ops.OpImportObject.bl_idname,
            text='Source Object (.object)'
        )
        layout.operator(anm_ops.OpImportAnm.bl_idname, text='Animation (.anm)')
        layout.operator(skl_ops.OpImportSkl.bl_idname, text='Skeletal Animation (.skl, .skls)')
        layout.operator(det_ops.OpImportDM.bl_idname, text='Details (.dm, .details)')
        layout.operator(err_ops.OpImportERR.bl_idname, text='Error List (.err)')
        layout.operator(scene_ops.OpImportLevelScene.bl_idname, text='Scene Selection (.level)')


@registry.module_thing
class XRayExportMenu(bpy.types.Menu):
    bl_idname = 'INFO_MT_xray_export'
    bl_label = 'X-Ray'

    def draw(self, context):
        layout = self.layout

        layout.operator(
            object_exp_ops.OpExportObjects.bl_idname,
            text='Source Object (.object)'
        )
        layout.operator(anm_ops.OpExportAnm.bl_idname, text='Animation (.anm)')
        layout.operator(skl_ops.OpExportSkls.bl_idname, text='Skeletal Animation (.skls)')
        layout.operator(ogf_ops.OpExportOgf.bl_idname, text='Game Object (.ogf)')
        layout.operator(det_ops.OpExportDMs.bl_idname, text='Detail Model (.dm)')
        layout.operator(
            det_ops.OpExportLevelDetails.bl_idname,
            text='Level Details (.details)'
        )
        layout.operator(scene_ops.OpExportLevelScene.bl_idname, text='Scene Selection (.level)')


def overlay_view_3d():
    def try_draw(base_obj, obj):
        if not hasattr(obj, 'xray'):
            return
        xray = obj.xray
        if hasattr(xray, 'ondraw_postview'):
            xray.ondraw_postview(base_obj, obj)
        if hasattr(obj, 'type'):
            if obj.type == 'ARMATURE':
                for bone in obj.data.bones:
                    try_draw(base_obj, bone)

    for obj in bpy.data.objects:
        try_draw(obj, obj)


_INITIALIZER = ObjectsInitializer([
    'objects',
    'materials',
])

@bpy.app.handlers.persistent
def load_post(_):
    _INITIALIZER.sync('LOADED', bpy.data)

@bpy.app.handlers.persistent
def scene_update_post(_):
    _INITIALIZER.sync('CREATED', bpy.data)


#noinspection PyUnusedLocal
def menu_func_import(self, _context):
    icon = get_stalker_icon()
    self.layout.operator(
        object_imp_ops.OpImportObject.bl_idname,
        text='X-Ray object (.object)',
        icon_value=icon
    )
    self.layout.operator(anm_ops.OpImportAnm.bl_idname, text='X-Ray animation (.anm)', icon_value=icon)
    self.layout.operator(skl_ops.OpImportSkl.bl_idname, text='X-Ray skeletal animation (.skl, .skls)', icon_value=icon)


def menu_func_export(self, _context):
    icon = get_stalker_icon()
    self.layout.operator(
        object_exp_ops.OpExportObjects.bl_idname,
        text='X-Ray object (.object)',
        icon_value=icon
    )
    self.layout.operator(anm_ops.OpExportAnm.bl_idname, text='X-Ray animation (.anm)', icon_value=icon)
    self.layout.operator(skl_ops.OpExportSkls.bl_idname, text='X-Ray animation (.skls)', icon_value=icon)


def menu_func_export_ogf(self, _context):
    icon = get_stalker_icon()
    self.layout.operator(ogf_ops.OpExportOgf.bl_idname, text='X-Ray game object (.ogf)', icon_value=icon)


def menu_func_xray_import(self, _context):
    icon = get_stalker_icon()
    self.layout.menu(XRayImportMenu.bl_idname, icon_value=icon)


def menu_func_xray_export(self, _context):
    icon = get_stalker_icon()
    self.layout.menu(XRayExportMenu.bl_idname, icon_value=icon)


def append_menu_func():
    prefs = plugin_prefs.get_preferences()
    if prefs.compact_menus:
        bpy.types.INFO_MT_file_import.remove(menu_func_import)
        bpy.types.INFO_MT_file_export.remove(menu_func_export)
        bpy.types.INFO_MT_file_export.remove(menu_func_export_ogf)
        bpy.types.INFO_MT_file_import.remove(err_ops.menu_func_import)
        bpy.types.INFO_MT_file_import.remove(det_ops.menu_func_import)
        bpy.types.INFO_MT_file_export.remove(det_ops.menu_func_export)
        bpy.types.INFO_MT_file_export.remove(scene_ops.menu_func_export)
        bpy.types.INFO_MT_file_import.remove(scene_ops.menu_func_import)
        bpy.types.INFO_MT_file_import.prepend(menu_func_xray_import)
        bpy.types.INFO_MT_file_export.prepend(menu_func_xray_export)
    else:
        bpy.types.INFO_MT_file_import.remove(menu_func_xray_import)
        bpy.types.INFO_MT_file_export.remove(menu_func_xray_export)
        bpy.types.INFO_MT_file_import.append(menu_func_import)
        bpy.types.INFO_MT_file_export.append(menu_func_export)
        bpy.types.INFO_MT_file_export.append(menu_func_export_ogf)
        bpy.types.INFO_MT_file_import.append(det_ops.menu_func_import)
        bpy.types.INFO_MT_file_export.append(det_ops.menu_func_export)
        bpy.types.INFO_MT_file_import.append(err_ops.menu_func_import)
        bpy.types.INFO_MT_file_export.append(scene_ops.menu_func_export)
        bpy.types.INFO_MT_file_import.append(scene_ops.menu_func_import)


registry.module_requires(__name__, [
    plugin_prefs,
    xray_inject,
])


preview_collections = {}
STALKER_ICON_NAME = 'stalker'


def get_stalker_icon():
    pcoll = preview_collections['main']
    icon = pcoll[STALKER_ICON_NAME]
    return icon.icon_id


def register():
    # load icon
    pcoll = bpy.utils.previews.new()
    icons_dir = os.path.join(os.path.dirname(__file__), 'icons')
    pcoll.load(STALKER_ICON_NAME, os.path.join(icons_dir, 'stalker.png'), 'IMAGE')
    preview_collections['main'] = pcoll

    registry.register_thing(object_imp_ops, __name__)
    registry.register_thing(object_exp_ops, __name__)
    registry.register_thing(anm_ops, __name__)
    registry.register_thing(skl_ops, __name__)
    registry.register_thing(ogf_ops, __name__)
    registry.register_thing(motion_list, __name__)
    scene_ops.register_operators()
    det_ops.register_operators()
    registry.register_thing(err_ops, __name__)
    append_menu_func()
    overlay_view_3d.__handle = bpy.types.SpaceView3D.draw_handler_add(
        overlay_view_3d, (),
        'WINDOW', 'POST_VIEW'
    )
    bpy.app.handlers.load_post.append(load_post)
    bpy.app.handlers.scene_update_post.append(scene_update_post)


def unregister():
    registry.unregister_thing(err_ops, __name__)
    det_ops.unregister_operators()
    scene_ops.unregister_operators()
    registry.unregister_thing(motion_list, __name__)
    registry.unregister_thing(ogf_ops, __name__)
    registry.unregister_thing(skl_ops, __name__)
    registry.unregister_thing(anm_ops, __name__)
    registry.unregister_thing(object_exp_ops, __name__)
    registry.unregister_thing(object_imp_ops, __name__)

    bpy.app.handlers.scene_update_post.remove(scene_update_post)
    bpy.app.handlers.load_post.remove(load_post)
    bpy.types.SpaceView3D.draw_handler_remove(overlay_view_3d.__handle, 'WINDOW')
    bpy.types.INFO_MT_file_export.remove(menu_func_export_ogf)
    bpy.types.INFO_MT_file_export.remove(menu_func_export)
    bpy.types.INFO_MT_file_import.remove(menu_func_import)
    bpy.types.INFO_MT_file_import.remove(menu_func_xray_import)
    bpy.types.INFO_MT_file_export.remove(menu_func_xray_export)

    # remove icon
    for pcoll in preview_collections.values():
        bpy.utils.previews.remove(pcoll)
    preview_collections.clear()
