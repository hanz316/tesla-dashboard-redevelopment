#!/usr/bin/env python3
"""Photoreal vehicle materials: real environment reflection instead of cards.

The V2/V3 pipeline shaped the car by placing emissive cards in the scene and
letting glossy rays find them. Human review rejected the result as
"plastic / CG model look" for eight concrete reasons, the first being a large
flat grey-white roof reflection and the last being the visible artificiality of
the cards themselves.

This module changes the source of the reflections, not the amount of them:

    V3    artificial reflection cards  ->  reflections are a handful of
                                           perfectly straight, perfectly even
                                           strips
    this  real HDRI environment        ->  reflections are continuous, uneven
                                           and directionally correct, because
                                           they come from an actual photographed
                                           studio

The world still renders with `film_transparent = True`, so the HDRI shapes the
car but never appears in the exported PNG. The final asset stays a transparent
vehicle.

Material philosophy (Parts C-F):

* The V3 paint worked around missing environment information by dropping
  metallic to 0.80, which keeps a diffuse term but is not what automotive
  paint does. With a real environment there is always something to reflect, so
  this module goes back to a genuinely metallic base + separate clearcoat and
  fixes the shading problem at its source.
* Glass is a dielectric whose appearance comes from Fresnel/IOR and the
  environment, not from a dark base colour.
* Wheels/tires/brakes get per-surface response: machined anisotropy on the
  wheel, near-zero specular on rubber, radial response on the disc.
* Lamp housings separate outer lens / internal cavity / reflector so an OFF
  lamp has depth instead of being a coloured surface.
"""

import math

import bpy

