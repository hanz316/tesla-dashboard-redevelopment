#!/usr/bin/env python3
"""Horizon V5 environment art: a rendered night road, not a drawn one.

The approved V5 reference (assets/ui/horizon_v5_reference.png) shows one
continuous cinematic place: a wet road at night, a lit city on the horizon,
mountain ridges behind it, and the car standing in that space. The rejected
attempts drew that space with gradients, polygons and lines. This script does
not draw it: it builds the space as geometry, materials and light and renders
it with Cycles, then composites the frozen Model A asset set into the same rig.

Every environment object is placed in *view space* - (u, v, z) with u across
the frame and v away from the camera along the frozen Horizon azimuth - because
the frozen camera looks 49.4 deg off the world Y axis. Placing ridges "at +Y"
would put the whole city outside the frame, which is exactly what a previous
run did.

Passes
------
plate          perspective environment camera, car hidden from every ray:
               assets/ui/horizon_v5_background.png
road_no_car    frozen ortho camera, the road with no car: the reference the
               road response is measured against
road_<state>   frozen ortho camera, road + car: the car occludes the road and
               the wet surface returns its shadow, its reflection and the
               ground response of whatever lamp the state has lit
car_<state>    frozen ortho camera, film transparent, environment geometry out
               of the camera ray but still lighting the car

Compositing road_<state> - road_no_car gives the car's ground response; pasting
car_<state> over it gives the vehicle layer. That is done by
tools/assets/compose_horizon_v5_vehicle.py, which has Pillow and numpy.

Frozen contracts respected: Model A geometry, the frozen Horizon camera, the
frozen taillight system and the 356x236 asset contract. The V5 tier adds
resolution and a cinematic environment; it does not change geometry or camera.

Usage:
    blender -b -P tools/blender/build_horizon_v5_environment.py -- \
        --master assets/source/blender/model_a_material_candidate.blend \
        --samples 96
"""

import argparse
import json
import math
import os
import random
import sys
import time

try:
    import bpy
    from mathutils import Vector
    from bpy_extras.object_utils import world_to_camera_view
except ImportError:  # pragma: no cover - only runs inside Blender
    sys.exit("Run inside Blender")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_vehicle_state_assets as state_assets  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# The frozen asset camera: 356x236 canvas, these exact numbers.
HORIZON_CAMERA = {
    "name": "Camera_Horizon",
    "type": "ORTHO",
    "ortho_scale": 5.55,
    "location": (-5.30, -4.55, 3.85),
    "target": (0.0, 0.0, 0.62),
}

CANVAS = (1920, 480)

# Reference-derived composition. Measured from
# assets/ui/horizon_v5_reference_measurements.json (2172x724) and mapped into a
# centred 1440x480 content box: s = 480/724 = 0.66298, x = 960 + (x_ref-1086)*s.
#   car   x 775..1380, y 235..520  ->  752..1153, 156..345
#   horizon 252                    ->  167
COMPOSITION = {
    "content_box": [240, 0, 1440, 480],
    "content_scale": 480 / 724.0,
    "car_visible_width_px": 401.0,
    "car_centre_x_px": 954.0,
    "car_ground_contact_y_px": 345.0,
    "horizon_row_px": 167.0,
}


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--master", required=True)
    parser.add_argument("--ui", default=os.path.join(REPO_ROOT, "assets", "ui"))
    parser.add_argument("--out", default=os.path.join(
        REPO_ROOT, "assets", "rendered", "vehicle", "horizon_v5"))
    parser.add_argument("--samples", type=int, default=96)
    parser.add_argument("--report", default=os.path.join(
        REPO_ROOT, "assets", "checkpoints", "horizon_v5",
        "horizon_v5_environment.json"))
    parser.add_argument("--stages", default="plate,road,car")
    parser.add_argument("--states", default="base,running,brake,headlight,"
                                            "indicator_left,indicator_right,"
                                            "hazard")
    parser.add_argument("--resolution", default="1920x480")
    parser.add_argument("--exposure", type=float, default=1.0)
    parser.add_argument("--dry-run", action="store_true",
                        help="build the scene and print measurements only")
    return parser.parse_args(argv)


