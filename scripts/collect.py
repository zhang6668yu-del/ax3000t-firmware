#!/usr/bin/env python3
import hashlib
import json
import os
import pathlib
import shutil
import sys

root = pathlib.Path(sys.argv[1]).resolve()
variant = sys.argv[2]
assert variant in ('mt7531', 'an8855'), f"Invalid variant {variant}"

profile = f'xiaomi_mi-router-ax3000t-{variant}-mtkuboot'
compat_name = 'xiaomi,mi-router-ax3000t-mtkuboot' if variant == 'mt7531' else 'xiaomi,mi-router-ax3000t-an8855-mtkuboot'
target = root / 'bin/targets/mediatek/filogic'
out = pathlib.Path('output')
out.mkdir(exist_ok=True)

print(f"Collecting firmware for {variant} ({profile})...")
all_files = list(target.iterdir())
print(f"Total files in target directory: {len(all_files)}")

# 1. Search and collect factory and sysupgrade images
all_bins = [f for f in all_files if f.is_file() and f.name.endswith('.bin')]
print("Found binary images:")
for b in all_bins:
    print(f"  {b.name} ({b.stat().st_size} bytes)")

for kind in ('factory', 'sysupgrade'):
    matched = [
        b for b in all_bins
        if kind in b.name.lower() and (
            variant in b.name.lower() or
            profile in b.name.lower() or
            compat_name.replace(',', '-') in b.name.lower() or
            compat_name in b.name.lower()
        )
    ]
    if not matched:
        # Fallback to any binary matching this kind
        matched = [b for b in all_bins if kind in b.name.lower()]
    assert matched, f"No {kind} image found in {target}!"
    chosen = matched[0]
    dest_name = f'AX3000T-{variant.upper()}-H-Uboot-112M-24.10.2-{kind}.bin'
    shutil.copy2(chosen, out / dest_name)
    print(f"Successfully collected {kind}: {chosen.name} -> {dest_name} ({chosen.stat().st_size} bytes)")

# 2. Copy build information if available
for info_name in ('config.buildinfo', 'profiles.json', 'feeds.buildinfo', 'version.buildinfo'):
    src = target / info_name
    if src.is_file():
        shutil.copy2(src, out / info_name)

# 3. Find and copy packages manifest
manifests = [f for f in all_files if f.name.endswith('.manifest') and (variant in f.name or profile in f.name)]
if not manifests:
    manifests = [f for f in all_files if f.name.endswith('.manifest')]
if manifests:
    shutil.copy2(manifests[0], out / 'packages.manifest')
    manifest_text = manifests[0].read_text()
    installed = {line.split(' - ')[0] for line in manifest_text.splitlines() if ' - ' in line}
    print(f"Total installed packages: {len(installed)}")
    # Check upstream Wi-Fi
    has_mt7915 = 'kmod-mt7915e' in installed
    print(f"Upstream kmod-mt7915e included: {has_mt7915}")
    assert 'kmod-mt_wifi' not in installed, "Vendor closed-source wifi driver must not be included!"

# 4. Copy audit directory if exists
if pathlib.Path('audit').is_dir():
    shutil.copytree('audit', out / 'audit', dirs_exist_ok=True)

# 5. Write documentation
readme_content = f"""================================================================================
Xiaomi AX3000T ({variant.upper()}) ImmortalWrt v24.10.2 Official Release Firmware
================================================================================
Hardware Switch: {variant.upper()} ONLY. Do not flash on the other switch variant.
Board Name / Compatible: {compat_name}
Target Profile: {profile}
Base Source: Official immortalwrt/immortalwrt release tag v24.10.2
Kernel: Linux 6.6.93 (Official ImmortalWrt 24.10.2 release kernel & kmod ABI)
Wi-Fi Stack: Upstream Linux mac80211 / mt76 (kmod-mt7915e + mt7981 firmware)
Switch Driver: {'Airoha AN8855 DSA switch' if variant == 'an8855' else 'MediaTek MT7531 switch'}
Software Feeds: Official ImmortalWrt 24.10.2 release feeds (/etc/opkg/distfeeds.conf)
                Compatible with official kmods and mainland Tsinghua mirror.
Partition Layout: H-Uboot / hanwckf immortalwrt-112m multi-layout
                  NMBM enabled, UBI at offset 0x600000, length 0x7000000 (112 MiB total)

Firmware Files:
  - AX3000T-{variant.upper()}-H-Uboot-112M-24.10.2-factory.bin
    Raw UBI image for flashing via H-Uboot Web failsafe / recovery interface.
  - AX3000T-{variant.upper()}-H-Uboot-112M-24.10.2-sysupgrade.bin
    Sysupgrade archive with metadata for upgrading an existing running system.

Important:
  - Only flash via compatible H-Uboot (immortalwrt-112m layout).
  - Never write directly to FIP, BL2, Factory, Nvram, Bdata, or raw NAND.
================================================================================
"""
(out / 'READ-BEFORE-FLASH.txt').write_text(readme_content)

# 6. Generate sha256 checksums
(out / 'sha256sums').write_text(
    ''.join(
        f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n'
        for p in sorted(out.iterdir())
        if p.is_file() and p.name != 'sha256sums'
    )
)
print("Firmware collection finished. Contents of output/:")
for f in sorted(out.iterdir()):
    print(f"  {f.name} ({f.stat().st_size} bytes)")
