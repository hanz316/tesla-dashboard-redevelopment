#!/usr/bin/env python3
"""One authoritative transform per moving panel.

The trunk is not one object. Opening it rotates the lid AND everything bolted
to it: the inner rear lamp lenses with their cavity and light-guide geometry,
the brake and reverse lamps that sit on the lid, the license plate and its
recess, the chrome and black trim, and the boot carpet/housing parts.

Treating the lid as a single object left those children behind at the closed
position - the defect the human review found. This module is the single place
that decides what moves and how, so the state renders and the trunk lighting
variants cannot disagree about it.

HOW THE LIST WAS DETERMINED (not from names):

    tools/blender/report_trunk_ownership.py   geometry: world bounds, distance
                                              to the lid surface, projected
                                              bbox in the 356x236 canvas
    lid-box membership                        fraction of an object's vertices
                                              inside the lid's own bounding box

Every object listed below has 100 % of its vertices inside the trunk lid's box
(`back_chrome_light` is 91 %). Names were used only to sanity-check the result.
Objects that straddle the lid and the quarter panel are listed in
`AMBIGUOUS_REAR` and are deliberately NOT moved: moving half a merged lamp
assembly would drag the fixed quarter lamp with it.
"""

TRUNK_MOVING = (
    # the lid itself
    "boot",
    "tembus_boot_ok",
    "tembus red",
    "black_boot",
    "_plastic_black_124",
    # inner rear lamp lenses, their cavities and light guides
    "rear_lightsl",
    "rear_lightsr",
    "Cavity_LEFT:rear_lightsl:0_6.0mm",
    "Cavity_RIGHT:rear_lightsr:0_6.0mm",
    "TailGuide_LEFT:rear_lightsl:0_6.0mm_rounded_rect_0.8_run0_s0",
    "TailGuide_LEFT:rear_lightsl:0_6.0mm_rounded_rect_0.8_run0_s1",
    "TailGuide_RIGHT:rear_lightsr:0_6.0mm_rounded_rect_0.45_run0_s0",
    "TailGuide_RIGHT:rear_lightsr:0_6.0mm_rounded_rect_0.45_run0_s1",
    "TailGuide_RIGHT:rear_lightsr:0_6.0mm_rounded_rect_0.45_run0_s2",
    "TailGuide_RIGHT:rear_lightsr:0_6.0mm_rounded_rect_0.45_run0_s3",
    # lamps that live on the lid
    "light_breake",
    "breake_int",
    "lightrevese_boot",
    "light_turn_lr_boot",
    "light_turn_rr_boot",
    "CavitySrc_LEFT:light_breake:0",
    "CavitySrc_RIGHT:light_breake:1",
    # plate and trim
    "platnomor",
    "chrome_light",
    "chrome.001",
    "back_chrome_light",
)

# Deliberately left fixed, with the measurement that put them here:
FIXED_BODY_REAR = (
    "rear_lights",          # 70 % inside the lid box: a merged lamp assembly
                            # spanning inner and quarter lamps, so moving it
                            # would drag the fixed quarter lamp along
    "Cavity_LEFT:rear_lights:0_5.0mm",       # quarter-panel lamp cavity
    "Cavity_RIGHT:rear_lights:1_5.0mm",
    "TailGuide_LEFT:rear_lights:0_5.0mm_rounded_rect_1.0_run0_s0",
    "TailGuide_LEFT:rear_lights:0_5.0mm_rounded_rect_1.0_run1_s0",
    "TailGuide_RIGHT:rear_lights:1_5.0mm_rounded_rect_1.0_run0_s0",
    "TailGuide_RIGHT:rear_lights:1_5.0mm_rounded_rect_1.0_run0_s1",
    "rear_lightsl_q", "rear_lightsr_q", "rear_bumper_ok", "body", "glass",
)

AMBIGUOUS_REAR = ("rear_lights",)

PANEL_ASSEMBLY = {
    "trunk": TRUNK_MOVING,
}


def members(panel_name, panel_object):
    """The objects that move together with this panel, panel object first."""
    listed = PANEL_ASSEMBLY.get(panel_name)
    if not listed:
        return (panel_object,)
    return listed


def rest_matrices(bpy, panel_name, panel_object):
    """Capture the rest pose of every member before anything moves."""
    captured = {}
    for name in members(panel_name, panel_object):
        obj = bpy.data.objects.get(name)
        if obj is not None:
            captured[name] = obj.matrix_world.copy()
    return captured


def set_progress(bpy, panel_name, panel_object, rests, applied_degrees,
                 axis, rotate_about):
    """Apply ONE transform to the whole assembly and return it.

    `applied_degrees` already includes the measured swing sign; the pivot is the
    panel object's rest position, so every member rotates about the same hinge
    point and the assembly stays rigid by construction.
    """
    pivot = rests[panel_object].translation.copy()
    transform = rotate_about(pivot, applied_degrees, axis)
    # Parents first. Assigning matrix_world to a child makes Blender derive its
    # local matrix from the parent's *current* world matrix, so a parent written
    # afterwards would drag the child off the intended pose. The first version
    # of this function wrote in dictionary order and produced a 0.9 m error on
    # exactly the pair boot/black_boot.
    for name, rest in sorted(rests.items(), key=lambda item: _depth(bpy, item[0], rests)):
        obj = bpy.data.objects.get(name)
        if obj is not None:
            obj.matrix_world = transform @ rest
    bpy.context.view_layer.update()
    return transform


def _depth(bpy, name, rests):
    """How many assembly members sit above this object in the tree."""
    depth = 0
    obj = bpy.data.objects.get(name)
    seen = set()
    while obj is not None and obj.parent is not None:
        parent = obj.parent
        if parent.name in seen:
            break
        seen.add(parent.name)
        if parent.name in rests:
            depth += 1
        obj = parent
    return depth


def restore(bpy, rests):
    for name, rest in rests.items():
        obj = bpy.data.objects.get(name)
        if obj is not None:
            obj.matrix_world = rest
    bpy.context.view_layer.update()


def rigidity_error(bpy, rests, panel_object, transform):
    """Largest deviation of any member's relative transform from the panel's.

    A rigid assembly has one transform: for every child,
    `child_now @ rest_child^-1` must equal `panel_now @ rest_panel^-1`. Returns
    the maximum absolute difference over the 4x4 matrix, in metres.
    """
    reference = rests[panel_object].inverted()
    worst = 0.0
    worst_name = None
    for name, rest in rests.items():
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        relative = obj.matrix_world @ rest.inverted()
        expected = transform @ rest.inverted() @ rest  # == transform
        delta = max(abs(relative[row][col] - expected[row][col])
                    for row in range(4) for col in range(4))
        if delta > worst:
            worst, worst_name = delta, name
    return worst, worst_name
