#!/usr/bin/env python3
"""Resolve which vehicle asset set the previewer/runtime should use.

Modes (manifest `vehicle_source.mode`):
    auto             prefer RENDERED_MODEL3, fall back to PLACEHOLDER
    rendered_model3  require real Blender renders
    placeholder      force the engineering placeholder (tests only)

The provider refuses to fall back to the placeholder when the caller is
not a developer preview (`allow_placeholder=False`), which is how the
production Horizon is prevented from shipping placeholder art.
"""

import json
import os

PLACEHOLDER = "PLACEHOLDER"
RENDERED_MODEL3 = "RENDERED_MODEL3"

# manifest["vehicle_source"]["active"] keys
KEY_RENDERED = "rendered_model3"
KEY_PLACEHOLDER = "placeholder"

# Marker written by the Blender render pipeline into the rendered tree.
MODEL3_MARKER = "MODEL3_SOURCE.json"


class VehicleAssetProvider:
    def __init__(self, repo_root, manifest):
        self.repo_root = repo_root
        self.manifest = manifest
        cfg = manifest.get("vehicle_source", {})
        self.mode = cfg.get("mode", "auto")
        self.sources = cfg.get("active", {})
        self.production_allows_placeholder = cfg.get(
            "production_allows_placeholder", False)
        self.selected = None
        self.warning = None

    # -------------------------------------------------------------- probing
    def _root(self, key):
        entry = self.sources.get(key)
        if not entry:
            return None
        return os.path.join(self.repo_root, entry["root"])

    def rendered_model3_available(self):
        root = self._root(KEY_RENDERED)
        if not root or not os.path.isdir(root):
            return False
        marker = os.path.join(root, MODEL3_MARKER)
        return os.path.isfile(marker)

    def placeholder_available(self):
        root = self._root(KEY_PLACEHOLDER)
        if not root or not os.path.isdir(root):
            return False
        for dirpath, _dirs, files in os.walk(root):
            if any(f.endswith(".png") for f in files):
                return True
        return False

    # ------------------------------------------------------------- resolve
    def resolve(self, allow_placeholder):
        """Returns (source_kind, root_path). Raises if nothing usable."""
        if self.mode == "placeholder":
            if not allow_placeholder:
                raise RuntimeError(
                    "manifest forces PLACEHOLDER but this is not a developer "
                    "preview: placeholder vehicle is forbidden in production")
            self.selected = PLACEHOLDER
        elif self.mode == "rendered_model3":
            if not self.rendered_model3_available():
                raise RuntimeError(
                    "manifest requires RENDERED_MODEL3 but no "
                    f"{MODEL3_MARKER} was found in "
                    f"{self._root(KEY_RENDERED)}")
            self.selected = RENDERED_MODEL3
        else:  # auto
            if self.rendered_model3_available():
                self.selected = RENDERED_MODEL3
            elif allow_placeholder and self.placeholder_available():
                self.selected = PLACEHOLDER
                self.warning = (
                    "no real Model 3 render found - falling back to the "
                    "ENGINEERING PLACEHOLDER (developer preview only)")
            else:
                raise RuntimeError(
                    "no vehicle asset available and placeholder is not "
                    "allowed here")

        if self.selected == PLACEHOLDER and not allow_placeholder and \
                not self.production_allows_placeholder:
            raise RuntimeError("placeholder vehicle is forbidden in production")
        return self.selected, self._root(
            KEY_PLACEHOLDER if self.selected == PLACEHOLDER else KEY_RENDERED)

    # -------------------------------------------------------------- access
    def path_for(self, relative):
        """Resolve an asset path relative to the selected source root."""
        if self.selected is None:
            raise RuntimeError("resolve() must be called first")
        return os.path.join(
            self._root(KEY_PLACEHOLDER if self.selected == PLACEHOLDER
                       else KEY_RENDERED), relative)

    def describe(self):
        return {
            "mode": self.mode,
            "selected": self.selected,
            "root": self._root(
                KEY_PLACEHOLDER if self.selected == PLACEHOLDER
                else KEY_RENDERED) if self.selected else None,
            "warning": self.warning,
        }


def load_provider(repo_root, manifest_path):
    with open(manifest_path) as fh:
        manifest = json.load(fh)
    return VehicleAssetProvider(repo_root, manifest)
