#!/usr/bin/env python3
import hashlib
import json
import pathlib
import shutil
import sys
import subprocess
import tarfile
import tempfile

root = pathlib.Path(sys.argv[1])
variant = sys.argv[2]
profile = f'xiaomi_mi-router-ax3000t-{variant}-mtkuboot'
target = root / 'bin/targets/mediatek/filogic'
out = pathlib.Path('output')
out.mkdir(exist_ok=True)
profiles = json.loads((target / 'profiles.json').read_text())
assert profile in profiles['profiles'], f'Missing built profile {profile}'
assert profiles['version_number'] == '24.10.2', profiles['version_number']
# Read the packaged SquashFS, not just the requested build configuration.
sysupgrade = next(target.glob(f'*{profile}*sysupgrade.bin'))
with tarfile.open(sysupgrade) as archive, tempfile.TemporaryDirectory() as temporary:
    root_member = next(m for m in archive.getmembers() if m.name.endswith('/root'))
    squashfs = pathlib.Path(temporary) / 'root.squashfs'
    squashfs.write_bytes(archive.extractfile(root_member).read())
    extractor = root.resolve() / 'staging_dir/host/bin/unsquashfs4'
    def read_image_file(name):
        return subprocess.check_output([str(extractor), '-cat', str(squashfs), name], text=True)
    built_feeds = read_image_file('etc/opkg/distfeeds.conf')
    built_release = read_image_file('etc/openwrt_release')
    built_os_release = read_image_file('usr/lib/os-release')
assert "DISTRIB_RELEASE='24.10.2'" in built_release, built_release
assert '24.10-SNAPSHOT' not in built_feeds
repo = 'https://downloads.immortalwrt.org/releases/24.10.2'
paths = ['targets/mediatek/filogic/packages'] + [
    f'packages/aarch64_cortex-a53/{feed}'
    for feed in ('base', 'luci', 'packages', 'routing', 'telephony')]
assert [line.split()[2] for line in built_feeds.splitlines() if line.startswith('src/gz ')] == [
    f'{repo}/{path}' for path in paths], built_feeds
for name, content in [('distfeeds.conf', built_feeds), ('openwrt_release', built_release),
                      ('os-release', built_os_release)]:
    (out / name).write_text(content)
print('Packaged version and six fixed 24.10.2 feeds verified')
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
    shutil.copy2(files[0], out / f'AX3000T-{variant.upper()}-H-Uboot-112M-24.10.2-{kind}.bin')
for name in ('config.buildinfo', 'profiles.json', 'feeds.buildinfo', 'version.buildinfo'):
    shutil.copy2(target / name, out / name)
(out / 'packages.manifest').write_text(manifest)
shutil.copytree('audit', out / 'audit', dirs_exist_ok=True)
(out / 'READ-BEFORE-FLASH.txt').write_text(f'''Switch: {variant.upper()} ONLY. Do not flash on the other switch variant.
Profile: {profile}
Source: padavanonly/immortalwrt-mt798x-6.6, pinned commit recorded in audit/source.sha.
This is a third-party build labelled 24.10.2, not the official 24.10.2 release source.\nThe original pinned vendor source and custom kernel are preserved.\nOfficial 24.10.2 feeds fix the invalid URL but do not guarantee all package ABIs match.\nDo not install official kmods with a different kernel ABI or force dependency overrides.\nAvoid blanket opkg upgrades of firmware/base/system packages.
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
