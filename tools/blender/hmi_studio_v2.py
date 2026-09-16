#!/usr/bin/env python3
"""Vehicle Visual V2: layered automotive paint + virtual reflection studio.

Two upgrades over V1:

1. **Layered paint** (`M_BodyPaint_HMI_V2`) — Principled BSDF base+clearcoat
   plus a very restrained procedural layer: a low-contrast noise drives slight
   roughness variation (metallic flake read) and a high-frequency bump adds a
   barely-visible flake normal. Deliberately sub-perceptual at 1:1 but it
   breaks up the flat CG highlight rolloff at dashboard scale.

2. **Reflection studio** (`HMI_Reflection_Studio_V2`) — emissive cards that are
   INVISIBLE TO CAMERA but visible to glossy/reflection rays. They are what
   actually shapes the car: long ceiling streaks, shoulder-line highlight,
   rear-quarter kick and door-curvature gradient. No HDRI, no sky, no studio
   background — the final frame stays transparent RGBA.

All objects/materials live only in memory; the master .blend is never
modified by this module except when the caller explicitly saves.
"""

import math
import os

import bpy

BODY_PRESETS_V2 = {
    "silver01": {
        "label": "Silver 01 Neutral",
        "base": (0.560, 0.572, 0.585, 1.0),
        "metallic": 0.90,
        "roughness": 0.30,
        "coat": 0.70,
        "coat_roughness": 0.055,
        "flake_strength": 0.16,
        "ior": 1.50,
    },
    "silver02": {
        "label": "Silver 02 Dark",
        "base": (0.150, 0.158, 0.172, 1.0),
        "metallic": 0.94,
        "roughness": 0.235,
        "coat": 0.85,
        "coat_roughness": 0.040,
        "flake_strength": 0.12,
        "ior": 1.52,
    },
    "silver03": {
        "label": "Silver 03 Cool",
        "base": (0.455, 0.505, 0.575, 1.0),
        "metallic": 0.89,
        "roughness": 0.315,
        "coat": 0.65,
        "coat_roughness": 0.065,
        "flake_strength": 0.18,
        "ior": 1.49,
    },
}


def _set(bsdf, names, value):
    for name in names:
        if name in bsdf.inputs:
            bsdf.inputs[name].default_value = value
            return True
    return False


