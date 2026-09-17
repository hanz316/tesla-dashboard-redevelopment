#!/usr/bin/env python3
"""Vehicle material diagnostic set (Parts D-I).

Four paint candidates, three silver base colours, an isolatable two-lobe
clearcoat, per-pane glass, a rebuilt wheel and a taillight that uses the
structure MODEL A actually has.

Everything here is diagnostic: nothing is promoted to production by this file.
"""

import math

import bpy


def _set(bsdf, names, value):
    for name in names:
        if name in bsdf.inputs:
            bsdf.inputs[name].default_value = value
            return True
    return False


def _new(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    return mat, mat.node_tree.nodes.get("Principled BSDF")


# --- Part E: three silvers. All metallic, none of them grey/white/chrome. ---
SILVERS = {
    "neutral": {"label": "OEM SILVER NEUTRAL", "base": (0.585, 0.600, 0.622)},
    "cool": {"label": "OEM SILVER COOL", "base": (0.520, 0.548, 0.592)},
    "graphite": {"label": "OEM SILVER GRAPHITE", "base": (0.400, 0.412, 0.430)},
}


# --- Part D: four paint candidates. --------------------------------
#   A  current baseline (frozen photoreal values), for reference
#   B  physically conservative single-lobe metallic
#   C  basecoat + clearcoat layered approximation (two distinct lobes)
#   D  metal flake tuned so the texture survives 600 px, not glitter
PAINTS = {
    "a": {
        "label": "PAINT A - current baseline",
        "metallic": 0.94, "roughness": 0.215,
        "coat": 1.00, "coat_roughness": 0.038,
        "flake_strength": 0.055, "flake_scale": 190.0,
        "rough_var": 0.055, "rough_scale": 3.5,
    },
    "b": {
        "label": "PAINT B - physically conservative metallic",
        # One lobe only. No separate clearcoat: the metal IS the surface.
        "metallic": 1.00, "roughness": 0.300,
        "coat": 0.00, "coat_roughness": 0.000,
        "flake_strength": 0.030, "flake_scale": 220.0,
        "rough_var": 0.040, "rough_scale": 4.0,
    },
    "c": {
        "label": "PAINT C - basecoat + clearcoat layered",
        # Broad rougher basecoat underneath, sharp thin clearcoat on top, so
        # two specular lobes of clearly different width contribute at once.
        "metallic": 0.80, "roughness": 0.360,
        "coat": 1.00, "coat_roughness": 0.022,
        "flake_strength": 0.075, "flake_scale": 150.0,
        "rough_var": 0.070, "rough_scale": 3.0,
    },
    "d": {
        "label": "PAINT D - flake tuned for 600 px",
        # The render is 2200 px wide with the car at 1868 px; the shipping asset
        # is 600 px, i.e. a 3.1x reduction. Flake at scale 120 is ~16 px at
        # render scale and therefore ~5 px at 600 px - visible as a subtle
        # break-up of the highlight instead of either nothing or glitter.
        "metallic": 0.88, "roughness": 0.295,
        "coat": 1.00, "coat_roughness": 0.045,
        "flake_strength": 0.115, "flake_scale": 120.0,
        "rough_var": 0.085, "rough_scale": 2.4,
    },
}


def build_paint(candidate="a", silver="neutral", mode="combined"):
    """mode: combined | basecoat | clearcoat (Part F lobe isolation)."""
    cfg = PAINTS[candidate]
    base = SILVERS[silver]["base"]
    mat, bsdf = _new(f"M_Paint_{candidate}_{silver}_{mode}")
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    if mode == "basecoat":
        coat = 0.0
    elif mode == "clearcoat":
        coat = 1.0
        base = (0.004, 0.004, 0.005)   # make the metal lobe contribute ~nothing
    else:
        coat = cfg["coat"]

    _set(bsdf, ["Base Color"], base + (1.0,))
    _set(bsdf, ["Metallic"], cfg["metallic"])
    _set(bsdf, ["Roughness"], cfg["roughness"])
    _set(bsdf, ["IOR"], 1.50)
    _set(bsdf, ["Coat Weight", "Clearcoat"], coat)
    _set(bsdf, ["Coat Roughness", "Clearcoat Roughness"],
         cfg["coat_roughness"] or 0.03)
    _set(bsdf, ["Specular IOR Level", "Specular"], 0.5)

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

    rough = nodes.new("ShaderNodeTexNoise")
    rough.location = (-760, -160)
    rough.inputs["Scale"].default_value = cfg["rough_scale"]
    rough.inputs["Detail"].default_value = 2.0
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.location = (-540, -160)
    ramp.color_ramp.elements[0].position = 0.30
    ramp.color_ramp.elements[0].color = (1.0 - cfg["rough_var"],) * 3 + (1.0,)
    ramp.color_ramp.elements[1].position = 0.70
    ramp.color_ramp.elements[1].color = (1.0 + cfg["rough_var"],) * 3 + (1.0,)
    mul = nodes.new("ShaderNodeMath")
    mul.location = (-320, -160)
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = cfg["roughness"]
    links.new(rough.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], mul.inputs[0])
    links.new(mul.outputs["Value"], bsdf.inputs["Roughness"])
    return mat


