#!/usr/bin/env python3
"""HMI material system for the dashboard vehicle visual.

Replaces the source model's materials (MODEL A ships a fluorescent-green
``primary`` car paint: base colour RGB 0.235/1.0/0.0) with a restrained,
dashboard-appropriate set:

    BODY      metallic silver paint, three selectable presets
    GLASS     dark panoramic glass with a faint interior read-through
    INTERIOR  near-black charcoal so it never competes with the car
    RIM       dark graphite metallic
    TIRE      matte near-black rubber
    BRAKE     dark disc/caliper
    LENS_*    lights-OFF lenses: dark but glossy, never black holes
    TRIM_*    black/chrome trim
    SCREEN    interior displays, near black

Classification is driven by the *material's own base-colour texture* where
possible (``tyre.PNG`` -> TIRE, ``rims.PNG`` -> RIM, ``kaca.PNG`` -> GLASS,
``leather*.PNG`` -> INTERIOR), which is objective evidence rather than a
guess from names alone.
"""

import os

import bpy

# --- body paint presets -----------------------------------------------------

BODY_PRESETS = {
    "silver01": {
        "label": "Silver 01 Neutral",
        "base": (0.560, 0.572, 0.585, 1.0),
        "metallic": 0.90,
        "roughness": 0.30,
        "coat": 0.65,
        "coat_roughness": 0.10,
    },
    "silver02": {
        "label": "Silver 02 Dark",
        "base": (0.185, 0.192, 0.205, 1.0),
        "metallic": 0.92,
        "roughness": 0.26,
        "coat": 0.75,
        "coat_roughness": 0.08,
    },
    "silver03": {
        "label": "Silver 03 Cool",
        "base": (0.470, 0.520, 0.585, 1.0),
        "metallic": 0.88,
        "roughness": 0.32,
        "coat": 0.60,
        "coat_roughness": 0.12,
    },
}

# --- texture-driven classification ------------------------------------------

TEXTURE_ROLE = {
    "tyre.png": "TIRE",
    "tyre2.png": "TIRE",
    "rims.png": "RIM",
    "disc.png": "BRAKE",
    "caliper.png": "BRAKE",
    "caliperbadge.png": "BRAKE",
    "kaca.png": "GLASS",
    "kaca2.png": "GLASS",
    "leather1.png": "INTERIOR",
    "leather2.png": "INTERIOR",
    "carpback.png": "INTERIOR",
    "lcd.png": "SCREEN",
    "belt.png": "INTERIOR",
    "button.png": "TRIM_MATTE",
    "remap2.png": "BODY",
    "remap3.png": "BODY",
    "vehiclelights.png": "LENS_CLEAR",
    "carplate.png": "PLATE",
    "red2.png": "LENS_RED",
    "red3.png": "LENS_RED",
    "tembus.png": "LENS_RED",
    "gray.png": "TRIM_MATTE",
    "gray1.png": "TRIM_MATTE",
    "black.png": "TRIM_MATTE",
    "internal_ground_ao_texture.jpeg": "TRIM_MATTE",
}

# Name-based fallbacks for materials with no image texture.
NAME_ROLE = [
    ("primary", "BODY"),
    ("glass", "GLASS"),
    ("seat", "INTERIOR"),
    ("putih", "INTERIOR"),          # Indonesian: white (seat leather)
    ("carpet", "INTERIOR"),
    ("leather", "INTERIOR"),
    ("movsteer", "INTERIOR"),       # steering wheel
    ("dvor", "TRIM_MATTE"),         # Russian: wipers
    ("hitam", "TRIM_MATTE"),        # Indonesian: black
    ("suspensi", "BRAKE"),
    ("hub_", "BRAKE"),
    ("wheel", "RIM"),
    ("chrome", "TRIM_CHROME"),
    ("cahrome", "TRIM_CHROME"),
    ("aluminium", "TRIM_ALUMINIUM"),
    ("platnomor", "PLATE"),         # licence plate
    ("lcd", "SCREEN"),
    ("light", "LENS_CLEAR"),
    ("lamp", "LENS_CLEAR"),
    ("fog", "LENS_CLEAR"),
    ("indicator", "LENS_AMBER"),
    ("revlight", "LENS_CLEAR"),
    ("break", "LENS_RED"),
    ("brake", "LENS_RED"),
    ("satin_red", "LENS_RED"),
    ("tembus", "LENS_RED"),
    ("pantulan", "LENS_RED"),
    ("mirror", "TRIM_CHROME"),
    ("black", "TRIM_MATTE"),
    ("plastic", "TRIM_MATTE"),
    ("primary", "BODY"),
]


def _texture_name(material):
    if not material.use_nodes:
        return None
    for node in material.node_tree.nodes:
        if node.type == "TEX_IMAGE" and node.image is not None:
            return os.path.basename(node.image.name).lower()
    return None


def classify(material):
    """Returns the HMI role for a source material."""
    tex = _texture_name(material)
    if tex:
        # Normalise Blender's "name.PNG.002" style duplicates.
        base = tex.split(".")[0] + "." + tex.split(".")[1] if tex.count(".") >= 1 else tex
        for key, role in TEXTURE_ROLE.items():
            if tex.startswith(key.split(".")[0]):
                return role
        del base
    low = material.name.lower()
    for token, role in NAME_ROLE:
        if token in low:
            return role
    return "TRIM_MATTE"


