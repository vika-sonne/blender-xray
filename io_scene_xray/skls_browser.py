import io
from typing import List, Dict, Tuple, Optional

import bpy

from .xray_io import PackedReader
from .xray_motions import (import_motion, _skip_motion_rest)


class VIEW3D_PT_skls_animations(bpy.types.Panel):
    'Contains open .skls file operator, animations list'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_label = 'X-Ray skls file browser'

    def draw(self, context):
        layout = self.layout

        col = layout.column(align=True)
        col.operator(operator='xray.browse_skls_file', text='Open skls file...')
        if hasattr(context.object, 'xray_skls'):
            layout.template_list(listtype_name='UI_SklsList_item', list_id='compact',
                dataptr=context.object.xray_skls, propname='skls_animations',
                active_dataptr=context.object.xray_skls, active_propname='skls_animations_index', rows=15)#, type='COMPACT')


class UI_SklsList_item(bpy.types.UIList):

    def draw_item(self, _context, layout, _data, item, _icon, _active_data, _active_propname):
        row = layout.row()
        row = row.split(percentage=.30)
        row.alignment = 'RIGHT'
        row.label(text=str(item.frames))
        row.alignment = 'LEFT'
        row.label(text=item.name)


class XRaySklsAnimationProperties(bpy.types.PropertyGroup):
    'Contains animation properties in animations list of .skls file'
    name = bpy.props.StringProperty(name='Name') # animation name in .skls file
    frames = bpy.props.IntProperty(name='Frames')


class OpBrowseSklsFile(bpy.types.Operator):
    'Shows file open dialog, reads .skls file to buffer, clears & populates animations list'
    bl_idname = 'xray.browse_skls_file'
    bl_label = 'Open .skls file'
    bl_description = 'Opens .skls file with collection of animations. Used to import X-Ray engine animations.'+\
        ' To import select object with X-Ray struct of bones'
    # bl_options = {'REGISTER', 'UNDO'}


    class SklsFile():
        '''
        Used to read animations from .skls file.
        Because .skls file can has big size and reading may take long time, so the animations
        cached by byte offset in file.
        Holds entire .skls file in memory as binary blob.
        '''
        __slots__ = 'pr', 'file_path', 'animations'

        def __init__(self, file_path):
            self.file_path = file_path
            self.animations = {} # cached animations info (name: (file_offset, frames_count))
            with io.open(file_path, mode='rb') as f:
                # read entire .skls file into memory
                self.pr = PackedReader(f.read())
            self._index_animations()

        def _index_animations(self):
            'Fills the cache (self.animations) by processing entire binary blob'
            animations_count = self.pr.getf('I')[0]
            for _ in range(animations_count):
                # index animation
                offset = self.pr.offset() # first byte of the animation name
                name = self.pr.gets() # animation name
                offset2 = self.pr.offset()
                frames_range = self.pr.getf('II')
                self.animations[name] = (offset, int(frames_range[1] - frames_range[0]))
                # skip the rest bytes of skl animation to the next animation
                self.pr.set_offset(offset2)
                skip = _skip_motion_rest(self.pr.getv(), 0)
                self.pr.skip(skip)


    filepath = bpy.props.StringProperty(subtype='FILE_PATH')
    filter_glob = bpy.props.StringProperty(default='*.skls', options={'HIDDEN'})

    skls_file = None # pure python hold variable of .skls file buffer instance

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and hasattr(context.active_object.data, 'bones')

    def execute(self, context):
        self.report({'INFO'}, 'Loading animations from .skls file: "{}"'.format(self.filepath))
        context.window.cursor_set('WAIT')
        sk = context.object.xray_skls
        sk.skls_animations.clear()
        OpBrowseSklsFile.skls_file = OpBrowseSklsFile.SklsFile(file_path=self.filepath)
        self.report({'INFO'}, 'Done: {} animation(s)'.format(len(OpBrowseSklsFile.skls_file.animations)))
        # fill list with animations names
        for name, offset_frames in OpBrowseSklsFile.skls_file.animations.items():
            newitem = sk.skls_animations.add()
            newitem.name = name # animation name
            newitem.frames = offset_frames[1] # frames count
        context.window.cursor_set('DEFAULT')
        return {'FINISHED'}

    def invoke(self, context, event):
        wm = context.window_manager
        wm.fileselect_add(operator=self)
        return {'RUNNING_MODAL'}