# --- Part G: per-pane glass. ----------------------------------------
GLASS = {
    "roof": {"tint": (0.014, 0.018, 0.026), "rough": 0.014, "trans": 0.12,
             "spec": 1.00, "ior": 1.54},
    "front": {"tint": (0.020, 0.024, 0.032), "rough": 0.020, "trans": 0.26,
              "spec": 0.92, "ior": 1.52},
    "side": {"tint": (0.024, 0.029, 0.038), "rough": 0.026, "trans": 0.34,
             "spec": 0.86, "ior": 1.52},
    "rear": {"tint": (0.019, 0.023, 0.031), "rough": 0.022, "trans": 0.28,
             "spec": 0.90, "ior": 1.52},
}


def build_glass(kind):
    cfg = GLASS[kind]
    mat, bsdf = _new(f"M_Glass_{kind}_v4")
    _set(bsdf, ["Base Color"], cfg["tint"] + (1.0,))
    _set(bsdf, ["Metallic"], 0.0)
    _set(bsdf, ["Roughness"], cfg["rough"])
    _set(bsdf, ["IOR"], cfg["ior"])
    _set(bsdf, ["Transmission Weight", "Transmission"], cfg["trans"])
    _set(bsdf, ["Specular IOR Level", "Specular"], cfg["spec"])
    return mat


# --- Part I: wheel. -------------------------------------------------
def build_wheel():
    rim, rb = _new("M_Wheel_v4")
    _set(rb, ["Base Color"], (0.150, 0.157, 0.170, 1.0))
    _set(rb, ["Metallic"], 0.95)
    _set(rb, ["Roughness"], 0.225)
    _set(rb, ["Anisotropic"], 0.62)          # stronger machined response
    _set(rb, ["Anisotropic Rotation"], 0.25)
    _set(rb, ["Coat Weight", "Clearcoat"], 0.28)
    _set(rb, ["Coat Roughness", "Clearcoat Roughness"], 0.08)
    _set(rb, ["Specular IOR Level", "Specular"], 0.70)

    edge, eb = _new("M_Wheel_RimEdge_v4")
    _set(eb, ["Base Color"], (0.330, 0.340, 0.355, 1.0))
    _set(eb, ["Metallic"], 1.0)
    _set(eb, ["Roughness"], 0.16)

    tire, tb = _new("M_Tire_v4")
    _set(tb, ["Base Color"], (0.020, 0.020, 0.022, 1.0))
    _set(tb, ["Metallic"], 0.0)
    _set(tb, ["Roughness"], 0.93)
    _set(tb, ["Specular IOR Level", "Specular"], 0.26)

    disc, db = _new("M_BrakeDisc_v4")
    _set(db, ["Base Color"], (0.270, 0.272, 0.278, 1.0))
    _set(db, ["Metallic"], 1.0)
    _set(db, ["Roughness"], 0.38)
    _set(db, ["Anisotropic"], 0.35)

    caliper, cb = _new("M_BrakeCaliper_v4")
    _set(cb, ["Base Color"], (0.040, 0.041, 0.045, 1.0))
    _set(cb, ["Metallic"], 0.55)
    _set(cb, ["Roughness"], 0.44)
    return rim, edge, tire, disc, caliper


