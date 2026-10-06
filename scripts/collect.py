#!/usr/bin/env python3
import hashlib
import json
import pathlib
import shutil
import sys

root = pathlib.Path(sys.argv[1])
variant = sys.argv[2]
profile = f'xiaomi_mi-router-ax3000t-{variant}-mtkuboot'
target = root / 'bin/targets/mediatek/filogic'
out = pathlib.Path('output')
out.mkdir(exist_ok=True)
profiles = json.loads((target / 'profiles.json').read_text())
assert profile in profiles['profiles'], f'Missing built profile {profile}'
manifest = next(target.glob(f'*{profile}*.manifest')).read_text()
installed = {line.split(' - ')[0] for line in manifest.splitlines()}
required = 'kmod-tun kmod-nft-socket kmod-nft-tproxy kmod-nft-queue kmod-inet-diag ip-full iptables-nft nftables-json curl wget-ssl ca-bundle ca-certificates bash unzip openssh-sftp-server coreutils coreutils-base64 luci-i18n-base-zh-cn kmod-mt_wifi mtwifi-cfg'.split()
missing = sorted(set(required) - installed)
assert not missing, f'Firmware missing required packages: {missing}'
assert not any('passwall' in p.lower() or 'openclash' in p.lower() or 'ssr-plus' in p.lower() for p in installed)
assert not any(p.startswith(('libustream-mbedtls', 'libustream-wolfssl')) for p in installed)
for kind in ('factory', 'sysupgrade'):
    files = list(target.glob(f'*{profile}*{kind}.bin'))
    assert len(files) == 1, f'Expected one {kind} image, found {files}'
    assert files[0].stat().st_size > 0
    shutil.copy2(files[0], out / f'AX3000T-{variant.upper()}-H-Uboot-112M-24.10-{kind}.bin')
for name in ('config.buildinfo', 'profiles.json', 'feeds.buildinfo', 'version.buildinfo'):
    shutil.copy2(target / name, out / name)
(out / 'packages.manifest').write_text(manifest)
shutil.copytree('audit', out / 'audit', dirs_exist_ok=True)
(out / 'READ-BEFORE-FLASH.txt').write_text(f'''Switch: {variant.upper()} ONLY. Do not flash on the other switch variant.
Profile: {profile}
Source: padavanonly/immortalwrt-mt798x-6.6, pinned commit recorded in audit/source.sha.
This is a third-party 24.10 branch build, not an official stable release image.
Layout: hanwckf AX3000T immortalwrt-112m, NMBM, UBI at 0x600000, length 0x7000000.
IMAGE_SIZE: 114688 KiB = 112 MiB total UBI; writable free space will be smaller.
factory.bin: raw UBI image for a compatible H-Uboot firmware upload.
sysupgrade.bin: sysupgrade tar with metadata for an already compatible running system.
Never write either image to FIP, BL2, Factory, or the whole NAND.
New switch-specific compatible ID: migration from older generic firmware must be reviewed separately.
Build audit verifies profile, manifests and sources; hardware boot/network tests are still required.
''')
(out / 'sha256sums').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in sorted(out.iterdir()) if p.is_file() and p.name != 'sha256sums'))
print('\n'.join(str(p) for p in out.iterdir()))