def _new_material(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    return mat, mat.node_tree.nodes.get("Principled BSDF")


def build_body_paint(preset="silver01"):
    """Layered metallic paint with subtle flake; stays simple on purpose."""
    cfg = BODY_PRESETS_V2.get(preset, BODY_PRESETS_V2["silver01"])
    mat, bsdf = _new_material("M_BodyPaint_HMI_V2_" + preset)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    _set(bsdf, ["Base Color"], cfg["base"])
    _set(bsdf, ["Metallic"], cfg["metallic"])
    _set(bsdf, ["Roughness"], cfg["roughness"])
    _set(bsdf, ["IOR"], cfg["ior"])
    _set(bsdf, ["Coat Weight", "Clearcoat"], cfg["coat"])
    _set(bsdf, ["Coat Roughness", "Clearcoat Roughness"], cfg["coat_roughness"])
    _set(bsdf, ["Specular IOR Level", "Specular"], 0.5)

    # Low-frequency roughness variation: breaks the uniform CG highlight.
    noise = nodes.new("ShaderNodeTexNoise")
    noise.location = (-780, -120)
    noise.inputs["Scale"].default_value = 7.0
    noise.inputs["Detail"].default_value = 2.0
    if "Roughness" in noise.inputs:
        noise.inputs["Roughness"].default_value = 0.5

    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.location = (-560, -120)
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (0.88, 0.88, 0.88, 1.0)
    ramp.color_ramp.elements[1].position = 0.65
    ramp.color_ramp.elements[1].color = (1.10, 1.10, 1.10, 1.0)

    rough_mul = nodes.new("ShaderNodeMath")
    rough_mul.location = (-320, -120)
    rough_mul.operation = "MULTIPLY"
    rough_mul.inputs[1].default_value = cfg["roughness"]

    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], rough_mul.inputs[0])
    links.new(rough_mul.outputs["Value"], bsdf.inputs["Roughness"])

    # Very fine flake normal. Strength is intentionally tiny.
    flake = nodes.new("ShaderNodeTexNoise")
    flake.location = (-780, -520)
    flake.inputs["Scale"].default_value = 260.0
    flake.inputs["Detail"].default_value = 1.0

    bump = nodes.new("ShaderNodeBump")
    bump.location = (-360, -520)
    bump.inputs["Strength"].default_value = cfg["flake_strength"] * 0.08
    bump.inputs["Distance"].default_value = 0.0007
    links.new(flake.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def build_glass_v2():
    """Roof glass (single dark panoramic pane) vs side/window glass."""
    roof, rb = _new_material("M_RoofGlass_HMI")
    _set(rb, ["Base Color"], (0.011, 0.014, 0.019, 1.0))
    _set(rb, ["Metallic"], 0.0)
    _set(rb, ["Roughness"], 0.035)
    _set(rb, ["IOR"], 1.52)
    _set(rb, ["Transmission Weight", "Transmission"], 0.16)
    _set(rb, ["Specular IOR Level", "Specular"], 0.72)

    win, wb = _new_material("M_WindowGlass_HMI")
    _set(wb, ["Base Color"], (0.015, 0.019, 0.025, 1.0))
    _set(wb, ["Metallic"], 0.0)
    _set(wb, ["Roughness"], 0.045)
    _set(wb, ["IOR"], 1.50)
    _set(wb, ["Transmission Weight", "Transmission"], 0.28)
    _set(wb, ["Specular IOR Level", "Specular"], 0.68)
    return roof, win


def build_reflector_and_lens():
    """Light housings read as real lens+reflector even with the lamp off."""
    lens_clear, lb = _new_material("M_Lens_Clear_Off")
    _set(lb, ["Base Color"], (0.055, 0.060, 0.068, 1.0))
    _set(lb, ["Metallic"], 0.10)
    _set(lb, ["Roughness"], 0.045)
    _set(lb, ["IOR"], 1.48)
    _set(lb, ["Transmission Weight", "Transmission"], 0.34)
    _set(lb, ["Specular IOR Level", "Specular"], 0.80)

    lens_red, rrb = _new_material("M_Lens_Red_Off")
    _set(rrb, ["Base Color"], (0.115, 0.014, 0.014, 1.0))
    _set(rrb, ["Metallic"], 0.05)
    _set(rrb, ["Roughness"], 0.075)
    _set(rrb, ["IOR"], 1.48)
    _set(rrb, ["Transmission Weight", "Transmission"], 0.12)
    _set(rrb, ["Specular IOR Level", "Specular"], 0.78)

    lens_amber, ab = _new_material("M_Lens_Amber_Off")
    _set(ab, ["Base Color"], (0.150, 0.070, 0.010, 1.0))
    _set(ab, ["Metallic"], 0.05)
    _set(ab, ["Roughness"], 0.080)
    _set(ab, ["IOR"], 1.48)

    # Reflectors behind the lens: dark chrome, not black plastic.
    reflector, reb = _new_material("M_Reflector_Dark")
    _set(reb, ["Base Color"], (0.400, 0.415, 0.435, 1.0))
    _set(reb, ["Metallic"], 1.0)
    _set(reb, ["Roughness"], 0.14)
    return lens_clear, lens_red, lens_amber, reflector


def build_wheel_v2():
    rim, rb = _new_material("M_Wheel_Graphite")
    _set(rb, ["Base Color"], (0.085, 0.090, 0.098, 1.0))
    _set(rb, ["Metallic"], 0.88)
    _set(rb, ["Roughness"], 0.32)
    _set(rb, ["Coat Weight", "Clearcoat"], 0.25)
    _set(rb, ["Coat Roughness", "Clearcoat Roughness"], 0.10)

    tire, tb = _new_material("M_Tire_Rubber")
    _set(tb, ["Base Color"], (0.023, 0.023, 0.025, 1.0))
    _set(tb, ["Metallic"], 0.0)
    _set(tb, ["Roughness"], 0.94)
    _set(tb, ["Specular IOR Level", "Specular"], 0.30)

    brake, bb = _new_material("M_Brake_Dark")
    _set(bb, ["Base Color"], (0.048, 0.049, 0.053, 1.0))
    _set(bb, ["Metallic"], 0.60)
    _set(bb, ["Roughness"], 0.52)
    return rim, tire, brake


def _emissive_card(name, location, size, rotation, strength=1.0,
                   color=(1.0, 0.99, 0.96, 1.0)):
    """A softbox the camera cannot see but glossy rays can."""
    mesh = bpy.data.meshes.new(name + "_mesh")
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)

    half = size * 0.5
    verts = [(-half, -half, 0.0), (half, -half, 0.0),
             (half, half, 0.0), (-half, half, 0.0)]
    mesh.from_pydata(verts, [], [(0, 1, 2, 3)])
    mesh.update()

    obj.location = location
    obj.rotation_euler = rotation
    mat, bsdf = _new_material(name + "_mat")
    _set(bsdf, ["Base Color"], (0.0, 0.0, 0.0, 1.0))
    for key in ("Emission Color", "Emission"):
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = color
            break
    _set(bsdf, ["Emission Strength"], strength)
    obj.data.materials.append(mat)

    # Visible in reflections, invisible to the camera, no shadow casting.
    for attr, value in (("visible_camera", False), ("visible_shadow", False),
                        ("visible_diffuse", True), ("visible_glossy", True),
                        ("visible_transmission", True)):
        if hasattr(obj, attr):
            setattr(obj, attr, value)
    return obj


