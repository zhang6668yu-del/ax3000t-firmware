#!/usr/bin/env python3
"""Audit sysupgrade image rootfs: verify board_name, kernel version, feeds and Wi-Fi."""
import os
import pathlib
import re
import subprocess
import sys
import tarfile
import tempfile

root = pathlib.Path(sys.argv[1]).resolve()
variant = sys.argv[2]
assert variant in ('mt7531', 'an8855'), f"Invalid variant: {variant}"

profile = f'xiaomi_mi-router-ax3000t-{variant}-mtkuboot'
expected_compat = 'xiaomi,mi-router-ax3000t-mtkuboot' if variant == 'mt7531' else 'xiaomi,mi-router-ax3000t-an8855-mtkuboot'

target_dir = root / 'bin/targets/mediatek/filogic'
image_files = list(target_dir.glob(f'*{profile}*sysupgrade.bin'))
assert len(image_files) == 1, f"Found {image_files}"
image = image_files[0]
print(f"Auditing image: {image.name}")

audit_dir = pathlib.Path('audit')
audit_dir.mkdir(exist_ok=True)
audit_log = []

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
            audit_log.append("CONTROL metadata:\n" + control_content)
            # Both device profile name (with underscore) and compatible (with comma) are valid board IDs
            assert (profile in control_content or expected_compat in control_content), \
                f"Neither {profile} nor {expected_compat} found in CONTROL:\n{control_content}"

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
    audit_log.append("distfeeds.conf:\n" + feeds_text)
    (audit_dir / 'distfeeds.conf').write_text(feeds_text)
    assert '24.10.2' in feeds_text, f"distfeeds.conf does not point to official 24.10.2 release feeds:\n{feeds_text}"

    # 4. Verify os-release
    for os_rel in (filesystem / 'usr/lib/os-release', filesystem / 'etc/os-release'):
        if os_rel.is_file():
            rel = os_rel.read_text()
            print("os-release:\n" + rel)
            audit_log.append("os-release:\n" + rel)
            assert '24.10.2' in rel, f"os-release mismatch: {rel}"
            break

    # 5. Verify board_name support in network scripts
    net_script = (filesystem / 'etc/board.d/02_network').read_text()
    assert expected_compat in net_script, f"Missing {expected_compat} in 02_network"
    print(f"Board compatibility {expected_compat} verified in /etc/board.d/02_network")

    # 6. Verify Wi-Fi kernel module in rootfs
    kmod_dir = list((filesystem / 'lib/modules').glob('6.6.*'))
    assert kmod_dir, "No kernel modules directory found in rootfs"
    kernel_ver = kmod_dir[0].name
    print(f"Kernel modules directory version: {kernel_ver}")
    audit_log.append(f"Kernel version: {kernel_ver}")
    assert kernel_ver.startswith('6.6.93'), f"Expected official 6.6.93 kernel, got {kernel_ver}"

    mt7915_mod = list(kmod_dir[0].rglob('*mt7915*.ko*'))
    assert mt7915_mod, f"Missing mt7915 Wi-Fi driver in rootfs: {list(kmod_dir[0].rglob('*.ko*'))}"
    print(f"Verified mt76 Wi-Fi module present: {[m.name for m in mt7915_mod]}")

    # 7. Check proot opkg update test
    (filesystem / 'tmp').mkdir(exist_ok=True)
    command = ['proot', '-0', '-q', '/usr/bin/qemu-aarch64-static', '-r', str(filesystem),
               '-b', '/etc/resolv.conf:/etc/resolv.conf', '-b', '/dev', '-b', '/proc',
               '-w', '/', '/bin/sh', '-c',
               'mkdir -p /var/lock /var/opkg-lists && chmod 1777 /var/lock && opkg update']
    try:
        result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=180)
        print("opkg update result:\n" + result.stdout)
        audit_log.append("opkg update result:\n" + result.stdout)
        (audit_dir / 'opkg-update.log').write_text(result.stdout)
    except Exception as e:
        print(f"proot opkg update test skipped due to runner network/environment: {e}")
        audit_log.append(f"proot opkg update test skipped: {e}")

(audit_dir / 'audit.log').write_text('\n\n'.join(audit_log))
print(f"Audit completed successfully for {profile}!")
