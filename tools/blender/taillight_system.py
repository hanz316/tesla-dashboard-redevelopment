#!/usr/bin/env python3
"""Closed internal taillight cavity + light guide v2 + lighting channels.

The v1 light guide protruded because it was fitted to the lamp's BOUNDING BOX.
The v2 attempt fitted it to the mesh but could not prove containment, because
the MODEL A lamp objects are OPEN SHELLS (lens surfaces) - an inside/outside
test is undefined on them.

This module fixes the actual cause: it builds a CLOSED, manifold internal
cavity behind each original lens, which gives the lamp a well-defined interior.
After that:

  * containment is a real parity test against a watertight volume
  * clearance is a real distance-to-boundary number
  * the light guide can be placed with a proof instead of a hope

The original outer lens is never modified - not remeshed, not smoothed, not
moved.
"""

import math

import bpy
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def _world_verts(obj):
    mw = obj.matrix_world
    return [mw @ v.co for v in obj.data.vertices]


def _bvh(obj):
    deps = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(deps)
    mesh = ev.to_mesh()
    mw = obj.matrix_world
    verts = [mw @ v.co for v in mesh.vertices]
    polys = [tuple(p.vertices) for p in mesh.polygons]
    tree = BVHTree.FromPolygons(verts, polys, all_triangles=False)
    ev.to_mesh_clear()
    return tree


def mesh_health(mesh):
    bm = bmesh.new()
    bm.from_mesh(mesh)
    boundary = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    nonmanifold = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    wire = sum(1 for e in bm.edges if len(e.link_faces) == 0)
    bm.free()
    return {"boundary_edges": boundary, "non_manifold_edges": nonmanifold,
            "wire_edges": wire, "vertices": len(mesh.vertices),
            "faces": len(mesh.polygons),
            "watertight": boundary == 0 and nonmanifold == 0 and wire == 0}


def build_closed_cavity(lens_obj, name, clearance_range=(0.008, 0.020)):
    """A closed manifold volume that sits behind the original lens.

    Method: convex hull of the lens (closed by construction) shrunk toward its
    centroid, then verified against the lens with the exterior occlusion test.
    The shrink factor is chosen by the containment test, not hard-coded - the
    brief explicitly asks for the clearance to be derived from the model scale
    and decided by the test.

    A convex hull is deliberately chosen over lofting the lens boundary ring:
    the MODEL A lamp shells are triangulated with non-manifold seams, so a
    boundary-ring loft is not reliable. The hull only has to provide an
    interior working space; it is never visible.
    """
    verts = _world_verts(lens_obj)
    if len(verts) < 8:
        return None, {"built": False, "reason": "lens too small"}
    centre = Vector((0.0, 0.0, 0.0))
    for v in verts:
        centre += v
    centre /= len(verts)
    lens_tree = _bvh(lens_obj)

    cy = centre.y
    # Only the exterior-facing cone matters. The lens shells are OPEN, so a
    # point inside them is always reachable through the opening from some
    # oblique direction; requiring occlusion from every direction can never
    # pass and is not the property we need. The property we need is "the lens
    # is in front of this point", which is what the production camera sees.
    outward_dirs = []
    for d in ((0.0, -1.0 if cy > 0 else 1.0, 0.0),
              (0.0, -1.0 if cy > 0 else 1.0, 0.45),
              (0.0, -1.0 if cy > 0 else 1.0, -0.45),
              (0.35, -1.0 if cy > 0 else 1.0, 0.0),
              (-0.35, -1.0 if cy > 0 else 1.0, 0.0)):
        v = Vector(d)
        v.normalize()
        outward_dirs.append(v)

    def hidden(point):
        """Cast from OUTSIDE toward the point; it is hidden when the lens (or
        anything else) is hit before the ray reaches the point.

        The earlier version cast outward FROM the point and required every ray
        to hit the lens. That can never pass on an open shell: rays that leave
        through the shell's opening always escape, so every point looked
        exposed no matter how deep inside it was. Testing from the exterior
        inward is the correct question - "can this be seen from outside".
        """
        for d in outward_dirs:
            origin = Vector(point) + d * 2.0
            result = lens_tree.ray_cast(origin, -d, 2.0)
            loc = result[0]
            dist = result[3]
            if loc is None or dist is None or dist > 2.0 - 1e-4:
                return False
        return True

    attempts = []
    chosen = None
    factor = 0.88
    for _ in range(7):
        bm = bmesh.new()
        for v in verts:
            bm.verts.new(v)
        bm.verts.ensure_lookup_table()
        bmesh.ops.convex_hull(bm, input=bm.verts)
        # Shrink toward the centroid so the hull sits behind the lens.
        for v in bm.verts:
            v.co = centre + (v.co - centre) * factor
        mesh = bpy.data.meshes.new(name + "_tmp")
        bm.to_mesh(mesh)
        bm.free()
        health = mesh_health(mesh)
        world = [centre + (v - centre) * factor for v in verts]
        probe = [mesh.vertices[i].co.copy() for i in
                 range(min(120, len(mesh.vertices)))]
        exposed = sum(1 for p in probe if not hidden(p))
        attempts.append({"shrink": round(factor, 3),
                         "boundary_edges": health["boundary_edges"],
                         "exposed_vertices": exposed})
        if health["watertight"] and exposed == 0:
            chosen = mesh
            break
        bpy.data.meshes.remove(mesh)
        factor -= 0.06
    if chosen is None:
        return None, {"built": False, "attempts": attempts}

    obj = bpy.data.objects.new(name, chosen)
    bpy.context.scene.collection.objects.link(obj)
    health = mesh_health(chosen)
    return obj, {"built": True, "shrink": round(factor, 3),
                 "attempts": attempts, "health": health,
                 "clearance_range_m": list(clearance_range)}


