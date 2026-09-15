# Blender source

`model3.blend` is generated (not hand-authored). Build it with:

```bash
blender -b -P tools/blender/build_model3_scene.py
```

That writes both `model3.blend` and `model3.manifest.json` here. The manifest
maps every action to the objects and frame range it drives, and is what
`tools/blender/render_vehicle_assets.py` reads.

Why the .blend is not committed: it is a build artifact derived from the
script, and keeping it out of git avoids binary churn. Regenerate it after any
change to `tools/blender/build_model3_scene.py`.

See `docs/VEHICLE_ASSET_PIPELINE.md` for the full pipeline, the fixed
`Camera_Horizon` framing, the required object split and the PNG output spec.
