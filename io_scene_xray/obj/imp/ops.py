import os

import bpy
import bpy_extras

from ... import ops, plugin_prefs, registry, utils
from .. import imp
from . import utils as imp_utils


@registry.module_thing
class OpImportObject(ops.BaseOperator, bpy_extras.io_utils.ImportHelper):
    bl_idname = 'xray_import.object'
    bl_label = 'Import .object'
    bl_description = 'Imports X-Ray object'
    bl_options = {'UNDO'}

    filter_glob = bpy.props.StringProperty(
        default='*.object', options={'HIDDEN'}
    )

    directory = bpy.props.StringProperty(subtype="DIR_PATH")
    files = bpy.props.CollectionProperty(
        type=bpy.types.OperatorFileListElement
    )

    import_motions = plugin_prefs.PropObjectMotionsImport()
    mesh_split_by_materials = plugin_prefs.PropObjectMeshSplitByMaterials()

    shaped_bones = plugin_prefs.PropObjectBonesCustomShapes()

    fmt_version = plugin_prefs.PropSDKVersion()

    @utils.execute_with_logger
    @utils.set_cursor_state
    def execute(self, _context):
        textures_folder = plugin_prefs.get_preferences().textures_folder_auto
        objects_folder = plugin_prefs.get_preferences().objects_folder
        if not textures_folder:
            self.report({'WARNING'}, 'No textures folder specified')
        if not self.files:
            self.report({'ERROR'}, 'No files selected')
            return {'CANCELLED'}
        import_context = imp_utils.ImportContext(
            textures=textures_folder,
            soc_sgroups=self.fmt_version == 'soc',
            import_motions=self.import_motions,
            split_by_materials=self.mesh_split_by_materials,
            operator=self,
            objects=objects_folder
        )
        for file in self.files:
            ext = os.path.splitext(file.name)[-1].lower()
            if ext == '.object':
                import_context.before_import_file()
                imp.import_file(
                    os.path.join(self.directory, file.name), import_context
                )
            else:
                self.report(
                    {'ERROR'}, 'Format of {} not recognised'.format(file)
                )
        return {'FINISHED'}

    def draw(self, _context):
        layout = self.layout
        row = layout.row()
        row.enabled = False
        row.label('%d items' % len(self.files))

        row = layout.split()
        row.label('Format Version:')
        row.row().prop(self, 'fmt_version', expand=True)

        layout.prop(self, 'import_motions')
        layout.prop(self, 'mesh_split_by_materials')
        layout.prop(self, 'shaped_bones')

    def invoke(self, context, event):
        prefs = plugin_prefs.get_preferences()
        self.fmt_version = prefs.sdk_version
        self.import_motions = prefs.object_motions_import
        self.mesh_split_by_materials = prefs.object_mesh_split_by_mat
        self.shaped_bones = prefs.object_bones_custom_shapes
        return super().invoke(context, event)