# --- material factory -------------------------------------------------------

def _principled(name, base, metallic, roughness, coat=0.0, coat_rough=0.1,
                transmission=0.0, ior=1.45, specular=0.5,
                emission=None, emission_strength=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        return mat
    bsdf.inputs["Base Color"].default_value = base
    if "Metallic" in bsdf.inputs:
        bsdf.inputs["Metallic"].default_value = metallic
    if "Roughness" in bsdf.inputs:
        bsdf.inputs["Roughness"].default_value = roughness
    if "IOR" in bsdf.inputs:
        bsdf.inputs["IOR"].default_value = ior
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = coat
    elif "Clearcoat" in bsdf.inputs:
        bsdf.inputs["Clearcoat"].default_value = coat
    if "Coat Roughness" in bsdf.inputs:
        bsdf.inputs["Coat Roughness"].default_value = coat_rough
    elif "Clearcoat Roughness" in bsdf.inputs:
        bsdf.inputs["Clearcoat Roughness"].default_value = coat_rough
    if transmission and "Transmission Weight" in bsdf.inputs:
        bsdf.inputs["Transmission Weight"].default_value = transmission
    elif transmission and "Transmission" in bsdf.inputs:
        bsdf.inputs["Transmission"].default_value = transmission
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = specular
    elif "Specular" in bsdf.inputs:
        bsdf.inputs["Specular"].default_value = specular
    if emission is not None:
        for key in ("Emission Color", "Emission"):
            if key in bsdf.inputs:
                bsdf.inputs[key].default_value = emission
                break
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emission_strength
    return mat


def build_material_set(body_preset="silver01"):
    """Creates one material per HMI role."""
    body = BODY_PRESETS.get(body_preset, BODY_PRESETS["silver01"])
    mats = {}
    mats["BODY"] = _principled(
        "M_BodyPaint_" + body_preset,
        body["base"], body["metallic"], body["roughness"],
        coat=body["coat"], coat_rough=body["coat_roughness"])
    mats["GLASS"] = _principled(
        "M_Glass_HMI", (0.017, 0.022, 0.028, 1.0), 0.0, 0.05,
        transmission=0.30, ior=1.45, specular=0.62)
    mats["INTERIOR"] = _principled(
        "M_Interior_Charcoal", (0.032, 0.033, 0.036, 1.0), 0.0, 0.78)
    mats["RIM"] = _principled(
        "M_Wheel_Graphite", (0.095, 0.100, 0.108, 1.0), 0.85, 0.38)
    mats["TIRE"] = _principled(
        "M_Tire_Rubber", (0.026, 0.026, 0.028, 1.0), 0.0, 0.92)
    mats["BRAKE"] = _principled(
        "M_Brake_Dark", (0.055, 0.056, 0.060, 1.0), 0.65, 0.48)
    mats["LENS_CLEAR"] = _principled(
        "M_Lens_Clear_Off", (0.075, 0.080, 0.088, 1.0), 0.15, 0.07,
        transmission=0.18, ior=1.46, specular=0.70)
    mats["LENS_RED"] = _principled(
        "M_Lens_Red_Off", (0.145, 0.018, 0.018, 1.0), 0.10, 0.10,
        specular=0.70)
    mats["LENS_AMBER"] = _principled(
        "M_Lens_Amber_Off", (0.165, 0.080, 0.012, 1.0), 0.10, 0.10,
        specular=0.70)
    mats["TRIM_MATTE"] = _principled(
        "M_Trim_MatteBlack", (0.030, 0.031, 0.034, 1.0), 0.30, 0.55)
    mats["TRIM_CHROME"] = _principled(
        "M_Trim_ChromeDark", (0.240, 0.248, 0.258, 1.0), 1.0, 0.20)
    mats["TRIM_ALUMINIUM"] = _principled(
        "M_Trim_Aluminium", (0.330, 0.340, 0.352, 1.0), 0.95, 0.28)
    mats["SCREEN"] = _principled(
        "M_Screen_Off", (0.020, 0.022, 0.026, 1.0), 0.0, 0.12)
    mats["PLATE"] = _principled(
        "M_Plate", (0.055, 0.056, 0.060, 1.0), 0.10, 0.55)
    return mats


def apply_to_meshes(meshes, body_preset="silver01", report=True):
    """Swaps every material slot for the HMI equivalent. Source untouched."""
    mats = build_material_set(body_preset)
    role_counts = {}
    cache = {}
    for obj in meshes:
        for slot in obj.material_slots:
            original = slot.material
            if original is None:
                slot.material = mats["TRIM_MATTE"]
                role_counts["TRIM_MATTE"] = role_counts.get("TRIM_MATTE", 0) + 1
                continue
            if original.name in cache:
                role = cache[original.name]
            else:
                role = classify(original)
                cache[original.name] = role
            slot.material = mats.get(role, mats["TRIM_MATTE"])
            role_counts[role] = role_counts.get(role, 0) + 1
    if report:
        print("[hmi] body preset:", body_preset,
              "| material roles applied:", dict(sorted(role_counts.items())))
    return mats, role_counts