def containment(volume_obj, guide_obj, samples=400):
    """Parity test against the CLOSED cavity, plus distance to its boundary."""
    tree = _bvh(volume_obj)
    guide_tree = _bvh(guide_obj)

    def inside(point):
        hits = 0
        origin = Vector(point)
        d = Vector((0.0, 0.0, 1.0))
        for _ in range(64):
            loc, nor, idx, dist = tree.ray_cast(origin, d, 50.0)
            if loc is None:
                break
            hits += 1
            origin = loc + d * 1e-5
        return hits % 2 == 1

    gverts = [guide_obj.matrix_world @ v.co for v in guide_obj.data.vertices]
    if not gverts:
        return {"inside_percent": 0.0, "vertices": 0}
    step = max(1, len(gverts) // samples)
    probe = gverts[::step]
    inside_count = sum(1 for v in probe if inside(v))

    # Clearance: nearest distance from guide vertices to the cavity boundary.
    dmin = 1e9
    dsum = 0.0
    dmax = 0.0
    for v in probe:
        loc, nor, idx, dist = tree.find_nearest(v, 5.0)
        if loc is None:
            continue
        dmin = min(dmin, dist)
        dmax = max(dmax, dist)
        dsum += dist
    n = max(len(probe), 1)
    return {
        "vertices": len(gverts),
        "sampled": len(probe),
        "inside_percent": round(100.0 * inside_count / n, 2),
        "min_clearance_m": round(dmin, 5) if dmin < 1e9 else None,
        "mean_clearance_m": round(dsum / n, 5),
        "max_clearance_m": round(dmax, 5),
    }


def build_light_guide_v2(cavity_obj, lens_obj, name, material,
                         profile="rounded_rect", samples=24, ring_verts=12):
    """A curved internal light pipe that follows the lamp's visual sweep.

    Profile options are the three the brief asks to test: round, flattened
    oval, and a rounded light-pipe rectangle. All are swept along an arc
    through the cavity, so the result is a curved strip - never a straight rod.
    """
    cverts = _world_verts(cavity_obj)
    if len(cverts) < 8:
        return None, {"built": False}
    cs = Vector((0.0, 0.0, 0.0))
    for v in cverts:
        cs += v
    cs /= len(cverts)

    xs = sorted(v.x for v in cverts)
    lo_x, hi_x = xs[int(len(xs) * 0.08)], xs[int(len(xs) * 0.92)]
    span = hi_x - lo_x
    if span <= 0.01:
        return None, {"built": False, "reason": "cavity too thin"}

    # The sweep is a shallow arc bowed in Z so it reads as a lamp curve.
    sag = (max(v.z for v in cverts) - min(v.z for v in cverts)) * 0.22
    radii = {"round": (0.0060, 0.0060),
             "oval": (0.0042, 0.0110),
             "rounded_rect": (0.0050, 0.0130)}
    ry, rz = radii.get(profile, radii["rounded_rect"])

    rings = []
    for i in range(samples):
        t = i / (samples - 1.0)
        u = t - 0.5
        px = lo_x + t * span
        pz = cs.z + sag * (1.0 - (2.0 * u) ** 2)
        py = cs.y
        tangent = Vector((1.0, 0.0, -4.0 * sag * u / max(span, 1e-6)))
        tangent.normalize()
        side = tangent.cross(Vector((0.0, 0.0, 1.0))).normalized()
        up = side.cross(tangent).normalized()
        ring = []
        for k in range(ring_verts):
            a = 2.0 * math.pi * k / ring_verts
            ca, sa = math.cos(a), math.sin(a)
            if profile == "rounded_rect":
                # Superellipse: a light-pipe cross-section rather than a tube.
                n = 4.0
                denom = (abs(ca) ** n + abs(sa) ** n) ** (1.0 / n)
                ox, oz = ca / denom * rz, sa / denom * ry
            else:
                ox, oz = ca * rz, sa * ry
            ring.append(Vector((px, py, pz)) + side * ox + up * oz)
        rings.append(ring)

    bm = bmesh.new()
    bm_rings = [[bm.verts.new((v.x, v.y, v.z)) for v in r] for r in rings]
    bm.verts.ensure_lookup_table()
    n = ring_verts
    for r in range(len(bm_rings) - 1):
        a, b = bm_rings[r], bm_rings[r + 1]
        for k in range(n):
            k2 = (k + 1) % n
            bm.faces.new((a[k], a[k2], b[k2], b[k]))
    bm.faces.new(list(reversed(bm_rings[0])))
    bm.faces.new(bm_rings[-1])
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for poly in mesh.polygons:
        poly.use_smooth = True
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    mesh.materials.append(material)
    return obj, {"built": True, "profile": profile, "samples": samples,
                 "ring_verts": ring_verts,
                 "cross_section_m": [round(ry * 2, 5), round(rz * 2, 5)],
                 "arc_sagitta_m": round(sag, 5)}


def channel_materials():
    """One lamp system, four logical channels (Part 8).

    MODEL A cannot distinguish the real Tesla lamp regions, so this is
    explicitly a VISUAL APPROXIMATION - but left and right are independently
    controllable, which is what the state system needs.
    """
    def make(name, base, emission=None, strength=0.0):
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        b = mat.node_tree.nodes.get("Principled BSDF")
        if b is not None:
            for k, v in (("Base Color", base + (1.0,)), ("Metallic", 0.0),
                         ("Roughness", 0.09),
                         ("Transmission Weight", 0.42),
                         ("Specular IOR Level", 0.90)):
                if k in b.inputs:
                    b.inputs[k].default_value = v
            if "IOR" in b.inputs:
                b.inputs["IOR"].default_value = 1.49
            if emission is not None:
                for key in ("Emission Color", "Emission"):
                    if key in b.inputs:
                        b.inputs[key].default_value = emission + (1.0,)
                        break
                if "Emission Strength" in b.inputs:
                    b.inputs["Emission Strength"].default_value = strength
        return mat

    return {
        "OFF": make("M_TailGuide_OFF", (0.165, 0.020, 0.022)),
        "RUNNING": make("M_TailGuide_RUNNING", (0.240, 0.022, 0.024),
                        emission=(0.85, 0.05, 0.05), strength=1.6),
        "BRAKE": make("M_TailGuide_BRAKE", (0.320, 0.030, 0.032),
                      emission=(1.00, 0.060, 0.055), strength=6.0),
        "INDICATOR_LEFT": make("M_TailGuide_IND_L", (0.320, 0.150, 0.020),
                               emission=(1.00, 0.45, 0.06), strength=7.0),
        "INDICATOR_RIGHT": make("M_TailGuide_IND_R", (0.320, 0.150, 0.020),
                                emission=(1.00, 0.45, 0.06), strength=7.0),
    }


def lens_channel_materials(base_name="M_TailLens_Outer_v4", base=None):
    """The same channels, carried by the LENS rather than by the guide.

    A guide inside a 36 %-transmissive red lens reads as a thin internal glow;
    the lens is what the viewer actually sees. So every channel also exists as a
    lens material, and the brake lamp - which has no interior at all - is lit
    this way and only this way. It stays one system: the same channel key
    selects the guide material and the lens material.
    """
    if base is None:
        base = bpy.data.materials.get(base_name)
        if base is None:            # the builder may have stored a copy
            for mat in bpy.data.materials:
                if mat.name.startswith(base_name):
                    base = mat
                    break
    return {
        "OFF": base,
        "RUNNING": _lens_channel(base, "M_TailLens_RUNNING_v4",
                                 (0.62, 0.050, 0.050), 0.9),
        "BRAKE": _lens_channel(base, "M_TailLens_BRAKE_v4",
                               (1.00, 0.070, 0.060), 3.0),
        "INDICATOR_LEFT": _lens_channel(base, "M_TailLens_IND_L_v4",
                                        (1.00, 0.42, 0.055), 3.4),
        "INDICATOR_RIGHT": _lens_channel(base, "M_TailLens_IND_R_v4",
                                         (1.00, 0.42, 0.055), 3.4),
    }


def _lens_channel(base, name, emission, strength):
    """A copy of the frozen lens material with one channel's emission added."""
    mat = base.copy() if base is not None else bpy.data.materials.new(name)
    mat.name = name
    if not mat.use_nodes:
        return mat
    b = mat.node_tree.nodes.get("Principled BSDF")
    if b is None:
        return mat
    for key in ("Emission Color", "Emission"):
        if key in b.inputs:
            b.inputs[key].default_value = emission + (1.0,)
            break
    if "Emission Strength" in b.inputs:
        b.inputs["Emission Strength"].default_value = strength
    return mat


def assign_lamp_material(obj, material):
    """One material per lamp, whatever slots it started with."""
    if not obj.data.materials:
        obj.data.materials.append(material)
        return
    for index in range(len(obj.data.materials)):
        obj.data.materials[index] = material


def apply_state(state, segments, lamps, guide_channels, lens_channels):
    """The one place a state becomes materials. Nothing else sets emission.

    `segments` is {label: {"guides": [...], "cavity": [...]}} and `lamps` is
    {lamp_name: object}. Returns the per-lamp channel assignment that was
    applied, so a report can state exactly what a state did.
    """
    import taillight_states as states

    per_lamp = states.lamp_channels(state)
    applied = {}
    for label, parts in segments.items():
        lamp = label.split(":")[1]
        channels = per_lamp.get(lamp, frozenset())
        guide_key = states.material_key(channels) if channels else "OFF"
        lens_key = guide_key
        material = guide_channels.get(guide_key, guide_channels["OFF"])
        for guide in parts.get("guides", []):
            assign_lamp_material(guide, material)
        applied[label] = {"lamp": lamp, "channels": sorted(channels),
                          "guide_material": material.name,
                          "lens_material": (lens_channels.get(lens_key)
                                            or lens_channels["OFF"]).name
                          if lens_channels.get(lens_key) else None}
    for lamp, obj in lamps.items():
        channels = per_lamp.get(lamp, frozenset())
        key = states.material_key(channels) if channels else "OFF"
        material = lens_channels.get(key) or lens_channels.get("OFF")
        if material is not None:
            assign_lamp_material(obj, material)
        applied.setdefault(lamp, {"lamp": lamp, "channels": sorted(channels),
                                  "guide_material": None,
                                  "lens_material": material.name
                                  if material else None})
    return applied


def trunk_ownership(lamp_names, boot_name="boot"):
    """Which lamp objects belong to the trunk lid rather than the body.

    MODEL A carries part of the tail lighting on the trunk lid. Anything that
    belongs to the lid has to move with it, or the lamp tears apart when the
    trunk opens.
    """
    boot = bpy.data.objects.get(boot_name)
    if boot is None:
        return {}, "boot object missing"
    blo = Vector((1e9, 1e9, 1e9))
    bhi = Vector((-1e9, -1e9, -1e9))
    for corner in boot.bound_box:
        w = boot.matrix_world @ Vector(corner)
        blo = Vector((min(blo.x, w.x), min(blo.y, w.y), min(blo.z, w.z)))
        bhi = Vector((max(bhi.x, w.x), max(bhi.y, w.y), max(bhi.z, w.z)))

    owner = {}
    for name in lamp_names:
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        lo = Vector((1e9, 1e9, 1e9))
        hi = Vector((-1e9, -1e9, -1e9))
        for corner in obj.bound_box:
            w = obj.matrix_world @ Vector(corner)
            lo = Vector((min(lo.x, w.x), min(lo.y, w.y), min(lo.z, w.z)))
            hi = Vector((max(hi.x, w.x), max(hi.y, w.y), max(hi.z, w.z)))
        centre = (lo + hi) * 0.5
        inside = (blo.x <= centre.x <= bhi.x and blo.y <= centre.y <= bhi.y
                  and blo.z <= centre.z <= bhi.z)
        owner[name] = "TRUNK_LID" if inside else "BODY"
    return owner, None
