#!/usr/bin/env python3
"""Vehicle Visual V3: controlled premium automotive HMI shading.

V2 proved the pipeline (layered paint + a reflection studio Cycles honours).
Human review then rejected V2 as production art for eight specific reasons,
and this module is the response to those reasons:

1. roof/trunk softbox reflection too big, too white, too uniform
   -> PART 3: the single large ceiling softbox becomes long, NARROW strips,
      and every card is re-coloured off-white / neutral grey so the reflection
      carries the silver base instead of turning the panel white.
2. dark side far too black, contours lost
   -> PART 4: dedicated diffuse-only ambient/bounce lights, marked
      visible_glossy=False. They raise the shadow floor and CANNOT create a
      new specular highlight.
3. door/body contour unreadable on the dark side -> same as 2
4. wheel arch and front wheel merge into the background
   -> PART 8: a dim, tightly aimed wheel strip plus a lifted graphite base.
5. silver base not present enough
   -> PART 6: the important physical point. metallic drops from ~0.90 to
      ~0.74-0.82 and the base colour rises, so the material keeps a diffuse
      term. A fully metallic surface has NO diffuse component: with nothing to
      reflect it renders black, which is exactly the V2 dark-side failure.
6. reflection contrast too strong -> PART 3 (narrower + dimmer cards)
7. glass is a black hole -> PART 7 (slight transmission + fresnel gradient)
8. taillight OFF housing has no lens depth -> PART 9

The MODEL A geometry is untouched. This module only builds materials, the
reflection studio and the light rig.
"""

import math

import bpy

BODY_PRESETS_V3 = {
    "silver_v3": {
        "label": "Silver V3 (balanced metallic)",
        "base": (0.585, 0.600, 0.620, 1.0),
        "metallic": 0.80,
        "roughness": 0.255,
        "coat": 0.50,
        "coat_roughness": 0.060,
        "flake_strength": 0.10,
        "ior": 1.50,
    },
    "silver_v3_bright": {
        "label": "Silver V3 (brighter base)",
        "base": (0.660, 0.672, 0.690, 1.0),
        "metallic": 0.74,
        "roughness": 0.275,
        "coat": 0.45,
        "coat_roughness": 0.065,
        "flake_strength": 0.09,
        "ior": 1.50,
    },
}

# Part 3: reflections are OFF-WHITE, never pure white, and much dimmer than V2.
CARD_GREY = (0.560, 0.568, 0.585, 1.0)   # neutral cool grey, keeps the silver
CARD_SOFT = (0.430, 0.440, 0.460, 1.0)   # dimmer, for fill strips
CARD_WARM = (0.520, 0.512, 0.500, 1.0)   # very slightly warm rear kick


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


def _emissive_card(name, location, size, rotation, strength=1.0,
                   color=CARD_GREY):
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

    for attr, value in (("visible_camera", False), ("visible_shadow", False),
                        ("visible_diffuse", True), ("visible_glossy", True),
                        ("visible_transmission", True)):
        if hasattr(obj, attr):
            setattr(obj, attr, value)
    return obj


def _area_light(name, location, energy, size, rotation, glossy=False):
    """Diffuse-only fill by default: lifts the shadow floor, no new highlight."""
    bpy.ops.object.light_add(type="AREA", location=location)
    light = bpy.context.active_object
    light.name = name
    light.data.energy = energy
    light.data.size = size
    light.rotation_euler = rotation
    if hasattr(light, "visible_glossy"):
        light.visible_glossy = glossy
    if hasattr(light, "visible_camera"):
        light.visible_camera = False
    return light