# --- Part H: taillight using the structure MODEL A actually has. -----
def build_taillight():
    """MODEL A gives us: outer lens geometry (rear_lights*, light_breake),
    a reflector (light_pantulan / pantulans), a red trim (satin_red) and the
    housing (black_lights / back_chrome_light). There is NO light guide.
    The materials therefore separate lens / cavity / reflector, which is all
    the geometry can support - see docs/VEHICLE_MATERIAL_DIAGNOSTIC.md
    """
    lens_red, lb = _new("M_TailLens_Outer_v4")
    _set(lb, ["Base Color"], (0.230, 0.022, 0.024, 1.0))
    _set(lb, ["Metallic"], 0.0)
    _set(lb, ["Roughness"], 0.028)
    _set(lb, ["IOR"], 1.51)
    _set(lb, ["Transmission Weight", "Transmission"], 0.36)
    _set(lb, ["Specular IOR Level", "Specular"], 0.95)

    cavity, kv = _new("M_TailCavity_v4")
    _set(kv, ["Base Color"], (0.008, 0.008, 0.010, 1.0))
    _set(kv, ["Metallic"], 0.0)
    _set(kv, ["Roughness"], 0.70)
    _set(kv, ["Specular IOR Level", "Specular"], 0.22)

    reflector, reb = _new("M_TailReflector_v4")
    _set(reb, ["Base Color"], (0.640, 0.655, 0.680, 1.0))
    _set(reb, ["Metallic"], 1.0)
    _set(reb, ["Roughness"], 0.065)

    satin, sb = _new("M_TailSatinRed_v4")
    _set(sb, ["Base Color"], (0.140, 0.016, 0.018, 1.0))
    _set(sb, ["Metallic"], 0.10)
    _set(sb, ["Roughness"], 0.34)

    housing, hb = _new("M_LightHousing_v4")
    _set(hb, ["Base Color"], (0.016, 0.016, 0.018, 1.0))
    _set(hb, ["Metallic"], 0.20)
    _set(hb, ["Roughness"], 0.46)

    lens_clear, clb = _new("M_Lens_Clear_v4")
    _set(clb, ["Base Color"], (0.050, 0.055, 0.064, 1.0))
    _set(clb, ["Metallic"], 0.0)
    _set(clb, ["Roughness"], 0.022)
    _set(clb, ["IOR"], 1.50)
    _set(clb, ["Transmission Weight", "Transmission"], 0.58)
    _set(clb, ["Specular IOR Level", "Specular"], 0.96)

    amber, ab = _new("M_Lens_Amber_v4")
    _set(ab, ["Base Color"], (0.210, 0.100, 0.014, 1.0))
    _set(ab, ["Metallic"], 0.0)
    _set(ab, ["Roughness"], 0.036)
    _set(ab, ["Transmission Weight", "Transmission"], 0.30)
    _set(ab, ["Specular IOR Level", "Specular"], 0.92)
    return lens_red, lens_clear, amber, cavity, reflector, satin, housing


