#!/usr/bin/env python3
"""Audit sysupgrade image rootfs: verify board_name, kernel version, feeds and opkg."""
import json
import os
import pathlib
import re
import subprocess
import sys
import tarfile
import tempfile

root = pathlib.Path(sys.argv[1]).resolve()
variant = sys.argv[2]
assert variant in ('mt7531', 'an8855')

profile = f'xiaomi_mi-router-ax3000t-{variant}-mtkuboot'
expected_compat = 'xiaomi,mi-router-ax3000t-mtkuboot' if variant == 'mt7531' else 'xiaomi,mi-router-ax3000t-an8855-mtkuboot'

target_dir = root / 'bin/targets/mediatek/filogic'
image_files = list(target_dir.glob(f'*{profile}*sysupgrade.bin'))
assert len(image_files) == 1, f"Found {image_files}"
image = image_files[0]

with tempfile.TemporaryDirectory() as temporary:
    temp_dir = pathlib.Path(temporary)
    squashfs = temp_dir / 'root.squashfs'
    
    # 1. Inspect tar archive and sysupgrade metadata
    with tarfile.open(image) as archive:
        members = {m.name: m for m in archive.getmembers()}
        root_member = next((m for name, m in members.items() if name.endswith('/root')), None)
        assert root_member is not None, "Missing root squashfs member in sysupgrade tar"
        squashfs.write_bytes(archive.extractfile(root_member).read())
        
        control_member = next((m for name, m in members.items() if 'CONTROL' in name), None)
        if control_member:
            control_content = archive.extractfile(control_member).read().decode('utf-8', errors='ignore')
            print("Sysupgrade CONTROL metadata:\n" + control_content)
            assert expected_compat in control_content, f"Expected {expected_compat} in sysupgrade CONTROL metadata"

    # 2. Extract rootfs
    filesystem = temp_dir / 'root'
    subprocess.run(['sudo', str(root / 'staging_dir/host/bin/unsquashfs4'),
                    '-d', str(filesystem), str(squashfs)],
                   check=True, stdout=subprocess.DEVNULL)
    subprocess.run(['sudo', 'chown', '-hR', f'{os.getuid()}:{os.getgid()}',
                    str(filesystem)], check=True)

    # 3. Verify distfeeds.conf
    distfeeds_path = filesystem / 'etc/opkg/distfeeds.conf'
    assert distfeeds_path.is_file(), "Missing /etc/opkg/distfeeds.conf in rootfs"
    feeds_text = distfeeds_path.read_text()
    print("cat /etc/opkg/distfeeds.conf:\n" + feeds_text)
    assert '24.10.2' in feeds_text, "distfeeds.conf does not point to official 24.10.2 release feeds"

    # 4. Verify os-release
    os_release_path = filesystem / 'usr/lib/os-release'
    if not os_release_path.is_file():
        os_release_path = filesystem / 'etc/os-release'
    if os_release_path.is_file():
        rel = os_release_path.read_text()
        print("os-release:\n" + rel)
        assert '24.10.2' in rel, f"os-release mismatch: {rel}"

    # 5. Verify board_name support scripts
    net_script = (filesystem / 'etc/board.d/02_network').read_text()
    assert expected_compat in net_script, f"Missing {expected_compat} in 02_network"

    audit_dir = pathlib.Path('audit')
    audit_dir.mkdir(exist_ok=True)
    (audit_dir / 'distfeeds.conf').write_text(feeds_text)
    
    # 6. Test opkg update against official repository under QEMU/proot
    (filesystem / 'tmp').mkdir(exist_ok=True)
    command = ['proot', '-0', '-q', '/usr/bin/qemu-aarch64-static', '-r', str(filesystem),
               '-b', '/etc/resolv.conf:/etc/resolv.conf', '-b', '/dev', '-b', '/proc',
               '-w', '/', '/bin/sh', '-c',
               'mkdir -p /var/lock /var/opkg-lists && chmod 1777 /var/lock && '
               'opkg update']
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=240)
    print("opkg update result:\n" + result.stdout, flush=True)
    (audit_dir / 'opkg-update.log').write_text(result.stdout)
    assert result.returncode == 0, f"opkg update failed:\n{result.stdout}"
    assert 'Signature check passed' in result.stdout, "Official package signatures failed verification"

print(f"Firmware audit and official feeds verification succeeded for {profile}!")
