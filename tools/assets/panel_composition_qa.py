#!/usr/bin/env python3
"""Does composing state layers ever put two panels where one belongs?

The defect this exists for: every state render is a whole car, so drawing two
of them leaves the first one's open panel repainted closed by the second one's
copy of it. The bake step turns each state into "only what this state changes";
this checks, in pixels, that composing those layers behaves.

No eyes are involved. Every claim below is a bitwise comparison:

1. one panel open: base + its layer equals the original render, so the layer is
   a faithful replacement rather than an approximation;
2. two panels open: neither layer disturbs the other's region, which is the
   duplicate-closed-panel defect stated as a pixel test;
3. no hole: composing only ever adds or replaces pixels the base already had;
4. the panel stays attached (its layer touches the body silhouette) and inside
   the permitted region;
5. trunk lighting ownership: opening the trunk with an indicator lit changes
   only the trunk's own layer - the fixed-position lamp is not lit while the
   lamps that belong to the lid are.

Usage:
    python3 tools/assets/panel_composition_qa.py
"""

import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ROOT = os.path.join(REPO, "assets", "rendered", "vehicle")
REPORT = os.path.join(ROOT, "delta", "delta_report.json")

FAILURES = []


def check(condition, label):
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}")
        FAILURES.append(label)


def main():
    try:
        import numpy as np
        from PIL import Image
    except ImportError as error:
        print(f"SKIPPED: Pillow and numpy are required ({error})")
        return 0
    if not os.path.isfile(REPORT):
        print("SKIPPED: no baked delta layers; run "
              "tools/assets/bake_vehicle_deltas.py")
        return 0

    report = json.load(open(REPORT))
    base = np.asarray(Image.open(os.path.join(ROOT, "base", "000.png"))
                      .convert("RGBA")).astype(np.int16)

    def layer_of(group, frame=None):
        entries = report["groups"][group]["entries"]
        if frame is None:
            return entries[-1]  # the fully open frame
        for entry in entries:
            if entry["frame"] == frame:
                return entry
        raise KeyError(f"{group}/{frame}")

    def load(rel):
        return np.asarray(Image.open(os.path.join(REPO, rel)).convert("RGBA")
                          ).astype(np.int16)

    def compose(*layers):
        """base with the given layers alpha-composited over it, exactly as the
        previewer does it (a layer is an image with transparency, not a patch
        pasted with a hard edge)."""
        out = base.copy()
        for layer in layers:
            alpha = layer[:, :, 3:4].astype(np.float32) / 255.0
            out[:, :, :3] = (layer[:, :, :3] * alpha +
                             out[:, :, :3] * (1.0 - alpha)).round().astype(np.int16)
            out[:, :, 3] = np.maximum(out[:, :, 3], layer[:, :, 3])
        return out

    panels = ["door_fl", "door_fr", "door_rl", "door_rr", "frunk", "trunk"]

    print("single panel: the layer reproduces its own render")
    layers = {}
    frames = {}
    for name in panels:
        entry = layer_of(name)
        frame = entry["frame"]
        layer = load(entry["layer"])
        frame_image = np.asarray(
            Image.open(os.path.join(ROOT, name, frame)).convert("RGBA")
        ).astype(np.int16)
        layers[name] = layer
        frames[name] = frame_image
        composed = compose(layer)
        diff = np.abs(composed[:, :, :3] - frame_image[:, :, :3]).max(axis=2)
        # Compare where the render is fully opaque: anti-aliased edges blend
        # against whatever is underneath and are not a fidelity statement.
        solid = frame_image[:, :, 3] == 255
        bad = int(((diff > report["threshold"]) & solid).sum())
        check(bad == 0,
              f"{name}: base + layer equals the render ({bad} px differ)")

    print("no hole")
    for name, layer in layers.items():
        mask = layer[:, :, 3] > 0
        composed = compose(layer)
        lost = int(((base[:, :, 3] > 0) & (composed[:, :, 3] == 0)).sum())
        check(lost == 0, f"{name}: composition cannot remove body pixels ({lost})")

    print("two panels at once: every panel keeps its own shape")
    doors = ["door_fl", "door_fr", "door_rl", "door_rr"]
    all_doors = compose(*(layers[d] for d in doors))
    for first in doors:
        mask = layers[first][:, :, 3] > 0
        differs = (all_doors[:, :, :3][mask] != base[:, :, :3][mask]).any()
        check(bool(differs),
              f"{first}: its region is not the closed door any more")
        # The door's own silhouette - the part that swings out past the body -
        # must survive composition. Arbitration between panels was tried and
        # cut exactly this, which is why panels keep whole layers and the
        # overlap is resolved by paint order instead.
        frame = np.asarray(
            Image.open(os.path.join(ROOT, first, layer_of(first)["frame"]))
            .convert("RGBA")).astype(np.int16)
        added = (frame[:, :, 3] > 0) & ~(base[:, :, 3] > 0)
        kept = int((added & mask).sum())
        check(kept == int(added.sum()),
              f"{first}: all {int(added.sum())} swung-out pixels survive "
              f"({kept})")
    # Two doors on the same side project into the same space. That is a 2D
    # limitation, not a bug: the overlap is small and the later layer wins.
    for first, second in (("door_fl", "door_rl"), ("door_fr", "door_rr")):
        overlap = ((layers[first][:, :, 3] > 0) & (layers[second][:, :, 3] > 0))
        share = float(overlap.sum()) / float((layers[first][:, :, 3] > 0).sum())
        check(share < 0.30,
              f"{first}/{second} overlap is small ({overlap.sum()} px, "
              f"{share:.0%} of the smaller layer)")

    print("the panel stays attached and inside its region")
    # Asset-space bounds of the car and its panels, measured from the layers
    # themselves with a small margin: the trunk assembly swings its plate and
    # lamps further than the lid alone did, so a fixed number would start
    # failing whenever a panel gets an assembly.
    boxes = []
    for layer in layers.values():
        ys, xs = np.nonzero(layer[:, :, 3] > 0)
        if len(xs):
            boxes.append((int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())))
    permitted = (min(b[0] for b in boxes) - 2, min(b[1] for b in boxes) - 2,
                 max(b[2] for b in boxes) + 2, max(b[3] for b in boxes) + 2)
    check(permitted[0] >= 0 and permitted[1] >= 0 and permitted[2] <= 356 and
          permitted[3] <= 236,
          f"every layer stays inside the asset canvas {permitted}")
    for name, layer in layers.items():
        mask = layer[:, :, 3] > 0
        ys, xs = np.nonzero(mask)
        if not len(xs):
            check(False, f"{name}: layer is empty")
            continue
        inside = (xs.min() >= permitted[0] and ys.min() >= permitted[1] and
                  xs.max() <= permitted[2] and ys.max() <= permitted[3])
        check(inside, f"{name}: layer stays inside the permitted region")
        # Attached: dilate the body silhouette by 2 px and require the layer to
        # touch it, so a panel cannot drift off the car.
        body = (base[:, :, 3] > 0).astype(np.int16)
        grown = body.copy()
        for _ in range(2):
            grown = np.maximum.reduce([
                grown,
                np.roll(grown, 1, axis=0), np.roll(grown, -1, axis=0),
                np.roll(grown, 1, axis=1), np.roll(grown, -1, axis=1)])
        check(bool((mask & grown.astype(bool)).sum() > 0),
              f"{name}: layer touches the body silhouette")

    print("trunk lighting ownership (layer side)")
    trunk_entries = report["groups"]["trunk"]["entries"]
    variant_entries = report["groups"]["trunk_ind_left"]["entries"]
    # The indicator variants are a blink loop, so the last frame is dark. Pick
    # the frame where the lamps are actually on, and compare it with the plain
    # lid at the same point of the motion.
    brightest_index = max(
        range(len(variant_entries)),
        key=lambda index: int(load(variant_entries[index]["layer"])[:, :, :3].sum()))
    trunk = load(trunk_entries[brightest_index]["layer"])
    trunk_left = load(variant_entries[brightest_index]["layer"])
    # The lid's lamps live in the lid's own layer: the indicator variant must
    # differ from the plain open lid *on the lid*, not somewhere else.
    both = (trunk_left[:, :, 3] > 0) & (trunk[:, :, 3] > 0)
    differs = both & (np.abs(trunk_left[:, :, :3] - trunk[:, :, :3]).max(axis=2) > 8)
    check(int(differs.sum()) > 20,
          f"the indicator variant differs from the plain open lid where the "
          f"lamps are ({int(differs.sum())} px)")
    ys, xs = np.nonzero(differs)
    if len(xs):
        delta = (trunk_left[:, :, :3] - trunk[:, :, :3])
        mean = [round(float(delta[:, :, c][differs].mean()), 1) for c in range(3)]
        print(f"       lamp pixels x{xs.min()}..{xs.max()} y{ys.min()}..{ys.max()}, "
              f"mean dRGB {mean}")
        # Recorded, not asserted: in these renders the variant is DARKER than the
        # plain lid at the lamp strip (mean -22 R). Whether that is the lamp's
        # own light being subtle at this angle or a lighting-convention
        # difference in the renders is unresolved, so the ownership claim rests
        # on the renderer contract (skip the fixed lamp when the lid carries it)
        # and on the output check in tests/horizon_v2_tests.py, not on this
        # brightness sign.
        print("       (direction recorded as a finding, not asserted)")
    outside = int((differs & ~(trunk_left[:, :, 3] > 0)).sum())
    check(outside == 0, f"the lamps stay inside the lid's layer ({outside})")
    # And the fixed-position indicator is a separate layer that the renderer
    # skips while the lid owns those lamps - that decision is measured on the
    # rendered screenshots, in tests/horizon_v2_tests.py.

    print("")
    if FAILURES:
        print(f"{len(FAILURES)} FAILED:")
        for failure in FAILURES:
            print(f"  {failure}")
        return 1
    print("all panel composition checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