def view_frame():
    """Forward and right unit vectors of the frozen Horizon view, on the ground
    plane, plus the camera's ground position."""
    location = Vector(HORIZON_CAMERA["location"])
    target = Vector(HORIZON_CAMERA["target"])
    forward = Vector((target.x - location.x, target.y - location.y, 0.0))
    forward.normalize()
    right = Vector((forward.y, -forward.x, 0.0))
    return {"forward": forward, "right": right, "ground": location,
            "azimuth_deg": math.degrees(math.atan2(forward.x, forward.y))}


FRAME = view_frame()


def place(u, v, z):
    """View-space point -> world. u is image-right, v is away from the camera."""
    ground = FRAME["ground"]
    return Vector((ground.x + u * FRAME["right"].x + v * FRAME["forward"].x,
                   ground.y + u * FRAME["right"].y + v * FRAME["forward"].y,
                   z))


def open_master(path):
    bpy.ops.wm.open_mainfile(filepath=path)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.use_denoising = True
    scene.cycles.seed = 0
    scene.cycles.use_animated_seed = False
    return scene


def hide_studio(scene):
    hidden = []
    for name in ("ENV_Floor", "ENV_Side", "ENV_Sky"):
        obj = bpy.data.objects.get(name)
        if obj is not None:
            obj.hide_render = True
            hidden.append(name)
    return hidden


def car_objects():
    return [obj for obj in bpy.data.objects
            if obj.type == "MESH"
            and not obj.name.startswith(("ENV_", "V5_"))]


def set_rays(objects, **flags):
    for obj in objects:
        for key, value in flags.items():
            setattr(obj, "visible_" + key, value)


# --------------------------------------------------------------------------
# the place
# --------------------------------------------------------------------------
def night_world(scene, spec):
    world = bpy.data.worlds.new("V5_NightSky")
    scene.world = world
    world.use_nodes = True
    tree = world.node_tree
    for node in list(tree.nodes):
        if node.type != "OUTPUT_WORLD":
            tree.nodes.remove(node)
    output = tree.nodes["World Output"]
    coord = tree.nodes.new("ShaderNodeTexCoord")
    separate = tree.nodes.new("ShaderNodeSeparateXYZ")
    tree.links.new(coord.outputs["Generated"], separate.inputs["Vector"])
    ramp = tree.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "EASE"
    elements = ramp.color_ramp.elements
    elements.remove(elements[1])
    for position, colour in spec["sky_stops"]:
        item = elements.new(position)
        item.color = colour
    background = tree.nodes.new("ShaderNodeBackground")
    background.inputs["Strength"].default_value = spec["sky_strength"]
    tree.links.new(separate.outputs["Z"], ramp.inputs["Fac"])
    tree.links.new(ramp.outputs["Color"], background.inputs["Color"])
    tree.links.new(background.outputs["Background"], output.inputs["Surface"])
    return world


def road(scene, spec):
    bpy.ops.mesh.primitive_plane_add(size=spec["road_size"], location=(0, 0, 0))
    plane = bpy.context.object
    plane.name = "V5_Road"
    material = bpy.data.materials.new("V5_Road_M")
    material.use_nodes = True
    tree = material.node_tree
    for node in list(tree.nodes):
        if node.type != "OUTPUT_MATERIAL":
            tree.nodes.remove(node)
    output = tree.nodes["Material Output"]
    shader = tree.nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Base Color"].default_value = spec["road_colour"]
    shader.inputs["Metallic"].default_value = 0.0
    noise = tree.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = spec["wet_scale"]
    noise.inputs["Detail"].default_value = 8.0
    ramp = tree.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = spec["wet_ramp"][0]
    ramp.color_ramp.elements[0].color = (spec["road_wet_roughness"],) * 3 + (1,)
    ramp.color_ramp.elements[1].position = spec["wet_ramp"][1]
    ramp.color_ramp.elements[1].color = (spec["road_dry_roughness"],) * 3 + (1,)
    tree.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    tree.links.new(ramp.outputs["Color"], shader.inputs["Roughness"])
    fine = tree.nodes.new("ShaderNodeTexNoise")
    fine.inputs["Scale"].default_value = spec["wet_scale"] * 42.0
    bump = tree.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.04
    tree.links.new(fine.outputs["Fac"], bump.inputs["Height"])
    tree.links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    tree.links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    plane.data.materials.append(material)
    return plane