def build_reflection_studio():
    """HMI_Reflection_Studio_V2 — the geometry that actually shapes the car.

    Layout is tuned so the reflected shapes run ALONG the car: long ceiling
    streaks over the roof, a narrow shoulder stripe that traces the beltline,
    a rear kick that separates the quarter panel from the background, and
    side cards that create the door-curvature gradient.
    """
    cards = []
    # Ceiling: big soft source; its reflection makes the long roof streak.
    cards.append(_emissive_card(
        "Ceiling_Softbox", (0.4, -0.8, 4.2), 14.0,
        (0.0, 0.0, 0.0), strength=1.5))
    # Ceiling stripe: narrow, offset forward -> crisp roofline highlight.
    cards.append(_emissive_card(
        "Shoulder_Stripe_Card", (1.1, -1.4, 3.6), 9.0,
        (0.0, math.radians(6), 0.0), strength=2.6))
    # Side cards: left brighter (that is the side facing the camera).
    cards.append(_emissive_card(
        "Side_Softbox_L", (0.2, -7.0, 1.9), 12.0,
        (math.radians(90), 0.0, 0.0), strength=1.35))
    cards.append(_emissive_card(
        "Side_Softbox_R", (0.0, 7.0, 1.9), 12.0,
        (math.radians(-90), 0.0, 0.0), strength=0.55))
    # Rear rim card: separates the tail from the dark dashboard background.
    cards.append(_emissive_card(
        "Rear_Rim_Card", (-6.6, -1.6, 2.6), 8.0,
        (math.radians(74), 0.0, math.radians(-72)), strength=2.1))
    # Front fill card: gentle gradient along the door surfaces.
    cards.append(_emissive_card(
        "Front_Fill_Card", (6.4, -2.2, 2.4), 9.0,
        (math.radians(76), 0.0, math.radians(70)), strength=0.75))
    for index, card in enumerate(cards):
        card["hmi_role"] = "reflection_card"
        card["hmi_index"] = index
    return cards


def apply_v2_materials(meshes, preset="silver01", report=True):
    """Swap every slot for the V2 material set, keeping the classification."""
    import hmi_materials  # reuse the evidence-based role classifier

    body = build_body_paint(preset)
    roof_glass, window_glass = build_glass_v2()
    lens_clear, lens_red, lens_amber, reflector = build_reflector_and_lens()
    rim, tire, brake = build_wheel_v2()

    interior, ib = _new_material("M_Interior_Charcoal")
    _set(ib, ["Base Color"], (0.028, 0.029, 0.032, 1.0))
    _set(ib, ["Roughness"], 0.80)
    trim, tb = _new_material("M_Trim_MatteBlack")
    _set(tb, ["Base Color"], (0.026, 0.027, 0.030, 1.0))
    _set(tb, ["Metallic"], 0.35)
    _set(tb, ["Roughness"], 0.50)
    chrome, cb = _new_material("M_Trim_ChromeDark")
    _set(cb, ["Base Color"], (0.230, 0.238, 0.248, 1.0))
    _set(cb, ["Metallic"], 1.0)
    _set(cb, ["Roughness"], 0.15)
    alu, ab = _new_material("M_Trim_Aluminium")
    _set(ab, ["Base Color"], (0.310, 0.320, 0.332, 1.0))
    _set(ab, ["Metallic"], 0.95)
    _set(ab, ["Roughness"], 0.26)
    screen, sb = _new_material("M_Screen_Off")
    _set(sb, ["Base Color"], (0.018, 0.020, 0.024, 1.0))
    _set(sb, ["Roughness"], 0.10)
    plate, pb = _new_material("M_Plate")
    _set(pb, ["Base Color"], (0.050, 0.051, 0.055, 1.0))
    _set(pb, ["Roughness"], 0.50)

    roles = {
        "BODY": body,
        "GLASS": window_glass,          # default glass = window
        "INTERIOR": interior,
        "RIM": rim,
        "TIRE": tire,
        "BRAKE": brake,
        "LENS_CLEAR": lens_clear,
        "LENS_RED": lens_red,
        "LENS_AMBER": lens_amber,
        "TRIM_MATTE": trim,
        "TRIM_CHROME": chrome,
        "TRIM_ALUMINIUM": alu,
        "SCREEN": screen,
        "PLATE": plate,
    }

    counts = {}
    cache = {}
    for obj in meshes:
        for slot in obj.material_slots:
            original = slot.material
            if original is None:
                slot.material = trim
                counts["TRIM_MATTE"] = counts.get("TRIM_MATTE", 0) + 1
                continue
            if original.name in cache:
                role = cache[original.name]
            else:
                role = hmi_materials.classify(original)
                cache[original.name] = role
            # Roof glass: only the panoramic pane on the 'glass' object.
            if role == "GLASS" and "glass.1" in original.name.lower():
                slot.material = roof_glass
                counts["ROOF_GLASS"] = counts.get("ROOF_GLASS", 0) + 1
                continue
            # Reflectors behind the lenses read as dark chrome.
            if role in ("LENS_CLEAR", "LENS_RED") and "pantulan" in original.name.lower():
                slot.material = reflector
                counts["REFLECTOR"] = counts.get("REFLECTOR", 0) + 1
                continue
            slot.material = roles.get(role, trim)
            counts[role] = counts.get(role, 0) + 1

    if report:
        print("[v2] preset:", preset, "| roles:", dict(sorted(counts.items())))
    return roles