def skls_animations_index_changed(self, context):
    'Selected animation changed in .skls list'

    # get new animation name
    if not OpBrowseSklsFile.skls_file:
        # .skls file not loaded
        return
    sk = context.object.xray_skls
    animation_name = sk.skls_animations[sk.skls_animations_index].name
    if animation_name == sk.skls_animations_prev_name:
        return # repeat animation selection

    # try to cancel & unlink old animation
    try:
        bpy.ops.screen.animation_cancel()
    except:
        pass
    try:
        # it can happened that unlink action is inaccessible
        bpy.ops.action.unlink()
    except:
        pass

    # remove previous animation if need
    ob = context.active_object
    if ob.animation_data:
        # need to remove previous animation to free the memory since .skls can contains thousand animations
        try:
            act = ob.animation_data.action
            ob.animation_data_clear()
            act.user_clear()
            bpy.data.actions.remove(action=act)
        except:
            pass

    # delete from xray property group
    try:
        ob.xray.motions_collection.remove(ob.xray.motions_collection.keys().index(sk.skls_animations_prev_name))
    except Exception as e:
        pass

    # import animation
    if animation_name not in bpy.data.actions:
        # animation not imported yet # import & create animation to bpy.data.actions
        context.window.cursor_set('WAIT')
        # import animation
        OpBrowseSklsFile.skls_file.pr.set_offset(OpBrowseSklsFile.skls_file.animations[animation_name][0])
        # bpy_armature = context.armature
        bonesmap = { b.name.lower(): b for b in ob.data.bones } # used to bone's reference detection
        reported = set() # bones names that has problems while import
        import_motion(OpBrowseSklsFile.skls_file.pr, ob, bonesmap, reported)
        sk.skls_animations_prev_name = animation_name
        context.window.cursor_set('DEFAULT')
        # try to find DopeSheet editor & set action to play
        try:
            ds = [ i for i in context.screen.areas if i.type=='DOPESHEET_EDITOR']
            if ds and not ds[0].spaces[0].action:
                ds.spaces[0].action = bpy.data.actions[animation_name]
        except:
            pass

    # assign & play a new animation
    # bpy.data.armatures[0].pose_position='POSE'
    try:
        act = bpy.data.actions[animation_name]
        if not ob.animation_data:
            ob.animation_data_create()
        ob.animation_data.action = act
    except:
        pass
    else:
        # play an action from first to last frames in cycle
        try:
            # active_scene = bpy.context.window.scene # 2.80
            context.scene.frame_start = act.frame_range[0]
            context.scene.frame_current = act.frame_range[0]
            context.scene.frame_end = act.frame_range[1]
            bpy.ops.screen.animation_play()
        except:
            pass


class XRayObjectProperties(bpy.types.PropertyGroup):
    skls_animations = bpy.props.CollectionProperty(type=XRaySklsAnimationProperties)
    skls_animations_index = bpy.props.IntProperty(update=skls_animations_index_changed)
    skls_animations_prev_name = bpy.props.StringProperty()


classes = (
    UI_SklsList_item,
    VIEW3D_PT_skls_animations,
    XRaySklsAnimationProperties,
    OpBrowseSklsFile,
    XRayObjectProperties,
)

def register():
    from bpy.utils import register_class
    # print('skls_browser.register')
    for _ in classes:
        # print('\t'+str(_))
        register_class(_)
    bpy.types.Object.xray_skls = bpy.props.PointerProperty(type=XRayObjectProperties)

def unregister():
    from bpy.utils import unregister_class
    # print('skls_browser.unregister')
    for _ in reversed(classes):
        # print('\t'+str(_))
        unregister_class(_)
    del bpy.types.Object.xray_skls
