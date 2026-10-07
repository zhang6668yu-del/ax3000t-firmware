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

# 1. Verify profiles.json
profiles_file = target / 'profiles.json'
assert profiles_file.is_file(), f"Missing {profiles_file}"
profiles = json.loads(profiles_file.read_text())
version_num = profiles.get('version_number', '')
print(f"Firmware version: {version_num}")
assert '24.10.2' in version_num, f"Expected 24.10.2, got {version_num}"
assert profile in profiles['profiles'], f"Missing built profile {profile} in profiles.json"

# 2. Verify installed packages manifest
manifest_files = list(target.glob(f'*{profile}*.manifest'))
assert manifest_files, f"Missing manifest for {profile}"
manifest = manifest_files[0].read_text()
installed = {line.split(' - ')[0] for line in manifest.splitlines() if ' - ' in line}

# Verify upstream mt76 Wi-Fi packages are installed
wifi_required = ['kmod-mt7915e', 'kmod-mt7981-firmware', 'mt7981-wo-firmware', 'wpad-openssl']
missing_wifi = set(wifi_required) - installed
assert not missing_wifi, f"Firmware missing required Wi-Fi packages: {missing_wifi}"

# Verify vendor wifi packages are NOT present
assert 'kmod-mt_wifi' not in installed, "Vendor kmod-mt_wifi must not be present"
assert 'mtwifi-cfg' not in installed, "Vendor mtwifi-cfg must not be present"

# Verify system & network acceleration packages
system_required = (
    'kmod-tun kmod-nft-socket kmod-nft-tproxy kmod-nft-queue kmod-inet-diag '
    'kmod-mediatek_hnat ip-full iptables-nft nftables-json curl wget-ssl '
    'ca-bundle ca-certificates bash unzip openssh-sftp-server coreutils '
    'coreutils-base64 luci-i18n-base-zh-cn'
).split()
missing_system = set(system_required) - installed
assert not missing_system, f"Firmware missing required system packages: {missing_system}"

# 3. Verify firmware binaries
for kind in ('factory', 'sysupgrade'):
    files = list(target.glob(f'*{profile}*{kind}.bin'))
    assert len(files) == 1, f"Expected one {kind} image, found {files}"
    img = files[0]
    size = img.stat().st_size
    assert size > 0, f"Empty image: {img}"
    dest_name = f'AX3000T-{variant.upper()}-H-Uboot-112M-24.10.2-{kind}.bin'
    shutil.copy2(img, out / dest_name)
    print(f"Generated {kind} image: {dest_name} ({size} bytes)")

for name in ('config.buildinfo', 'profiles.json', 'feeds.buildinfo', 'version.buildinfo'):
    src = target / name
    if src.is_file():
        shutil.copy2(src, out / name)

(out / 'packages.manifest').write_text(manifest)
if pathlib.Path('audit').is_dir():
    shutil.copytree('audit', out / 'audit', dirs_exist_ok=True)

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

# Generate checksums
(out / 'sha256sums').write_text(
    ''.join(
        f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n'
        for p in sorted(out.iterdir())
        if p.is_file() and p.name != 'sha256sums'
    )
)
print("Firmware collection and verification completed successfully.")
