#!/usr/bin/env python3
"""Dump the dynamic symbol table of an ELF file.

Needed because the device's shared libraries are shipped with their
section headers stripped (``file`` reports "no section header"), so
``nm -D`` cannot enumerate them. This walks PT_DYNAMIC directly and is
how the EasyUI runtime API (e.g. ZKImageAnim, zk_disp_*) was recovered
for docs/RENDERING_CAPABILITY_AUDIT.md.

Usage:
  python3 tools/elf_dynsyms.py <file.so> [name-filter]
"""

import struct
import sys


def parse(path):
    data = open(path, "rb").read()
    if data[:4] != b"\x7fELF":
        return None
    if data[4] != 1:  # 32-bit only; the device is ARM32
        return None
    (e_phoff,) = struct.unpack_from("<I", data, 28)
    (e_phentsize, e_phnum) = struct.unpack_from("<HH", data, 42)

    phdrs = []
    dynamic = None
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        p_type, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_flags, p_align = \
            struct.unpack_from("<IIIIIIII", data, off)
        phdrs.append((p_type, p_offset, p_vaddr, p_filesz))
        if p_type == 2:  # PT_DYNAMIC
            dynamic = (p_offset, p_filesz)
    if dynamic is None:
        return None

    def vaddr_to_offset(vaddr):
        for p_type, p_offset, p_vaddr, p_filesz in phdrs:
            if p_type == 1 and p_vaddr <= vaddr < p_vaddr + p_filesz:
                return p_offset + (vaddr - p_vaddr)
        return None

    tags = {}
    off, size = dynamic
    for i in range(0, size, 8):
        tag, val = struct.unpack_from("<II", data, off + i)
        if tag == 0:
            break
        tags.setdefault(tag, val)

    symtab = tags.get(6)   # DT_SYMTAB
    strtab = tags.get(5)   # DT_STRTAB
    syment = tags.get(11, 16)  # DT_SYMENT
    if not symtab or not strtab:
        return None
    str_off = vaddr_to_offset(strtab)
    sym_off = vaddr_to_offset(symtab)
    if str_off is None or sym_off is None:
        return None

    strings = data[str_off:]
    out = []
    i = 0
    while i < 200000:
        o = sym_off + i * syment
        if o + syment > len(data):
            break
        st_name, st_value, st_size, st_info, st_other, st_shndx = \
            struct.unpack_from("<IIIBBH", data, o)
        if st_name == 0 and st_value == 0 and i > 0:
            break
        end = strings.find(b"\0", st_name)
        name = strings[st_name:end].decode("utf-8", "replace") if end > 0 else ""
        out.append((name, st_info & 0xF, st_value))
        i += 1
    return out


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    syms = parse(sys.argv[1])
    if syms is None:
        sys.exit("could not parse dynamic symbols")
    needle = sys.argv[2] if len(sys.argv) > 2 else None
    kind = {0: "NOTYPE", 1: "OBJECT", 2: "FUNC", 3: "SECTION"}
    count = 0
    for name, typ, value in syms:
        if needle and needle.lower() not in name.lower():
            continue
        print(f"{kind.get(typ, typ):8} 0x{value:08x} {name}")
        count += 1
    print(f"-- {count} of {len(syms)} dynamic symbols --", file=sys.stderr)


if __name__ == "__main__":
    main()
