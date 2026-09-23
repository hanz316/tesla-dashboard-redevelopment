#!/usr/bin/env python3
"""Layout QA for Horizon V2, without eyes.

Every check here exists because the author cannot look at the result. The
checks that matter are the ones a screenshot would reveal to a human: something
moved off the panel, the car got clipped, the speed landed on the vehicle, two
labels landed on each other, debug text leaked into the driving screen, or an
unknown value was drawn as a number.

Run standalone, or through tests/horizon_v2_tests.py:
    python3 tools/preview/horizon_v2_layout_qa.py
"""

import glob
import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

LAYOUT = os.path.join(REPO, "assets", "ui", "horizon_v2_layout.json")
TOKENS = os.path.join(REPO, "assets", "ui", "design_tokens.json")
SCENE = os.path.join(REPO, "scenes", "horizon_v2.scene")
VEHICLE_ROOT = os.path.join(REPO, "assets", "rendered", "vehicle")

FAILURES = []
NOTES = []

try:
    from PIL import Image, ImageDraw

    HAVE_PIL = True
except ImportError:  # pragma: no cover - CI images without Pillow
    HAVE_PIL = False


def load(path):
    with open(path) as fh:
        return json.load(fh)


def check(condition, label):
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}")
        FAILURES.append(label)
    return condition


def note(label):
    NOTES.append(label)
    print(f"  note {label}")