def build_body_paint_v3(preset="silver_v3"):
    """Layered metallic silver that still reads as silver where nothing shines.

    The whole point of V3: keep enough diffuse term (metallic < 1) and enough
    base reflectance that an unlit panel is dark silver, not black plastic.
    """
    cfg = BODY_PRESETS_V3.get(preset, BODY_PRESETS_V3["silver_v3"])
    mat, bsdf = _new_material("M_BodyPaint_HMI_V3_" + preset)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    _set(bsdf, ["Base Color"], cfg["base"])
    _set(bsdf, ["Metallic"], cfg["metallic"])
    _set(bsdf, ["Roughness"], cfg["roughness"])
    _set(bsdf, ["IOR"], cfg["ior"])
    _set(bsdf, ["Coat Weight", "Clearcoat"], cfg["coat"])
    _set(bsdf, ["Coat Roughness", "Clearcoat Roughness"], cfg["coat_roughness"])
    _set(bsdf, ["Specular IOR Level", "Specular"], 0.5)

    # Gentler roughness variation than V2: V2's range was part of what made the
    # reflections read as "CG studio model" rather than painted metal.
    noise = nodes.new("ShaderNodeTexNoise")
    noise.location = (-780, -120)
    noise.inputs["Scale"].default_value = 5.0
    noise.inputs["Detail"].default_value = 2.0
    if "Roughness" in noise.inputs:
        noise.inputs["Roughness"].default_value = 0.5

    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.location = (-560, -120)
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (0.93, 0.93, 0.93, 1.0)
    ramp.color_ramp.elements[1].position = 0.65
    ramp.color_ramp.elements[1].color = (1.05, 1.05, 1.05, 1.0)

    rough_mul = nodes.new("ShaderNodeMath")
    rough_mul.location = (-320, -120)
    rough_mul.operation = "MULTIPLY"
    rough_mul.inputs[1].default_value = cfg["roughness"]

    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], rough_mul.inputs[0])
    links.new(rough_mul.outputs["Value"], bsdf.inputs["Roughness"])

    flake = nodes.new("ShaderNodeTexNoise")
    flake.location = (-780, -520)
    flake.inputs["Scale"].default_value = 240.0
    flake.inputs["Detail"].default_value = 1.0

    bump = nodes.new("ShaderNodeBump")
    bump.location = (-360, -520)
    bump.inputs["Strength"].default_value = cfg["flake_strength"] * 0.06
    bump.inputs["Distance"].default_value = 0.0006
    links.new(flake.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def build_glass_v3():
    """Deep glass that still shows curvature and its own boundary.

    V2 glass was so dark it read as a hole. V3 keeps it very dark but adds a
    fresnel gradient into the base colour, so the pane carries a visible
    sweep across its curve even where the studio strips do not land.
    """
    def glass(name, base_dark, base_edge, roughness, transmission, specular):
        mat, bsdf = _new_material(name)
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        _set(bsdf, ["Metallic"], 0.0)
        _set(bsdf, ["Roughness"], roughness)
        _set(bsdf, ["IOR"], 1.52)
        _set(bsdf, ["Transmission Weight", "Transmission"], transmission)
        _set(bsdf, ["Specular IOR Level", "Specular"], specular)

        layer = nodes.new("ShaderNodeLayerWeight")
        layer.location = (-760, 120)
        layer.inputs["Blend"].default_value = 0.35
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.location = (-540, 120)
        ramp.color_ramp.elements[0].position = 0.30
        ramp.color_ramp.elements[0].color = base_dark + (1.0,)
        ramp.color_ramp.elements[1].position = 0.85
        ramp.color_ramp.elements[1].color = base_edge + (1.0,)
        links.new(layer.outputs["Facing"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        return mat

    roof = glass("M_RoofGlass_HMI_V3", (0.019, 0.023, 0.030),
                 (0.085, 0.098, 0.120), 0.030, 0.24, 0.80)
    window = glass("M_WindowGlass_HMI_V3", (0.024, 0.029, 0.037),
                   (0.100, 0.112, 0.135), 0.042, 0.36, 0.74)
    return roof, window


def build_wheel_v3():
    """Dark graphite that separates from the background without going silver."""
    rim, rb = _new_material("M_Wheel_Graphite_V3")
    _set(rb, ["Base Color"], (0.115, 0.121, 0.132, 1.0))
    _set(rb, ["Metallic"], 0.84)
    _set(rb, ["Roughness"], 0.285)
    _set(rb, ["Coat Weight", "Clearcoat"], 0.30)
    _set(rb, ["Coat Roughness", "Clearcoat Roughness"], 0.09)
    _set(rb, ["Specular IOR Level", "Specular"], 0.62)

    tire, tb = _new_material("M_Tire_Rubber_V3")
    _set(tb, ["Base Color"], (0.028, 0.028, 0.031, 1.0))
    _set(tb, ["Metallic"], 0.0)
    _set(tb, ["Roughness"], 0.90)
    _set(tb, ["Specular IOR Level", "Specular"], 0.38)

    brake, bb = _new_material("M_Brake_Dark_V3")
    _set(bb, ["Base Color"], (0.058, 0.059, 0.064, 1.0))
    _set(bb, ["Metallic"], 0.62)
    _set(bb, ["Roughness"], 0.48)
    return rim, tire, brake


def build_lens_v3():
    """OFF lamps still need lens depth and an internal reflector impression."""
    lens_clear, lb = _new_material("M_Lens_Clear_Off_V3")
    _set(lb, ["Base Color"], (0.070, 0.076, 0.086, 1.0))
    _set(lb, ["Metallic"], 0.10)
    _set(lb, ["Roughness"], 0.030)
    _set(lb, ["IOR"], 1.48)
    _set(lb, ["Transmission Weight", "Transmission"], 0.42)
    _set(lb, ["Specular IOR Level", "Specular"], 0.88)

    lens_red, rrb = _new_material("M_Lens_Red_Off_V3")
    _set(rrb, ["Base Color"], (0.140, 0.017, 0.017, 1.0))
    _set(rrb, ["Metallic"], 0.05)
    _set(rrb, ["Roughness"], 0.055)
    _set(rrb, ["IOR"], 1.48)
    _set(rrb, ["Transmission Weight", "Transmission"], 0.18)
    _set(rrb, ["Specular IOR Level", "Specular"], 0.86)

    lens_amber, ab = _new_material("M_Lens_Amber_Off_V3")
    _set(ab, ["Base Color"], (0.170, 0.082, 0.012, 1.0))
    _set(ab, ["Metallic"], 0.05)
    _set(ab, ["Roughness"], 0.065)
    _set(ab, ["IOR"], 1.48)
    _set(ab, ["Specular IOR Level", "Specular"], 0.84)

    # Internal reflector bowl: dark chrome with a gradient, so an OFF housing
    # reads as having depth behind the lens instead of being a flat block.
    reflector, reb = _new_material("M_Reflector_Dark_V3")
    _set(reb, ["Base Color"], (0.300, 0.315, 0.335, 1.0))
    _set(reb, ["Metallic"], 1.0)
    _set(reb, ["Roughness"], 0.115)
    return lens_clear, lens_red, lens_amber, reflector


def build_reflection_studio_v3():
    """HMI_Reflection_Studio_V3 - long narrow strips instead of big softboxes.

    Every card is off-white and dimmer than V2. A reflection should describe
    the panel's curvature; it must not repaint the panel white.
    """
    cards = []
    # Two long ceiling strips (X long, Y narrow) instead of one big softbox.
    # They are separated across Y so the roof gets a genuine double streak
    # rather than one uniform white band.
    cards.append(_emissive_card(
        "Roof_Strip_L", (0.0, -0.95, 3.30), 1.0,
        (0.0, 0.0, 0.0), strength=1.55, color=CARD_GREY))
    cards[-1].scale.x = 9.0    # long along the car
    cards[-1].scale.y = 0.55   # narrow across it
    cards.append(_emissive_card(
        "Roof_Strip_R", (0.0, 0.35, 3.05), 1.0,
        (0.0, math.radians(4), 0.0), strength=1.15, color=CARD_SOFT))
    cards[-1].scale.x = 8.0
    cards[-1].scale.y = 0.45

    # Shoulder/beltline: narrow and bright enough to trace the character line.
    cards.append(_emissive_card(
        "Shoulder_Strip", (0.6, -2.05, 2.05), 1.0,
        (math.radians(-58), 0.0, 0.0), strength=1.90, color=CARD_GREY))
    cards[-1].scale.x = 7.5
    cards[-1].scale.y = 0.32

    # Side gradient: a tall, very dim card. This is what gives the doors a
    # gradient on the camera side instead of one hard highlight plus black.
    cards.append(_emissive_card(
        "Side_Gradient", (-0.4, -6.4, 1.55), 1.0,
        (math.radians(90), 0.0, 0.0), strength=0.42, color=CARD_SOFT))
    cards[-1].scale.x = 8.5
    cards[-1].scale.y = 3.6

    # Rear quarter: two short cards at different angles approximate the
    # curved highlight that a single flat card cannot produce.
    cards.append(_emissive_card(
        "Rear_Quarter_A", (-5.1, -1.1, 1.95), 1.0,
        (math.radians(72), 0.0, math.radians(-64)), strength=1.35,
        color=CARD_WARM))
    cards[-1].scale.x = 3.4
    cards[-1].scale.y = 0.45
    cards.append(_emissive_card(
        "Rear_Quarter_B", (-5.9, 0.5, 1.35), 1.0,
        (math.radians(80), 0.0, math.radians(-40)), strength=0.95,
        color=CARD_SOFT))
    cards[-1].scale.x = 2.6
    cards[-1].scale.y = 0.40

    # Trunk: dim, wide, low. Keeps the trunk lid silver instead of white.
    cards.append(_emissive_card(
        "Trunk_Fill", (-2.6, -2.9, 2.75), 1.0,
        (math.radians(30), 0.0, math.radians(-8)), strength=0.55,
        color=CARD_SOFT))
    cards[-1].scale.x = 4.6
    cards[-1].scale.y = 1.8

    # Wheels: tightly aimed, deliberately dim. Separates the rim from the
    # background without turning graphite into silver.
    cards.append(_emissive_card(
        "Wheel_Strip", (-0.2, -3.4, 0.45), 1.0,
        (math.radians(66), 0.0, 0.0), strength=0.62, color=CARD_SOFT))
    cards[-1].scale.x = 5.4
    cards[-1].scale.y = 0.55

    # Lenses: a narrow low strip so an OFF housing still catches a specular
    # line on its lens and reads as glass over a reflector.
    cards.append(_emissive_card(
        "Lens_Strip", (1.2, -2.6, 0.95), 1.0,
        (math.radians(62), 0.0, 0.0), strength=0.70, color=CARD_GREY))
    cards[-1].scale.x = 4.2
    cards[-1].scale.y = 0.28

    for index, card in enumerate(cards):
        card["hmi_role"] = "reflection_card_v3"
        card["hmi_index"] = index
    return cards


def build_light_rig_v3(key_scale=1.0, ambient_scale=1.0, world_floor=None):
    """Soft key + explicit dark-side recovery (PART 4).

    HMI_Key and HMI_Rim still do the shaping. The two Ambient_* lights are
    diffuse-only (visible_glossy=False), so they exist purely to lift the
    shadow floor: the dark side stays the dark side, but the door contour,
    wheel arch, side skirt and front wheel become readable.
    """
    _area_light("HMI_Key", (5.0, -5.4, 5.4), 520.0 * key_scale, 7.0,
                (math.radians(46), 0, math.radians(50)), glossy=True)
    _area_light("HMI_Rim", (-7.2, -3.2, 3.6), 370.0 * key_scale, 5.0,
                (math.radians(78), 0, math.radians(-66)), glossy=True)
    # Dark-side recovery: large, dim, diffuse only.
    # 540 W: tuned by histogram against the V2 reference. Enough to lift the
    # shadow floor (p1 2 -> 19, p5 12 -> 35) without flattening the car
    # (p95 stays at 195 and the over-200 share stays near 4%).
    _area_light("HMI_Ambient_DarkSide", (-1.6, 6.8, 2.6), 540.0 * ambient_scale, 14.0,
                (math.radians(84), 0, math.radians(-158)), glossy=False)
    # Under/side bounce: keeps the rocker panel and wheel arch from going flat.
    _area_light("HMI_Ambient_Bounce", (-0.5, 3.2, 0.30), 216.0 * ambient_scale, 12.0,
                (math.radians(96), 0, math.radians(-170)), glossy=False)

    world = bpy.data.worlds.new("HMI_World_V3")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        # Slightly raised from V2: this is the global shadow floor. It is not
        # enough to flatten the car, only enough to stop pure black.
        floor = 0.030 if world_floor is None else world_floor
        bg.inputs["Color"].default_value = (floor, floor * 1.2, floor * 1.55, 1.0)
        if "Strength" in bg.inputs:
            bg.inputs["Strength"].default_value = 1.0


def apply_v3_materials(meshes, preset="silver_v3", report=True):
    """Swap every slot for the V3 material set, keeping the role classifier."""
    import hmi_materials  # reuse the evidence-based role classifier

    body = build_body_paint_v3(preset)
    roof_glass, window_glass = build_glass_v3()
    lens_clear, lens_red, lens_amber, reflector = build_lens_v3()
    rim, tire, brake = build_wheel_v3()

    interior, ib = _new_material("M_Interior_Charcoal_V3")
    _set(ib, ["Base Color"], (0.034, 0.035, 0.039, 1.0))
    _set(ib, ["Roughness"], 0.78)
    trim, tb = _new_material("M_Trim_MatteBlack_V3")
    _set(tb, ["Base Color"], (0.030, 0.031, 0.035, 1.0))
    _set(tb, ["Metallic"], 0.35)
    _set(tb, ["Roughness"], 0.48)
    chrome, cb = _new_material("M_Trim_ChromeDark_V3")
    _set(cb, ["Base Color"], (0.250, 0.258, 0.270, 1.0))
    _set(cb, ["Metallic"], 1.0)
    _set(cb, ["Roughness"], 0.14)
    alu, ab = _new_material("M_Trim_Aluminium_V3")
    _set(ab, ["Base Color"], (0.330, 0.340, 0.352, 1.0))
    _set(ab, ["Metallic"], 0.95)
    _set(ab, ["Roughness"], 0.24)
    screen, sb = _new_material("M_Screen_Off_V3")
    _set(sb, ["Base Color"], (0.022, 0.024, 0.029, 1.0))
    _set(sb, ["Roughness"], 0.09)
    plate, pb = _new_material("M_Plate_V3")
    _set(pb, ["Base Color"], (0.055, 0.056, 0.060, 1.0))
    _set(pb, ["Roughness"], 0.48)

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
        print("[v3] preset:", preset, "| roles:", dict(sorted(counts.items())))
    return roles