def ridgeline(scene, spec):
    """Mountain silhouettes: vertical curtains whose crest is a summed sine
    profile, placed in view space so they span the frame."""
    made = []
    for index, layer in enumerate(spec["ridges"]):
        mesh = bpy.data.meshes.new(f"V5_Ridge_{index:02d}")
        columns = layer["columns"]
        vertices, faces = [], []
        for column in range(columns):
            t = column / float(columns - 1)
            u = -layer["width"] / 2.0 + layer["width"] * t
            profile = (0.55
                       + 0.30 * math.sin(t * math.pi * layer["freq"]
                                         + layer["phase"])
                       + 0.13 * math.sin(t * math.pi * layer["freq"] * 2.3
                                         + layer["phase"] * 1.7)
                       + 0.06 * math.sin(t * math.pi * layer["freq"] * 4.7
                                         + layer["phase"] * 0.4))
            top = layer["height"] * max(0.04, profile)
            vertices.append((u, 0.0, 0.0))
            vertices.append((u, 0.0, top))
        for column in range(columns - 1):
            base = column * 2
            faces.append((base, base + 1, base + 3, base + 2))
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        obj = bpy.data.objects.new(f"V5_Ridge_{index:02d}", mesh)
        obj.location = place(layer["u"], layer["v"], 0.0)
        # Local +Y must map onto the view direction, so the rotation is the
        # negative azimuth: rotating by +azimuth would swing every ridge about
        # 100 degrees off the frame and show its side edge instead of a skyline.
        obj.rotation_euler = (0.0, 0.0,
                              -FRAME["azimuth_deg"] * math.pi / 180.0)
        scene.collection.objects.link(obj)
        material = bpy.data.materials.new(f"V5_Ridge_M_{index:02d}")
        material.use_nodes = True
        shader = material.node_tree.nodes["Principled BSDF"]
        shader.inputs["Base Color"].default_value = layer["colour"]
        shader.inputs["Roughness"].default_value = 1.0
        if layer.get("emit"):
            # A vertical gradient inside the ridge: the crest stays dark while
            # the base picks up the city's haze, which is what makes a distant
            # range read as distance instead of as a cut-out.
            coord = material.node_tree.nodes.new("ShaderNodeTexCoord")
            separate = material.node_tree.nodes.new("ShaderNodeSeparateXYZ")
            material.node_tree.links.new(coord.outputs["Generated"],
                                         separate.inputs["Vector"])
            ramp = material.node_tree.nodes.new("ShaderNodeValToRGB")
            ramp.color_ramp.elements[0].position = 0.0
            ramp.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
            ramp.color_ramp.elements[1].position = 0.55
            ramp.color_ramp.elements[1].color = tuple(layer["emit"])
            material.node_tree.links.new(separate.outputs["Z"],
                                         ramp.inputs["Fac"])
            material.node_tree.links.new(ramp.outputs["Color"],
                                         shader.inputs["Emission Color"])
            shader.inputs["Emission Strength"].default_value = layer.get(
                "emit_strength", 0.1)
        obj.data.materials.append(material)
        made.append(obj)
    return made


def city_lights(scene, spec):
    """The lit city: one mesh of camera-facing emissive quads in view space."""
    rng = random.Random(spec["city_seed"])
    families = [(1.00, 0.90, 0.74), (0.74, 0.86, 1.00), (1.00, 0.76, 0.48),
                (0.60, 0.90, 1.00), (0.96, 0.96, 0.96)]
    mesh = bpy.data.meshes.new("V5_City")
    vertices, faces, indices = [], [], []
    for _ in range(spec["city_count"]):
        distance = rng.uniform(spec["city_near"], spec["city_far"])
        u = rng.uniform(-distance * spec["city_spread"],
                        distance * spec["city_spread"]) + spec["city_u"]
        z = rng.uniform(spec["city_z"][0], spec["city_z"][1])
        size = (rng.uniform(*spec["city_size"])
                * (distance / spec["city_size_reference_distance"]))
        family = rng.choices(range(len(families)),
                             weights=spec["city_weights"])[0]
        centre = place(u, distance, z)
        right = FRAME["right"]
        base = len(vertices)
        vertices.extend([
            tuple(centre - right * size + Vector((0, 0, -size))),
            tuple(centre + right * size + Vector((0, 0, -size))),
            tuple(centre + right * size + Vector((0, 0, size))),
            tuple(centre - right * size + Vector((0, 0, size)))])
        faces.append((base, base + 1, base + 2, base + 3))
        indices.append(family)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    for position, face in enumerate(mesh.polygons):
        face.material_index = indices[position]
    obj = bpy.data.objects.new("V5_City", mesh)
    scene.collection.objects.link(obj)
    for family, colour in enumerate(families):
        material = bpy.data.materials.new(f"V5_City_M_{family}")
        material.use_nodes = True
        shader = material.node_tree.nodes["Principled BSDF"]
        shader.inputs["Base Color"].default_value = (0, 0, 0, 1)
        shader.inputs["Emission Color"].default_value = (*colour, 1.0)
        shader.inputs["Emission Strength"].default_value = spec["city_strength"]
        obj.data.materials.append(material)
    made = [obj]
    for index, lamp in enumerate(spec["street_lamps"]):
        centre = place(lamp["u"], lamp["v"], lamp["z"])
        bpy.ops.mesh.primitive_uv_sphere_add(radius=lamp["radius"],
                                             location=tuple(centre))
        item = bpy.context.object
        item.name = f"V5_Lamp_{index:02d}"
        material = bpy.data.materials.new(f"V5_Lamp_M_{index:02d}")
        material.use_nodes = True
        shader = material.node_tree.nodes["Principled BSDF"]
        shader.inputs["Emission Color"].default_value = lamp["colour"]
        shader.inputs["Emission Strength"].default_value = lamp["strength"]
        item.data.materials.append(material)
        made.append(item)
    return made