def rect(source):
    b = source["bounds"] if "bounds" in source else source
    return (b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"])


def overlaps(a, b):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return not (ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0)


def panel_cut(y, layout):
    top = layout["panel"]["top_corner_cut"]
    bottom = layout["panel"]["bottom_corner_cut"]
    return top + (bottom - top) * (float(y) / layout["canvas"]["height"])


def invalid_hidden(node):
    return node.get("invalid_alpha", 1.0) <= 0.0 or node.get("invalid_text", "") == ""


def text_boxes(scene, state, previewer):
    """Ink boxes for every text node that is actually drawn in this state."""
    scratch = Image.new("RGBA", (scene["canvas"]["width"],
                                 scene["canvas"]["height"]))
    draw = ImageDraw.Draw(scratch)
    boxes = {}
    for node in scene["nodes"]:
        if node["type"] != "text":
            continue
        text, valid = previewer.resolve_value(node, state)
        alpha = previewer.alpha_when(node, state)
        if not valid:
            text = node.get("invalid_text", text)
            alpha *= node.get("invalid_alpha", 1.0)
        if not text or alpha <= 0.001:
            continue
        font = previewer.load_font(node.get("font", 32), node.get("bold", False),
                                   node.get("font_role"))
        anchor = {"center": "mm", "left": "lm", "right": "rm"}.get(
            node.get("align", "center"), "mm")
        box = draw.textbbox((node.get("x", 0), node.get("y", 0)), text,
                            font=font, anchor=anchor)
        boxes[node["id"]] = (box[0] - 1, box[1] - 1, box[2] + 1, box[3] + 1)
    return boxes


def check_golden(scene, layout, components, check):
    print("golden source")
    check(scene["provenance"]["layout"] == "assets/ui/horizon_v2_layout.json",
          "the scene names this layout as its source")
    check([n["id"] for n in scene["nodes"]] == [c["id"] for c in layout["components"]],
          "the scene has exactly the layout's components, in order")
    for node in scene["nodes"]:
        bounds = components[node["id"]]["bounds"]
        if node["type"] != "text":
            continue
        align = node["align"]
        expected_x = bounds["x"] if align == "left" else (
            bounds["x"] + bounds["w"] if align == "right"
            else bounds["x"] + bounds["w"] / 2)
        expected_y = bounds["y"] + bounds["h"] / 2
        check(abs(node["x"] - round(expected_x, 1)) < 0.2 and
              abs(node["y"] - round(expected_y, 1)) < 0.2,
              f"{node['id']}: scene position matches the layout bounds")


def check_tokens(scene, tokens, check):
    print("tokens")
    allowed_colors = set(tokens["colors"].values())
    allowed_sizes = {t["size"] for t in tokens["typography"]["tiers"].values()}
    for node in scene["nodes"]:
        for key in ("color", "fill", "stroke", "from", "to"):
            value = node.get(key)
            if isinstance(value, str) and value.startswith("#"):
                check(value in allowed_colors,
                      f"{node['id']}.{key} comes from design_tokens.json")
        for rule in (node.get("progress") or {}).get("color_when", []):
            check(rule["color"] in allowed_colors,
                  f"{node['id']} progress colour comes from design_tokens.json")
        if node["type"] == "text":
            check(node["size"] in allowed_sizes,
                  f"{node['id']}.size is a typography token")


def check_bounds(layout, components, check):
    print("bounds")
    canvas = layout["canvas"]
    safe = layout["safe_area"]
    for component in layout["components"]:
        if component.get("exempt_from_safe_area"):
            continue
        x0, y0, x1, y1 = rect(component)
        check(x0 >= 0 and y0 >= 0 and x1 <= canvas["width"] and
              y1 <= canvas["height"], f"{component['id']} is inside the canvas")
        check(x0 >= safe["left"] and y0 >= safe["top"] and
              x1 <= canvas["width"] - safe["right"] and
              y1 <= canvas["height"] - safe["bottom"],
              f"{component['id']} is inside the safe area")
        check(all(x0 >= panel_cut(y, layout) and
                  x1 <= canvas["width"] - panel_cut(y, layout)
                  for y in (y0, y1)),
              f"{component['id']} is clear of the panel mask")


def check_zones(layout, components, check):
    print("zones")
    canvas = layout["canvas"]
    driver_zone = (layout["zones"]["driver"]["x"], 0,
                   layout["zones"]["driver"]["right"], canvas["height"])
    energy_zone = (layout["zones"]["energy"]["x"], 0,
                   layout["zones"]["energy"]["right"], canvas["height"])
    vehicle = components["vehicle"]
    car_closed = rect(vehicle["visible_bounds_closed"])
    car_open = rect(vehicle["visible_bounds_open_union"])
    permitted = rect(vehicle["permitted_region"])
    check(not overlaps(rect(components["speed.value"]), car_closed),
          "the speed does not overlap the car")
    check(not overlaps(rect(components["speed.value"]), car_open),
          "the speed does not overlap the car even with its panels open")
    check(not overlaps(car_closed, rect(components["range.value"])),
          "the car does not overlap the range")
    check(not overlaps(car_closed, rect(components["soc.bar.track"])),
          "the car does not overlap the SOC bar")
    check(not overlaps(car_open, energy_zone),
          "the car stays out of the energy column with its panels open")
    check(not overlaps(car_open, driver_zone),
          "the car stays out of the driver column with its panels open")
    nav_pill = rect(components["nav.pill"])
    for other in ("top.temperature", "top.clock"):
        check(not overlaps(nav_pill, rect(components[other])),
              f"the navigation pill does not overlap {other}")
    return car_closed, car_open, permitted


def check_vehicle(layout, tokens, car_closed, car_open, permitted, check):
    print("vehicle")
    canvas = layout["canvas"]
    safe = layout["safe_area"]
    check(car_closed[0] >= permitted[0] and car_closed[2] <= permitted[2] and
          car_closed[1] >= permitted[1] and car_closed[3] <= permitted[3],
          "the closed car is inside its permitted region")
    check(car_open[0] >= permitted[0] and car_open[2] <= permitted[2] and
          car_open[1] >= permitted[1] and car_open[3] <= permitted[3],
          "the car with every panel open is inside its permitted region")
    check(car_closed[1] >= safe["top"] and
          car_closed[3] <= canvas["height"] - safe["bottom"],
          "the closed car is inside the safe area")
    check(car_open[1] >= safe["top"] and
          car_open[3] <= canvas["height"] - safe["bottom"],
          "the car with every panel open is inside the safe area")

    if not HAVE_PIL:
        note("Pillow is absent: the Model A alpha-bbox drift check is skipped "
             "(the golden numbers in design_tokens.json still apply)")
        return
    if not os.path.isdir(VEHICLE_ROOT):
        note("vehicle renders are absent; the golden bounding boxes in "
             "design_tokens.json still apply")
        return
    def bbox_of(path):
        return Image.open(path).convert("RGBA").getchannel("A").getbbox()

    measurements = tokens["vehicle"]["measurements"]
    base = bbox_of(os.path.join(VEHICLE_ROOT, "base", "000.png"))
    check(list(base) == measurements["closed_bbox"],
          f"the closed car bounding box is unchanged {list(base)}")
    union = None
    patterns = ["base/000.png", "brake_on/000.png", "headlight_on/000.png",
                "running_on/000.png"]
    patterns += [f"door_{side}/*.png" for side in ("fl", "fr", "rl", "rr")]
    patterns += ["frunk/*.png", "trunk/*.png", "indicator_left/*.png",
                 "indicator_right/*.png", "trunk/ind_left/*.png",
                 "trunk/ind_right/*.png", "trunk/ind_both/*.png"]
    for pattern in patterns:
        for path in sorted(glob.glob(os.path.join(VEHICLE_ROOT, pattern)))[-1:]:
            bbox = bbox_of(path)
            if bbox is None:
                continue
            union = bbox if union is None else [
                min(union[0], bbox[0]), min(union[1], bbox[1]),
                max(union[2], bbox[2]), max(union[3], bbox[3])]
    check(list(union) == measurements["open_union_bbox"],
          f"the open-panel union is unchanged {list(union)}")


def check_debug(scene, layout, check):
    print("debug isolation")
    offenders = []
    for node in scene["nodes"]:
        parts = [str(node.get("id", "")), str(node.get("text", "")),
                 str(node.get("bind", "")), str(node.get("invalid_text", ""))]
        for rule in node.get("text_when", []):
            parts.append(str(rule.get("text", "")))
        blob = " ".join(parts).lower()
        for token in layout["forbidden_in_production"]:
            if token.lower() in blob:
                offenders.append(f"{node['id']}~{token}")
    check(not offenders,
          f"no link, source or protocol text on the screen ({offenders})")


def check_text(scene, previewer, check):
    print("text collisions")
    if previewer is None or not HAVE_PIL:
        note("Pillow is absent: text collision measurement is skipped")
        return
    for state_name in ("h2_neutral", "h2_unknown", "h2_low_soc", "h2_navigation"):
        state = previewer.State(previewer.MOCK_STATES[state_name])
        boxes = text_boxes(scene, state, previewer)
        ids = sorted(boxes)
        collisions = []
        for index, first in enumerate(ids):
            for second in ids[index + 1:]:
                if overlaps(boxes[first], boxes[second]):
                    collisions.append(f"{first}/{second}")
        check(not collisions,
              f"no two texts collide in {state_name} ({collisions})")


def check_unknown(scene, previewer, check):
    print("unknown behaviour")
    if previewer is None:
        # Without the previewer the value resolution cannot be replayed, so the
        # rule is checked where it is written instead: every bound text must
        # carry a placeholder, and that placeholder must not be a number.
        offenders = []
        for node in scene["nodes"]:
            if node["type"] != "text" or not node.get("bind"):
                continue
            if invalid_hidden(node):
                continue  # design says: hide the whole element when unknown
            placeholder = node.get("invalid_text", "")
            if placeholder == "" or any(c.isdigit() for c in placeholder):
                offenders.append(f"{node['id']}={placeholder!r}")
        check(not offenders,
              f"every bound value states a non-numeric placeholder ({offenders})")
        note("the previewer is unavailable here: the unknown-state replay is "
             "skipped")
        return
    unknown = previewer.State(previewer.MOCK_STATES["h2_unknown"])
    fakes = []
    for node in scene["nodes"]:
        if node["type"] != "text" or not node.get("bind"):
            continue
        text, valid = previewer.resolve_value(node, unknown)
        if valid or invalid_hidden(node):
            continue
        if text != node.get("invalid_text", text):
            fakes.append(f"{node['id']}={text!r}")
        elif any(character.isdigit() for character in text):
            fakes.append(f"{node['id']} drew digits {text!r}")
    check(not fakes, f"every bound value falls back to its placeholder ({fakes})")
    if HAVE_PIL:
        neutral = previewer.State(previewer.MOCK_STATES["h2_neutral"])
        check(text_boxes(scene, unknown, previewer) !=
              text_boxes(scene, neutral, previewer),
              "the unknown screen is not the same screen as the neutral one")
    else:
        note("Pillow is absent: the unknown-vs-neutral comparison is skipped "
             "(the placeholder rule above is still enforced)")


def main():
    layout = load(LAYOUT)
    tokens = load(TOKENS)
    scene = load(SCENE)

    try:
        import scene_preview as previewer
    except (ImportError, SystemExit) as error:
        # The previewer needs Pillow, and exits with a message rather than
        # raising when it is missing. The geometric checks below do not need it.
        previewer = None
        note(f"the previewer is unavailable here ({error}); its checks are "
             f"skipped, the geometry checks still run")

    components = {c["id"]: c for c in layout["components"]}
    check_golden(scene, layout, components, check)
    check_tokens(scene, tokens, check)
    check_bounds(layout, components, check)
    car_closed, car_open, permitted = check_zones(layout, components, check)
    check_vehicle(layout, tokens, car_closed, car_open, permitted, check)
    check_debug(scene, layout, check)
    check_text(scene, previewer, check)
    check_unknown(scene, previewer, check)

    print("")
    if FAILURES:
        print(f"{len(FAILURES)} FAILED:")
        for failure in FAILURES:
            print(f"  {failure}")
        return 1
    print("all horizon v2 layout checks passed")
    for entry in NOTES:
        print(f"  note: {entry}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