# Silver automotive paint. Base colour is the F0 of the metallic layer, so it
# is the metal's reflectance - not a "how bright do I want it" dial.
PAINT_PRESETS = {
    "silver_photoreal": {
        "label": "Silver (photoreal multilayer)",
        "base": (0.585, 0.600, 0.622, 1.0),
        "metallic": 0.94,
        "roughness": 0.215,
        "coat": 1.0,
        "coat_roughness": 0.038,
        "flake_strength": 0.055,
        "flake_scale": 190.0,
        "ior": 1.50,
    },
    "silver_photoreal_cool": {
        "label": "Silver (cooler, slightly darker)",
        "base": (0.520, 0.545, 0.585, 1.0),
        "metallic": 0.96,
        "roughness": 0.235,
        "coat": 1.0,
        "coat_roughness": 0.034,
        "flake_strength": 0.05,
        "flake_scale": 210.0,
        "ior": 1.50,
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


def build_paint(preset="silver_photoreal"):
    """Multilayer metallic paint: metal base + clearcoat + microflake.

    Ordering matters: the clearcoat sits *on top* of the metal, so the sharp
    studio reflection comes from the coat while the body colour depth comes
    from the metal underneath. That separation is what reads as "paint"
    instead of "painted plastic".
    """
    cfg = PAINT_PRESETS.get(preset, PAINT_PRESETS["silver_photoreal"])
    mat, bsdf = _new_material("M_Paint_Photoreal_" + preset)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    _set(bsdf, ["Base Color"], cfg["base"])
    _set(bsdf, ["Metallic"], cfg["metallic"])
    _set(bsdf, ["Roughness"], cfg["roughness"])
    _set(bsdf, ["IOR"], cfg["ior"])
    _set(bsdf, ["Coat Weight", "Clearcoat"], cfg["coat"])
    _set(bsdf, ["Coat Roughness", "Clearcoat Roughness"], cfg["coat_roughness"])
    _set(bsdf, ["Specular IOR Level", "Specular"], 0.5)

    # Metallic flake: a fine, low-contrast normal break-up. Deliberately much
    # weaker than a "glitter" effect - it should only stop the clearcoat
    # reflection from looking like a mirror finish.
    noise = nodes.new("ShaderNodeTexNoise")
    noise.location = (-760, -520)
    noise.inputs["Scale"].default_value = cfg["flake_scale"]
    noise.inputs["Detail"].default_value = 1.0
    bump = nodes.new("ShaderNodeBump")
    bump.location = (-360, -520)
    bump.inputs["Strength"].default_value = cfg["flake_strength"]
    bump.inputs["Distance"].default_value = 0.0005
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    # Very slight roughness variation across the panel. Wide, low amplitude:
    # enough to make the reflection breathe, not enough to look like noise.
    rough_noise = nodes.new("ShaderNodeTexNoise")
    rough_noise.location = (-760, -160)
    rough_noise.inputs["Scale"].default_value = 3.5
    rough_noise.inputs["Detail"].default_value = 2.0
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.location = (-540, -160)
    ramp.color_ramp.elements[0].position = 0.30
    ramp.color_ramp.elements[0].color = (0.95, 0.95, 0.95, 1.0)
    ramp.color_ramp.elements[1].position = 0.70
    ramp.color_ramp.elements[1].color = (1.06, 1.06, 1.06, 1.0)
    mul = nodes.new("ShaderNodeMath")
    mul.location = (-320, -160)
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = cfg["roughness"]
    links.new(rough_noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], mul.inputs[0])
    links.new(mul.outputs["Value"], bsdf.inputs["Roughness"])
    return mat


def build_glass():
    """Dielectric glass: Fresnel/IOR driven, tinted, dark but not a hole.

    Transmission is kept low on purpose - automotive glass is tinted, so most
    of what you see is the environment *reflected* off it, and only a little
    of what is behind it. The deep-at-normal / bright-at-grazing behaviour is
    what sells the curvature, and that comes from the dielectric BSDF, not
    from a colour.
    """
    def make(name, tint, roughness, transmission, specular):
        mat, bsdf = _new_material(name)
        _set(bsdf, ["Base Color"], tint + (1.0,))
        _set(bsdf, ["Metallic"], 0.0)
        _set(bsdf, ["Roughness"], roughness)
        _set(bsdf, ["IOR"], 1.52)
        _set(bsdf, ["Transmission Weight", "Transmission"], transmission)
        _set(bsdf, ["Specular IOR Level", "Specular"], specular)
        return mat

    roof = make("M_Glass_Roof_Photoreal", (0.020, 0.024, 0.031),
                0.020, 0.20, 0.90)
    side = make("M_Glass_Side_Photoreal", (0.026, 0.031, 0.040),
                0.028, 0.34, 0.86)
    rear = make("M_Glass_Rear_Photoreal", (0.022, 0.027, 0.035),
                0.024, 0.28, 0.88)
    return roof, side, rear


def build_wheels():
    """Machined graphite alloy: response must differ per spoke face."""
    rim, rb = _new_material("M_Wheel_Machined_Photoreal")
    _set(rb, ["Base Color"], (0.135, 0.142, 0.155, 1.0))
    _set(rb, ["Metallic"], 0.95)
    _set(rb, ["Roughness"], 0.255)
    _set(rb, ["Coat Weight", "Clearcoat"], 0.20)
    _set(rb, ["Coat Roughness", "Clearcoat Roughness"], 0.12)
    # Anisotropy is what makes a machined face read as machined: the highlight
    # stretches along the cutting direction instead of being a round dot.
    _set(rb, ["Anisotropic"], 0.45)
    _set(rb, ["Anisotropic Rotation"], 0.25)
    _set(rb, ["Specular IOR Level", "Specular"], 0.55)

    tire, tb = _new_material("M_Tire_Rubber_Photoreal")
    _set(tb, ["Base Color"], (0.022, 0.022, 0.024, 1.0))
    _set(tb, ["Metallic"], 0.0)
    _set(tb, ["Roughness"], 0.92)
    # Very low specular so rubber does not read as shiny plastic, but not zero:
    # a faint sheen at grazing angles is what keeps it from black-crushing.
    _set(tb, ["Specular IOR Level", "Specular"], 0.28)

    disc, db = _new_material("M_Brake_Disc_Photoreal")
    _set(db, ["Base Color"], (0.240, 0.242, 0.248, 1.0))
    _set(db, ["Metallic"], 1.0)
    _set(db, ["Roughness"], 0.42)
    _set(db, ["Anisotropic"], 0.30)          # radial brushed response
    _set(db, ["Anisotropic Rotation"], 0.0)

    caliper, cb = _new_material("M_Brake_Caliper_Photoreal")
    _set(cb, ["Base Color"], (0.045, 0.046, 0.050, 1.0))
    _set(cb, ["Metallic"], 0.55)
    _set(cb, ["Roughness"], 0.46)
    return rim, tire, disc, caliper


def build_lights():
    """OFF lamp housings.

    A taillight is not a red surface. Even unlit it is: a clear outer lens with
    a strong specular response, a dark cavity behind it, and a reflector with
    structure. Geometry is untouched, so the depth is created by giving the
    lens a real dielectric response and the cavity a much darker, rougher
    material than the lens.
    """
    lens_clear, lb = _new_material("M_Lens_Clear_Photoreal")
    _set(lb, ["Base Color"], (0.055, 0.060, 0.070, 1.0))
    _set(lb, ["Metallic"], 0.0)
    _set(lb, ["Roughness"], 0.025)
    _set(lb, ["IOR"], 1.50)
    _set(lb, ["Transmission Weight", "Transmission"], 0.55)
    _set(lb, ["Specular IOR Level", "Specular"], 0.95)

    # Outer red lens: transmissive enough that the cavity behind it shows
    # through, which is what creates the depth.
    lens_red, rlb = _new_material("M_Lens_Red_Photoreal")
    _set(rlb, ["Base Color"], (0.190, 0.020, 0.020, 1.0))
    _set(rlb, ["Metallic"], 0.0)
    _set(rlb, ["Roughness"], 0.035)
    _set(rlb, ["IOR"], 1.50)
    _set(rlb, ["Transmission Weight", "Transmission"], 0.30)
    _set(rlb, ["Specular IOR Level", "Specular"], 0.92)

    lens_amber, ab = _new_material("M_Lens_Amber_Photoreal")
    _set(ab, ["Base Color"], (0.200, 0.095, 0.014, 1.0))
    _set(ab, ["Metallic"], 0.0)
    _set(ab, ["Roughness"], 0.045)
    _set(ab, ["IOR"], 1.50)
    _set(ab, ["Transmission Weight", "Transmission"], 0.26)
    _set(ab, ["Specular IOR Level", "Specular"], 0.90)

    # The cavity is what the lens is in front of. Dark, matte, almost no
    # response: it exists to make the lens look like it has something behind
    # it instead of being a coloured sticker on the body.
    cavity, kv = _new_material("M_Lamp_Cavity_Photoreal")
    _set(kv, ["Base Color"], (0.012, 0.012, 0.014, 1.0))
    _set(kv, ["Metallic"], 0.0)
    _set(kv, ["Roughness"], 0.62)
    _set(kv, ["Specular IOR Level", "Specular"], 0.30)

    reflector, reb = _new_material("M_Reflector_Photoreal")
    _set(reb, ["Base Color"], (0.560, 0.575, 0.600, 1.0))
    _set(reb, ["Metallic"], 1.0)
    _set(reb, ["Roughness"], 0.085)
    return lens_clear, lens_red, lens_amber, cavity, reflector


def apply_photoreal_materials(meshes, preset="silver_photoreal", report=True):
    """Swap every slot for the photoreal set, keeping the role classifier."""
    import hmi_materials  # reuse the evidence-based role classifier

    paint = build_paint(preset)
    roof_glass, side_glass, rear_glass = build_glass()
    rim, tire, disc, caliper = build_wheels()
    lens_clear, lens_red, lens_amber, cavity, reflector = build_lights()

    interior, ib = _new_material("M_Interior_Photoreal")
    _set(ib, ["Base Color"], (0.030, 0.031, 0.034, 1.0))
    _set(ib, ["Roughness"], 0.80)
    trim, tb = _new_material("M_Trim_Matte_Photoreal")
    _set(tb, ["Base Color"], (0.028, 0.029, 0.032, 1.0))
    _set(tb, ["Metallic"], 0.30)
    _set(tb, ["Roughness"], 0.55)
    chrome, cb = _new_material("M_Trim_Chrome_Photoreal")
    _set(cb, ["Base Color"], (0.520, 0.535, 0.555, 1.0))
    _set(cb, ["Metallic"], 1.0)
    _set(cb, ["Roughness"], 0.085)
    alu, ab = _new_material("M_Trim_Aluminium_Photoreal")
    _set(ab, ["Base Color"], (0.480, 0.495, 0.515, 1.0))
    _set(ab, ["Metallic"], 1.0)
    _set(ab, ["Roughness"], 0.20)
    screen, sb = _new_material("M_Screen_Photoreal")
    _set(sb, ["Base Color"], (0.016, 0.018, 0.022, 1.0))
    _set(sb, ["Roughness"], 0.10)
    plate, pb = _new_material("M_Plate_Photoreal")
    _set(pb, ["Base Color"], (0.500, 0.505, 0.515, 1.0))
    _set(pb, ["Roughness"], 0.55)

    roles = {
        "BODY": paint,
        "GLASS": side_glass,
        "INTERIOR": interior,
        "RIM": rim,
        "TIRE": tire,
        "BRAKE": disc,
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
            lowered = original.name.lower()
            # Panoramic roof pane vs side/side-rear glass.
            if role == "GLASS" and "glass.1" in lowered:
                slot.material = roof_glass
                counts["ROOF_GLASS"] = counts.get("ROOF_GLASS", 0) + 1
                continue
            if role == "GLASS" and ("rear" in lowered or "belakang" in lowered):
                slot.material = rear_glass
                counts["REAR_GLASS"] = counts.get("REAR_GLASS", 0) + 1
                continue
            # Reflector bowl behind the lens gets the bright chrome surface;
            # the lens itself stays glass.
            if role in ("LENS_CLEAR", "LENS_RED") and "pantulan" in lowered:
                slot.material = reflector
                counts["REFLECTOR"] = counts.get("REFLECTOR", 0) + 1
                continue
            slot.material = roles.get(role, trim)
            counts[role] = counts.get(role, 0) + 1

    if report:
        print("[photoreal] preset:", preset,
              "| roles:", dict(sorted(counts.items())))
    return roles


def build_hdri_world(hdri_path, strength=1.0, rotation_deg=0.0,
                     background_visible=False):
    """World = real HDRI. The camera never sees it (film stays transparent)."""
    world = bpy.data.worlds.new("HMI_World_HDRI")
    bpy.context.scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    for node in list(nodes):
        nodes.remove(node)

    output = nodes.new("ShaderNodeOutputWorld")
    output.location = (300, 0)
    bg = nodes.new("ShaderNodeBackground")
    bg.location = (100, 0)
    bg.inputs["Strength"].default_value = strength
    env = nodes.new("ShaderNodeTexEnvironment")
    env.location = (-160, 0)
    img = bpy.data.images.load(hdri_path, check_existing=True)
    env.image = img

    mapping = nodes.new("ShaderNodeMapping")
    mapping.location = (-380, 0)
    mapping.inputs["Rotation"].default_value = (0.0, 0.0,
                                                math.radians(rotation_deg))
    tex = nodes.new("ShaderNodeTexCoord")
    tex.location = (-600, 0)

    links.new(tex.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    links.new(env.outputs["Color"], bg.inputs["Color"])
    links.new(bg.outputs["Background"], output.inputs["Surface"])
    print(f"[photoreal] HDRI world: {hdri_path.split('/')[-1]} "
          f"strength={strength} rotation={rotation_deg}deg")
    return world


def _area_light(name, location, energy, size, rotation, glossy=True):
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


def build_hybrid_lights(key_scale=1.0, fill_scale=1.0):
    """HDRI HYBRID: at most one key, one fill, one rim.

    These are shaping only. They are deliberately weak compared with V3,
    because the HDRI is now responsible for the actual reflection content.
    """
    _area_light("HMI_Key", (5.4, -5.0, 5.6), 260.0 * key_scale, 6.0,
                (math.radians(44), 0, math.radians(48)), glossy=True)
    _area_light("HMI_Fill", (-5.0, 5.6, 2.6), 90.0 * key_scale * fill_scale, 11.0,
                (math.radians(80), 0, math.radians(-150)), glossy=False)
    # A second, very low bounce so the underbody and wheel arches keep some
    # information. Crushed black is a lighting error, not a premium look.
    _area_light("HMI_Bounce", (-0.5, 3.4, 0.35), 46.0 * fill_scale, 13.0,
                (math.radians(96), 0, math.radians(-170)), glossy=False)
    _area_light("HMI_Rim", (-7.0, -3.4, 3.4), 150.0 * key_scale, 5.0,
                (math.radians(78), 0, math.radians(-66)), glossy=True)


def build_hdri_only_lights(fill_scale=1.0):
    """HDRI ONLY: no shaped reflection cards, no key light.

    One very wide, very dim diffuse bounce survives. Without it the underside
    of the car is lit only by whatever the HDRI has below the horizon, and the
    wheel arches crush to black - which is a lighting error, not a look.
    """
    _area_light("HMI_Bounce", (-0.5, 3.4, 0.35), 92.0 * fill_scale, 13.0,
                (math.radians(96), 0, math.radians(-170)), glossy=False)