def light_rig(scene, spec):
    made = []
    for entry in spec["lights"]:
        data = bpy.data.lights.new(entry["name"], type="AREA")
        data.shape = "RECTANGLE"
        data.size = entry["size"][0]
        data.size_y = entry["size"][1]
        data.energy = entry["power"]
        data.color = entry["colour"]
        obj = bpy.data.objects.new(entry["name"], data)
        obj.location = entry["location"]
        direction = Vector(entry["target"]) - Vector(entry["location"])
        obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        scene.collection.objects.link(obj)
        made.append(obj)
    return made


# --------------------------------------------------------------------------
# cameras and framing
# --------------------------------------------------------------------------
def proj(scene, camera, point):
    """World point -> pixel (x, y) at the scene's render resolution."""
    bpy.context.view_layer.update()
    co = world_to_camera_view(scene, camera, Vector(point))
    return (co.x * scene.render.resolution_x,
            (1.0 - co.y) * scene.render.resolution_y)


def environment_camera(scene, spec):
    data = bpy.data.cameras.new("Camera_V5_Environment")
    data.type = "PERSP"
    data.lens = spec["lens_mm"]
    data.sensor_fit = "HORIZONTAL"
    data.clip_start = 0.1
    data.clip_end = 80000.0  # the ridges are kilometres away
    obj = bpy.data.objects.new("Camera_V5_Environment", data)
    obj.location = place(spec["u"], spec["v"], spec["height"])
    target = place(spec["look_u"], spec["look_v"], spec["look_z"])
    direction = target - Vector(obj.location)
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    scene.collection.objects.link(obj)
    return obj


def solve_environment_framing(scene, camera, spec):
    """Put the horizon exactly on the reference row by solving the camera shift
    against the projection of a ground point at infinity."""
    camera.data.shift_x = 0.0
    camera.data.shift_y = 0.0
    far = place(0.0, 1.0e7, 0.0)
    row_a = proj(scene, camera, far)[1]
    camera.data.shift_y = 0.1
    row_b = proj(scene, camera, far)[1]
    slope = (row_b - row_a) / 0.1
    if abs(slope) < 1e-6:
        raise SystemExit("[v5-env] camera shift does not move the horizon")
    target = COMPOSITION["horizon_row_px"]
    camera.data.shift_y = (target - row_a) / slope
    bpy.context.view_layer.update()
    return {"horizon_row_px": proj(scene, camera, far)[1],
            "shift_y": camera.data.shift_y,
            "row_per_shift": slope,
            "target_row_px": target}


