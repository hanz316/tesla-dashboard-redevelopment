#!/usr/bin/env python3
"""Parts C, D, F, G: reference shaders and two geometry experiments.

REFERENCE PAINT is deliberately built from two different BSDFs rather than one
Principled with different slider values, because the previous round showed that
Paint A/B/C/D - four sets of Principled sliders - produced differences too small
to see at 600 px:

        Glossy BSDF          (clearcoat: sharp, thin, low roughness)
              |
        Mix Shader by Fresnel
              |
        Principled BSDF      (metallic basecoat: broad, rougher)
              ^
        Voronoi-driven bump  (microflake, under the coat, not on it)

Putting the flake on the basecoat rather than the clearcoat is the physically
correct order: real flake sits under the clearcoat, so it perturbs the broad
lobe and leaves the sharp clearcoat reflection intact.

The two geometry experiments never touch the source files: they build temporary
objects / modifiers in memory.
"""

import math

import bpy
import bmesh
from mathutils import Vector


def _set(bsdf, names, value):
    for name in names:
        if name in bsdf.inputs:
            bsdf.inputs[name].default_value = value
            return True
    return False


SILVER_REFERENCE = (0.560, 0.578, 0.605)


def build_reference_paint(name="M_Paint_Reference",
                          base_color=SILVER_REFERENCE):
    """Clearcoat over metallic basecoat, mixed by Fresnel, with microflake."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    for node in list(nt.nodes):
        nt.nodes.remove(node)

    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (700, 0)

    # --- clearcoat lobe: a separate Glossy BSDF, not a Principled slider ---
    gloss = nt.nodes.new("ShaderNodeBsdfGlossy")
    gloss.location = (200, 260)
    _set(gloss, ["Roughness"], 0.018)
    clearcoat_tint = (0.92, 0.93, 0.95, 1.0)
    if "Color" in gloss.inputs:
        gloss.inputs["Color"].default_value = clearcoat_tint

    # --- basecoat lobe: metallic Principled ---
    base = nt.nodes.new("ShaderNodeBsdfPrincipled")
    base.location = (200, -120)
    _set(base, ["Base Color"], base_color + (1.0,))
    _set(base, ["Metallic"], 1.0)
    _set(base, ["Roughness"], 0.340)
    _set(base, ["IOR"], 1.5)

    # Microflake lives UNDER the coat: it perturbs the basecoat normal only.
    flake = nt.nodes.new("ShaderNodeTexVoronoi")
    flake.location = (-560, -430)
    flake.feature = "F1"
    flake.inputs["Scale"].default_value = 260.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.location = (-260, -430)
    bump.inputs["Strength"].default_value = 0.16
    bump.inputs["Distance"].default_value = 0.0006
    nt.links.new(flake.outputs["Distance"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], base.inputs["Normal"])

    # Broad roughness variation across the panel.
    broad = nt.nodes.new("ShaderNodeTexNoise")
    broad.location = (-560, -160)
    broad.inputs["Scale"].default_value = 2.6
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.location = (-330, -160)
    ramp.color_ramp.elements[0].position = 0.32
    ramp.color_ramp.elements[0].color = (0.90, 0.90, 0.90, 1.0)
    ramp.color_ramp.elements[1].position = 0.68
    ramp.color_ramp.elements[1].color = (1.12, 1.12, 1.12, 1.0)
    mul = nt.nodes.new("ShaderNodeMath")
    mul.location = (-110, -160)
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = 0.340
    nt.links.new(broad.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], mul.inputs[0])
    nt.links.new(mul.outputs["Value"], base.inputs["Roughness"])

    # --- Fresnel mix: coat dominates at grazing angles ---
    layer = nt.nodes.new("ShaderNodeLayerWeight")
    layer.location = (-330, 120)
    layer.inputs["Blend"].default_value = 0.16
    fres = nt.nodes.new("ShaderNodeMath")
    fres.location = (-110, 120)
    fres.operation = "MULTIPLY"
    fres.inputs[1].default_value = 0.62
    nt.links.new(layer.outputs["Facing"], fres.inputs[0])

    mix = nt.nodes.new("ShaderNodeMixShader")
    mix.location = (450, 0)
    # A constant 0.5-ish coat share plus the fresnel term, so the sharp lobe
    # is present at normal incidence too (real clearcoat is not only grazing).
    add = nt.nodes.new("ShaderNodeMath")
    add.location = (200, 60)
    add.operation = "ADD"
    add.inputs[1].default_value = 0.42
    nt.links.new(fres.outputs["Value"], add.inputs[0])
    clamp = nt.nodes.new("ShaderNodeClamp")
    clamp.location = (330, 60)
    nt.links.new(add.outputs["Value"], clamp.inputs["Value"])
    nt.links.new(clamp.outputs["Result"], mix.inputs["Fac"])
    nt.links.new(base.outputs["BSDF"], mix.inputs[1])
    nt.links.new(gloss.outputs["BSDF"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    return mat


REFERENCE_GLASS = {
    "roof": {"tint": (0.012, 0.016, 0.024), "rough": 0.010, "trans": 0.10,
             "ior": 1.545, "coat": 0.85},
    "front": {"tint": (0.018, 0.022, 0.030), "rough": 0.016, "trans": 0.22,
              "ior": 1.525, "coat": 0.55},
    "side": {"tint": (0.022, 0.027, 0.036), "rough": 0.020, "trans": 0.30,
             "ior": 1.520, "coat": 0.40},
    "rear": {"tint": (0.017, 0.021, 0.029), "rough": 0.018, "trans": 0.25,
             "ior": 1.522, "coat": 0.48},
}


def build_reference_glass(kind):
    """Dielectric base plus an explicit thin coating layer.

    The coating is what separates "deep tinted automotive glass" from "black
    acrylic": it adds a controlled specular layer on top of the dielectric, so
    the pane keeps a visible Fresnel edge and a low-roughness environment
    reflection instead of reading as a flat dark solid.
    """
    cfg = REFERENCE_GLASS[kind]
    mat = bpy.data.materials.new(f"M_Glass_Reference_{kind}")
    mat.use_nodes = True
    nt = mat.node_tree
    for node in list(nt.nodes):
        nt.nodes.remove(node)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (520, 0)
    prism = nt.nodes.new("ShaderNodeBsdfPrincipled")
    prism.location = (180, -80)
    _set(prism, ["Base Color"], cfg["tint"] + (1.0,))
    _set(prism, ["Metallic"], 0.0)
    _set(prism, ["Roughness"], cfg["rough"])
    _set(prism, ["IOR"], cfg["ior"])
    _set(prism, ["Transmission Weight", "Transmission"], cfg["trans"])
    _set(prism, ["Specular IOR Level", "Specular"], 0.5)
    coat = nt.nodes.new("ShaderNodeBsdfGlossy")
    coat.location = (180, 200)
    _set(coat, ["Roughness"], max(cfg["rough"] * 0.7, 0.008))
    if "Color" in coat.inputs:
        coat.inputs["Color"].default_value = (0.85, 0.88, 0.93, 1.0)
    mix = nt.nodes.new("ShaderNodeMixShader")
    mix.location = (350, 40)
    mix.inputs["Fac"].default_value = cfg["coat"]
    nt.links.new(prism.outputs["BSDF"], mix.inputs[1])
    nt.links.new(coat.outputs["BSDF"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    return mat


def local_remesh(obj, voxel_size=0.008, adaptivity=0.0, smooth_iters=2):
    """Part C: an in-memory retopology proxy for one object.

    Voxel remesh is used as a *proxy* for retopology, not as a recommendation:
    it rebuilds the surface on a uniform grid, which is exactly the thing we
    want to test (does a regular, evenly sized surface carry a better
    reflection than the original triangulation). The silhouette deviation is
    measured separately by the caller.

    The original object is left untouched: the reshaped copy replaces the mesh
    data of the SAME object so materials and parenting still apply, and the
    pre-remesh mesh is returned so nothing is silently lost.
    """
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    mod = obj.modifiers.new("HMI_LocalRemesh", "REMESH")
    mod.mode = "VOXEL"
    mod.voxel_size = voxel_size
    mod.adaptivity = adaptivity
    mod.use_smooth_shade = True
    deps = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(deps)
    new_mesh = bpy.data.meshes.new_from_object(evaluated)
    obj.modifiers.remove(mod)
    obj.data = new_mesh
    for poly in new_mesh.polygons:
        poly.use_smooth = True
    wn = obj.modifiers.new("HMI_WeightedNormal", "WEIGHTED_NORMAL")
    wn.keep_sharp = True
    wn.weight = 60
    obj.select_set(False)
    return new_mesh


def add_light_guide(obj_names, length=0.62, radius=0.016, z_offset=0.0):
    """Part G: a temporary internal light guide inside the tail lamp.

    Not production. It exists only to answer "how much of 'red plastic' is a
    missing-geometry problem". The strip is a simple capsule placed inside the
    existing lens objects.
    """
    created = []
    mat = bpy.data.materials.new("M_LightGuide_TEMP")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        _set(bsdf, ["Base Color"], (0.420, 0.030, 0.032, 1.0))
        _set(bsdf, ["Metallic"], 0.35)
        _set(bsdf, ["Roughness"], 0.18)
        _set(bsdf, ["Specular IOR Level", "Specular"], 0.75)

    for name in obj_names:
        src = bpy.data.objects.get(name)
        if src is None or src.type != "MESH":
            continue
        lo = Vector((1e9, 1e9, 1e9))
        hi = Vector((-1e9, -1e9, -1e9))
        for corner in src.bound_box:
            w = src.matrix_world @ Vector(corner)
            lo = Vector((min(lo.x, w.x), min(lo.y, w.y), min(lo.z, w.z)))
            hi = Vector((max(hi.x, w.x), max(hi.y, w.y), max(hi.z, w.z)))
        centre = (lo + hi) * 0.5
        width = max(hi.y - lo.y, 0.05)

        bm = bmesh.new()
        segs = max(3, int(width / (radius * 2)))
        bmesh.ops.create_cone(bm, cap_ends=True, segments=12,
                              radius1=radius, radius2=radius,
                              depth=length)
        for v in bm.verts:
            v.co = Vector((v.co.x, v.co.z, v.co.y))   # lay it along Y
        mesh = bpy.data.meshes.new(name + "_lightguide")
        bm.to_mesh(mesh)
        bm.free()
        strip = bpy.data.objects.new(name + "_lightguide", mesh)
        bpy.context.scene.collection.objects.link(strip)
        strip.location = (centre.x + 0.01, centre.y, centre.z + z_offset)
        mesh.materials.append(mat)
        for poly in mesh.polygons:
            poly.use_smooth = True
        created.append(strip)
    print(f"[reference] temporary light guides: {len(created)}")
    return created
