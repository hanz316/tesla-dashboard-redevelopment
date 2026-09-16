# Third-party asset attribution

This file records attribution for any third-party 3D model, texture or
other asset used by the dashboard. Creative Commons licences such as
CC-BY 4.0 **require** attribution when the asset is redistributed, which
includes publishing it in this repository.

## How to use

When a third-party asset is added, append a section:

```text
### <asset name>
- Title:      <model title>
- Author:     <creator display name>
- Source:     <URL>
- License:    <e.g. CC BY 4.0> (<licence URL>)
- Retrieved:  <YYYY-MM-DD>
- Modifications: <e.g. separated doors, retopology, own materials>
- Used in:    assets/source/blender/model3_master.blend
```

If an asset cannot be redistributed, it must **not** be committed: keep it
locally under `assets/source/downloads/` (git-ignored) and register its
SHA-256 here so the pipeline stays reproducible without redistributing it.

## Current status

Two third-party Tesla Model 3 models were obtained for the A/B evaluation.
**Neither is committed to this repository** (both live in the git-ignored
`assets/source/download/`); only their hashes and attribution are recorded.

### MODEL A — "Tesla 2018 Model 3" (FBX, evaluated)

- Title:      Tesla 2018 Model 3
- Author:     Ameer Studio (Sketchfab uploader)
- Source:     https://sketchfab.com/3d-models/5ef9b845aaf44203b6d04e2c677e444f
- License:    Creative Commons Attribution (CC BY 4.0)
              http://creativecommons.org/licenses/by/4.0/
- Retrieved:  2026-09-15 (user-supplied FBX original format)
- Files:      `assets/source/download/model_a_ameer/source/tesla_car1.fbx`
              + `assets/source/download/model_a_ameer/textures/` (22 files)
- SHA-256:    `5992165a9d7aa1e95940bc11a809839a9248e0f9031d8a4e95df5c977ac788a5`
- Modifications: NONE to the source file. Evaluation renders were produced
  from an in-memory copy (scale/rotation normalisation only, not saved).
- ⚠️ Provenance note: this mesh (684,315 faces) is uploaded on Sketchfab by
  **8 different accounts** under different names, so the original author is
  unverifiable. See `docs/MODEL3_AB_EVALUATION.md` §15.

### MODEL B — "Tesla M3 model" (BLEND, evaluated)

- Title:      Tesla M3 model
- Author:     wintrez
- Source:     https://sketchfab.com/3d-models/3a602469d7874d1397efa67182198705
- License:    CC-BY 4.0 (http://creativecommons.org/licenses/by/4.0/)
- Retrieved:  2026-09-15 (user-supplied .blend)
- File:       `assets/source/download/model_b_wintrez/teslaMSFullSketchfab001.blend`
- SHA-256:    `d4efbdfcae3f47419ae00d852879d9173cb2495a70155d3d3b18d3da2091453d`
- Modifications: NONE to the source file. Evaluation renders used an
  in-memory copy (in-memory visibility/scale/rotation only, not saved).

### Engineering placeholder (self-built, not third-party)

`tools/assets/generate_placeholder_frames.py` emits the neutral placeholder
used for pipeline tests and developer preview only. It is not third-party
art and must never appear in a production Horizon.

### Studio HDRIs — dark automotive studio lighting (evaluated + used)

Lighting/environment maps for the photoreal material study. Both are **CC0**
(public domain dedication): no attribution is legally required, but Poly Haven
asks for credit and the provenance is recorded here anyway because an
unverifiable HDRI must never enter this pipeline.

| Field | Value |
|---|---|
| Title | Studio Kontrast 01 (**used** for the study) |
| Author | Grzegorz Wronkowski |
| Source | https://polyhaven.com/a/studio_kontrast_01 |
| Download | https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/2k/studio_kontrast_01_2k.hdr |
| License | CC0 1.0 (https://creativecommons.org/publicdomain/zero/1.0/) |
| Resolution | 1024×512 (1k, evaluation) and 2048×1024 (2k, render) |
| Retrieved | 2026-09-16 |
| Local path | `assets/source/hdri/studio_kontrast_01_2k.hdr` (git-ignored) |

| Field | Value |
|---|---|
| Title | Brown Photostudio 02 (evaluated, not selected) |
| Author | Sergej Majboroda |
| Source | https://polyhaven.com/a/brown_photostudio_02 |
| License | CC0 1.0 |
| Resolution | 1024×512 (1k) and 2048×1024 (2k) |
| Retrieved | 2026-09-16 |
| Local path | `assets/source/hdri/brown_photostudio_02_2k.hdr` (git-ignored) |

Rejected candidates are recorded in `docs/VEHICLE_PHOTOREAL_STUDY.md` §1 so a
future round does not re-evaluate the same files.