def car_silhouette(scene, camera, objects):
    xs, ys = [], []
    for obj in objects:
        matrix = obj.matrix_world
        for vertex in obj.data.vertices:
            x, y = proj(scene, camera, matrix @ vertex.co)
            xs.append(x)
            ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def solve_car_framing(scene, camera, objects):
    """Frozen camera, V5 framing: solve ortho_scale so the car's visible width
    matches the reference, then both shifts so it lands on the reference
    composition. Orthographic projection is linear, so this converges in one
    pass per parameter."""
    camera.data.type = "ORTHO"
    camera.data.clip_start = 0.01
    camera.data.clip_end = 80000.0
    camera.data.shift_x = 0.0
    camera.data.shift_y = 0.0
    camera.data.ortho_scale = HORIZON_CAMERA["ortho_scale"]
    x0, y0, x1, y1 = car_silhouette(scene, camera, objects)
    width = x1 - x0
    camera.data.ortho_scale *= width / COMPOSITION["car_visible_width_px"]
    x0, y0, x1, y1 = car_silhouette(scene, camera, objects)
    width = x1 - x0
    # shift_x is in canvas-width units; shift_y is in the same units, which for
    # a 4:1 canvas is 4x the pixel offset. Both are solved from measurements.
    base_shift_x, base_shift_y = camera.data.shift_x, camera.data.shift_y
    camera.data.shift_x = base_shift_x + 0.05
    dx = car_silhouette(scene, camera, objects)[2] - x1
    camera.data.shift_x = base_shift_x
    camera.data.shift_y = base_shift_y + 0.05
    dy = car_silhouette(scene, camera, objects)[3] - y1
    camera.data.shift_y = base_shift_y
    centre_x = (x0 + x1) / 2.0
    camera.data.shift_x += (COMPOSITION["car_centre_x_px"] - centre_x) \
        / (dx / 0.05)
    camera.data.shift_y += (COMPOSITION["car_ground_contact_y_px"] - y1) \
        / (dy / 0.05)
    x0, y0, x1, y1 = car_silhouette(scene, camera, objects)
    return {"ortho_scale": camera.data.ortho_scale,
            "shift_x": camera.data.shift_x, "shift_y": camera.data.shift_y,
            "projected_box_px": [round(v, 1) for v in (x0, y0, x1, y1)],
            "projected_width_px": round(x1 - x0, 1),
            "projected_centre_x_px": round((x0 + x1) / 2.0, 1),
            "projected_contact_y_px": round(y1, 1),
            "target": COMPOSITION}


# --------------------------------------------------------------------------
# render helpers
# --------------------------------------------------------------------------
def configure_render(scene, samples, transparent, resolution):
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA" if transparent else "RGB"
    scene.render.film_transparent = transparent
    scene.cycles.samples = samples


def render_to(scene, path):
    scene.render.filepath = path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.render.render(write_still=True)
    return path


