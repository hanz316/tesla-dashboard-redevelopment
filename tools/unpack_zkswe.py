#!/usr/bin/env python3
"""Reconstruct a standard SquashFS image from a ZKSWE application update.

The ZKSWE application image used by this dashboard has this layout:

    0x000..0x01f  vendor update header
    0x020..0x033  first 20 bytes of the SquashFS superblock
    0x034..0x24f  vendor metadata inserted into the superblock
    0x250..EOF    remainder of the SquashFS image

This tool only reads the source image and writes a reconstructed copy.  It does
not modify the source package or communicate with a device.
"""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path


OUTER_HEADER_SIZE = 0x20
SQUASH_PREFIX_SIZE = 0x14
SQUASH_TAIL_OFFSET = 0x250
EXPECTED_VENDOR_MAGIC = b"ZKSWEV1.0-1801270"
EXPECTED_SQUASH_MAGIC = b"hsqs"


class ImageFormatError(ValueError):
    """Raised when an input does not match the validated ZKSWE layout."""


def reconstruct(
    source: Path, destination: Path, fragment_count: int | None = None
) -> dict[str, int | str]:
    image = source.read_bytes()
    minimum_size = SQUASH_TAIL_OFFSET + 76
    if len(image) < minimum_size:
        raise ImageFormatError(f"image is too small: {len(image)} bytes")
    if not image.startswith(EXPECTED_VENDOR_MAGIC):
        raise ImageFormatError("missing ZKSWEV1.0-1801270 header")
    if image[OUTER_HEADER_SIZE : OUTER_HEADER_SIZE + 4] != EXPECTED_SQUASH_MAGIC:
        raise ImageFormatError("missing little-endian SquashFS magic at 0x20")

    squashfs = bytearray(
        image[OUTER_HEADER_SIZE : OUTER_HEADER_SIZE + SQUASH_PREFIX_SIZE]
        + image[SQUASH_TAIL_OFFSET:]
    )

    compression, block_log, flags, id_count, major, minor = struct.unpack_from(
        "<6H", squashfs, 0x14
    )
    bytes_used = struct.unpack_from("<Q", squashfs, 0x28)[0]
    inode_count, created, block_size, original_fragments = struct.unpack_from(
        "<4I", squashfs, 0x04
    )

    if fragment_count is not None:
        if not 0 < fragment_count <= original_fragments:
            raise ImageFormatError(
                "fragment override must be positive and no larger than the "
                f"stored value ({original_fragments})"
            )
        struct.pack_into("<I", squashfs, 0x10, fragment_count)
    fragments = fragment_count or original_fragments

    if (major, minor) != (4, 0):
        raise ImageFormatError(
            f"unexpected SquashFS version {major}.{minor}; refusing to write"
        )
    if block_size != 1 << block_log:
        raise ImageFormatError(
            f"block size {block_size} does not match block log {block_log}"
        )
    if not 0 < bytes_used <= len(squashfs):
        raise ImageFormatError(
            f"invalid bytes_used {bytes_used} for {len(squashfs)}-byte image"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(squashfs)
    return {
        "source": str(source),
        "destination": str(destination),
        "source_size": len(image),
        "squashfs_size": len(squashfs),
        "bytes_used": bytes_used,
        "inode_count": inode_count,
        "created_unix": created,
        "block_size": block_size,
        "fragments": fragments,
        "original_fragments": original_fragments,
        "compression_id": compression,
        "flags": flags,
        "id_count": id_count,
        "version": f"{major}.{minor}",
        "removed_outer_header_bytes": OUTER_HEADER_SIZE,
        "removed_vendor_metadata_bytes": (
            SQUASH_TAIL_OFFSET - OUTER_HEADER_SIZE - SQUASH_PREFIX_SIZE
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="ZKSWE update.img")
    parser.add_argument("destination", type=Path, help="output .squashfs path")
    parser.add_argument(
        "--fragment-count",
        type=int,
        help=(
            "override the stored SquashFS fragment count in the reconstructed "
            "copy; use only when the on-disk fragment index proves the vendor "
            "count is incompatible with standard SquashFS"
        ),
    )
    args = parser.parse_args()

    try:
        metadata = reconstruct(args.source, args.destination, args.fragment_count)
    except (OSError, ImageFormatError) as exc:
        parser.error(str(exc))
    print(json.dumps(metadata, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