def apply_v4_materials(meshes, paint="d", silver="neutral", mode="combined",
                       glass=True, tail=True, wheel=True, report=True):
    """Swap the exterior/glass/lamp/wheel slots for the v4 diagnostic set."""
    import hmi_materials

    body = build_paint(paint, silver, mode)
    roof_glass, front_glass = build_glass("roof"), build_glass("front")
    side_glass, rear_glass = build_glass("side"), build_glass("rear")
    rim, rim_edge, tire, disc, caliper = build_wheel()
    (lens_red, lens_clear, amber, cavity, reflector, satin,
     housing) = build_taillight()

    interior, ib = _new("M_Interior_v4")
    _set(ib, ["Base Color"], (0.030, 0.031, 0.034, 1.0))
    _set(ib, ["Roughness"], 0.80)
    trim, tb = _new("M_Trim_v4")
    _set(tb, ["Base Color"], (0.028, 0.029, 0.032, 1.0))
    _set(tb, ["Metallic"], 0.30)
    _set(tb, ["Roughness"], 0.55)
    chrome, cb = _new("M_Chrome_v4")
    _set(cb, ["Base Color"], (0.520, 0.535, 0.555, 1.0))
    _set(cb, ["Metallic"], 1.0)
    _set(cb, ["Roughness"], 0.085)
    alu, ab = _new("M_Aluminium_v4")
    _set(ab, ["Base Color"], (0.480, 0.495, 0.515, 1.0))
    _set(ab, ["Metallic"], 1.0)
    _set(ab, ["Roughness"], 0.20)
    screen, sb = _new("M_Screen_v4")
    _set(sb, ["Base Color"], (0.016, 0.018, 0.022, 1.0))
    _set(sb, ["Roughness"], 0.10)
    plate, pb = _new("M_Plate_v4")
    _set(pb, ["Base Color"], (0.500, 0.505, 0.515, 1.0))
    _set(pb, ["Roughness"], 0.55)

    roles = {
        "BODY": body, "GLASS": side_glass, "INTERIOR": interior,
        "RIM": rim if wheel else body, "TIRE": tire, "BRAKE": disc,
        "LENS_CLEAR": lens_clear, "LENS_RED": lens_red, "LENS_AMBER": amber,
        "TRIM_MATTE": trim, "TRIM_CHROME": chrome, "TRIM_ALUMINIUM": alu,
        "SCREEN": screen, "PLATE": plate,
    }

    counts = {}
    cache = {}
    for obj in meshes:
        # Light housing objects: cavity + reflector separation.
        lowered_obj = obj.name.lower()
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
            name = original.name.lower()

            if role == "GLASS":
                if "glass.1" in name:
                    slot.material = roof_glass
                    counts["ROOF_GLASS"] = counts.get("ROOF_GLASS", 0) + 1
                elif "depan" in name or "front" in name:
                    slot.material = front_glass
                    counts["FRONT_GLASS"] = counts.get("FRONT_GLASS", 0) + 1
                elif "belakang" in name or "rear" in name:
                    slot.material = rear_glass
                    counts["REAR_GLASS"] = counts.get("REAR_GLASS", 0) + 1
                else:
                    slot.material = side_glass
                    counts["SIDE_GLASS"] = counts.get("SIDE_GLASS", 0) + 1
                continue

            if "pantulan" in name:
                slot.material = reflector
                counts["REFLECTOR"] = counts.get("REFLECTOR", 0) + 1
                continue
            if "satin" in name:
                slot.material = satin
                counts["SATIN_RED"] = counts.get("SATIN_RED", 0) + 1
                continue
            if role in ("LENS_RED", "LENS_CLEAR") and (
                    "rear" in lowered_obj or "breake" in lowered_obj
                    or "boot" in lowered_obj or "belakang" in lowered_obj):
                slot.material = lens_red if role == "LENS_RED" else cavity
                counts["TAIL_LENS" if role == "LENS_RED" else "TAIL_CAVITY"] = \
                    counts.get("TAIL_LENS" if role == "LENS_RED"
                               else "TAIL_CAVITY", 0) + 1
                continue
            if "black_lights" in lowered_obj or "black_light" in name:
                slot.material = housing
                counts["LIGHT_HOUSING"] = counts.get("LIGHT_HOUSING", 0) + 1
                continue

            slot.material = roles.get(role, trim)
            counts[role] = counts.get(role, 0) + 1

    if report:
        print(f"[v4] paint={paint} silver={silver} mode={mode} "
              f"| roles: {dict(sorted(counts.items()))}")
    return roles