def default_spec():
    return {
        "sky_stops": [
            [0.00, (0.007, 0.011, 0.019, 1.0)],
            [0.30, (0.011, 0.016, 0.027, 1.0)],
            [0.44, (0.021, 0.030, 0.046, 1.0)],
            [0.52, (0.034, 0.040, 0.052, 1.0)],
            [0.58, (0.050, 0.051, 0.058, 1.0)],
            [0.66, (0.018, 0.023, 0.032, 1.0)],
            [1.00, (0.009, 0.012, 0.017, 1.0)],
        ],
        "sky_strength": 0.8,
        "ridge_profile": {"base": 0.55, "octaves": [[0.34, 1.0], [0.16, 2.3],
                                                    [0.08, 4.7]]},
        "road_size": 9000.0,
        "road_colour": (0.012, 0.015, 0.021, 1.0),
        "road_wet_roughness": 0.08,
        "road_dry_roughness": 0.40,
        "wet_scale": 0.03,
        "wet_ramp": [0.36, 0.88],
        "city_seed": 11,
        "city_count": 620,
        "city_near": 700.0,
        "city_far": 4200.0,
        "city_u": 0.0,
        "city_spread": 0.70,
        "city_z": [0.2, 5.0],
        "city_size": [0.5, 1.8],
        "city_size_reference_distance": 2200.0,
        "city_strength": 12.0,
        "city_weights": [0.30, 0.24, 0.16, 0.10, 0.20],
        "ridges": [
            {"u": -1800.0, "v": 9000.0, "width": 24000.0, "height": 430.0,
             "columns": 320, "freq": 4.0, "phase": 1.9,
             "colour": (0.011, 0.016, 0.024, 1.0),
             "emit": (0.048, 0.066, 0.094, 1.0), "emit_strength": 0.30},
            {"u": 2200.0, "v": 5200.0, "width": 14000.0, "height": 245.0,
             "columns": 280, "freq": 5.5, "phase": 0.6,
             "colour": (0.007, 0.011, 0.017, 1.0),
             "emit": (0.028, 0.040, 0.058, 1.0), "emit_strength": 0.18},
            {"u": -2400.0, "v": 3000.0, "width": 8000.0, "height": 96.0,
             "columns": 240, "freq": 7.0, "phase": 2.4,
             "colour": (0.004, 0.007, 0.011, 1.0)},
        ],
        "street_lamps": [
            {"u": -22.0, "v": 96.0, "z": 4.9, "radius": 0.18,
             "colour": (1.0, 0.86, 0.66, 1.0), "strength": 90.0},
            {"u": 20.0, "v": 150.0, "z": 4.9, "radius": 0.20,
             "colour": (1.0, 0.84, 0.62, 1.0), "strength": 95.0},
            {"u": -30.0, "v": 260.0, "z": 5.0, "radius": 0.22,
             "colour": (1.0, 0.86, 0.68, 1.0), "strength": 95.0},
            {"u": 34.0, "v": 400.0, "z": 5.0, "radius": 0.24,
             "colour": (1.0, 0.84, 0.64, 1.0), "strength": 95.0},
        ],
        "lights": [
            {"name": "V5_Key", "location": (-7.5, -5.0, 7.5),
             "target": (0.0, -0.2, 0.8), "size": [7.0, 4.0],
             "power": 2400.0, "colour": (1.0, 0.97, 0.93)},
            {"name": "V5_Sky", "location": (-2.0, -1.0, 14.0),
             "target": (0.0, 0.0, 0.6), "size": [18.0, 18.0],
             "power": 520.0, "colour": (0.70, 0.79, 0.95)},
            {"name": "V5_Rim", "location": (3.2, 6.0, 3.4),
             "target": (0.0, -0.6, 0.9), "size": [4.0, 2.0],
             "power": 900.0, "colour": (0.78, 0.87, 1.0)},
            {"name": "V5_Fill", "location": (-4.0, -8.0, 1.6),
             "target": (0.0, -0.4, 0.7), "size": [6.0, 3.0],
             "power": 300.0, "colour": (0.86, 0.90, 1.0)},
        ],
        "environment_camera": {
            "lens_mm": 35.0, "height": 1.80, "u": 0.0, "v": 0.0,
            "look_u": 0.0, "look_v": 26.0, "look_z": 1.05,
        },
    }


def main():
    start = time.time()
    args = parse_args()
    width, height = (int(value) for value in args.resolution.lower().split("x"))
    global CANVAS
    CANVAS = (width, height)
    spec = default_spec()
    scene = open_master(args.master)
    report = {"schema": "horizon-v5-environment v1",
              "master": os.path.relpath(args.master, REPO_ROOT),
              "resolution": [width, height], "samples": args.samples,
              "view_frame": {key: list(round(v, 5) for v in value)
                             if isinstance(value, Vector) else round(value, 4)
                             for key, value in FRAME.items()},
              "composition": COMPOSITION, "stages": args.stages.split(","),
              "renders": {}, "timings_s": {}}
    report["studio_hidden"] = hide_studio(scene)
    night_world(scene, spec)
    road_obj = road(scene, spec)
    ridges = ridgeline(scene, spec)
    city = city_lights(scene, spec)
    rig = light_rig(scene, spec)
    environment = [road_obj] + ridges + city
    car = car_objects()

    env_camera = environment_camera(scene, spec["environment_camera"])
    car_camera = bpy.data.objects[HORIZON_CAMERA["name"]]
    scene.camera = env_camera
    configure_render(scene, args.samples, False, (width, height))
    report["environment_framing"] = solve_environment_framing(
        scene, env_camera, spec["environment_camera"])
    report["car_framing"] = solve_car_framing(scene, car_camera, car)
    if args.dry_run:
        print("[v5-env] dry run " + json.dumps(
            {"environment": report["environment_framing"],
             "car": report["car_framing"]}))
        return 0

    stages = set(args.stages.split(","))
    if "plate" in stages:
        scene.camera = env_camera
        configure_render(scene, args.samples, False, (width, height))
        set_rays(car, camera=False, diffuse=False, glossy=False,
                 transmission=False, shadow=False, volume_scatter=False)
        # The car rig is a studio rig: it exists to light the car, and its
        # reflection in the road is not part of the place the car stands in.
        for obj in rig:
            obj.hide_render = True
        started = time.time()
        plate = os.path.join(args.ui, "horizon_v5_background.png")
        render_to(scene, plate)
        report["timings_s"]["plate"] = round(time.time() - started, 1)
        report["renders"]["plate"] = os.path.relpath(plate, REPO_ROOT)
        for obj in rig:
            obj.hide_render = False
        set_rays(car, camera=True, diffuse=True, glossy=True,
                 transmission=True, shadow=True, volume_scatter=True)

    if "road" in stages or "car" in stages:
        scene.camera = car_camera
        for obj in environment:
            set_rays([obj], camera=False)
        set_rays(rig, camera=False)
        if "road" in stages:
            # The road alone: the reference the car's ground response is
            # measured against. Rendered once, because it is state independent.
            configure_render(scene, args.samples, False, (width, height))
            set_rays([road_obj], camera=True)
            # The car has to leave the road completely: `camera=False` alone
            # still lets it reflect in the wet surface, which would cancel the
            # very response this pass exists to measure.
            set_rays(car, camera=False, glossy=False, diffuse=False,
                     shadow=False, transmission=False, volume_scatter=False)
            started = time.time()
            path = os.path.join(args.out, "road", "no_car.png")
            render_to(scene, path)
            report["timings_s"]["road_no_car"] = round(time.time() - started, 1)
            report["renders"]["road_no_car"] = os.path.relpath(path, REPO_ROOT)
            set_rays(car, camera=True, glossy=True, diffuse=True, shadow=True,
                     transmission=True, volume_scatter=True)
        if "car" in stages:
            state_assets.setup_horizon_camera(scene)
            car_camera = bpy.data.objects[HORIZON_CAMERA["name"]]
            # Re-apply the V5 framing: setup_horizon_camera resets the camera.
            report["car_framing"] = solve_car_framing(scene, car_camera, car)
            scene.camera = car_camera
            for name in args.states.split(","):
                state = {"base": "OFF", "running": "HEADLIGHT",
                         "brake": "BRAKE", "headlight": "FRONT",
                         "indicator_left": "LEFT_INDICATOR",
                         "indicator_right": "RIGHT_INDICATOR",
                         "hazard": "HAZARD"}[name]
                started = time.time()
                if state == "FRONT":
                    state_assets.render_headlight_overlay(
                        scene, os.path.join(args.out, "car"), args.samples)
                    source = os.path.join(args.out, "car", "headlight_on",
                                          "000.png")
                    target = os.path.join(args.out, "car", name, "000.png")
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    os.replace(source, target)
                else:
                    state_assets.render_lighting_state(
                        scene, os.path.join(args.out, "car"), name, state,
                        args.samples, "FIXED_BODY")
                    source = os.path.join(args.out, "car", name, "000.png")
                report["renders"][f"car_{name}"] = os.path.relpath(source,
                                                                   REPO_ROOT)

                # Road with the car: same camera, same lighting, wet surface.
                set_rays([road_obj], camera=True)
                set_rays(car, camera=True, glossy=True, shadow=True,
                         diffuse=True)
                configure_render(scene, args.samples, False, (width, height))
                road_path = os.path.join(args.out, "road", f"{name}.png")
                render_to(scene, road_path)
                report["renders"][f"road_{name}"] = os.path.relpath(
                    road_path, REPO_ROOT)
                report["timings_s"][f"state_{name}"] = round(
                    time.time() - started, 1)
                # Car-only pass: clean alpha, environment out of the camera ray.
                configure_render(scene, args.samples, True, (width, height))
                set_rays([road_obj], camera=False)
                car_path = os.path.join(args.out, "car", name, "000.png")
                render_to(scene, car_path)
                report["renders"][f"car_{name}_alpha"] = os.path.relpath(
                    car_path, REPO_ROOT)

    report["elapsed_s"] = round(time.time() - start, 1)
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w") as handle:
        json.dump(report, handle, indent=1)
        handle.write("\n")
    print(f"[v5-env] timings {json.dumps(report['timings_s'])}")
    print(f"[v5-env] environment framing "
          f"{json.dumps(report['environment_framing'])}")
    print(f"[v5-env] car framing {json.dumps(report['car_framing'])}")
    print(f"[v5-env] report {os.path.relpath(args.report, REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
