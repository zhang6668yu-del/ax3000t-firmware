#!/usr/bin/env python3
"""Run the firmware's opkg under QEMU/proot against the published signed feed."""
import os
import pathlib
import re
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

root = pathlib.Path(sys.argv[1]).resolve()
variant = sys.argv[2]
profile = f'xiaomi_mi-router-ax3000t-{variant}-mtkuboot'
image = next((root / 'bin/targets/mediatek/filogic').glob(f'*{profile}*sysupgrade.bin'))
url = f'https://raw.githubusercontent.com/{os.environ["GITHUB_REPOSITORY"]}/ipk-feeds/{os.environ["FEED_BUILD_ID"]}/{variant}'
with tempfile.TemporaryDirectory() as temporary:
    directory = pathlib.Path(temporary)
    squashfs = directory / 'root.squashfs'
    with tarfile.open(image) as archive:
        member = next(m for m in archive.getmembers() if m.name.endswith('/root'))
        squashfs.write_bytes(archive.extractfile(member).read())
    filesystem = directory / 'root'
    # Preserve the image's device nodes while extracting on an unprivileged runner.
    subprocess.run(['sudo', str(root / 'staging_dir/host/bin/unsquashfs4'),
                    '-d', str(filesystem), str(squashfs)],
                   check=True, stdout=subprocess.DEVNULL)
    # Run the real firmware client under proot as the runner user and allow cleanup.
    subprocess.run(['sudo', 'chown', '-hR', f'{os.getuid()}:{os.getgid()}',
                    str(filesystem)], check=True)
    feeds = (filesystem / 'etc/opkg/distfeeds.conf').read_text()
    assert feeds == f'src/gz ax3000t_custom {url}\n', feeds
    print('cat /etc/opkg/distfeeds.conf:\n' + feeds, flush=True)
    # Wait briefly for raw content propagation before exercising the actual client.
    for attempt in range(10):
        try:
            with urllib.request.urlopen(url + '/Packages.gz', timeout=30) as response:
                assert response.status == 200
            break
        except Exception:
            if attempt == 9:
                raise
            time.sleep(6)
    (filesystem / 'tmp').mkdir(exist_ok=True)
    command = ['proot', '-0', '-q', '/usr/bin/qemu-aarch64-static', '-r', str(filesystem),
               '-b', '/etc/resolv.conf:/etc/resolv.conf', '-b', '/dev', '-b', '/proc',
               '-w', '/', '/bin/sh', '-c', 'cat /etc/opkg/distfeeds.conf; opkg update']
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=240)
    print(result.stdout, flush=True)
    audit = pathlib.Path('audit')
    audit.mkdir(exist_ok=True)
    (audit / 'opkg-update.log').write_text(result.stdout)
    (audit / 'distfeeds.conf').write_text(feeds)
    assert result.returncode == 0, 'Actual firmware opkg update failed'
    assert 'Signature check passed' in result.stdout, 'No successful package signature verification'
    assert 'Failed to download' not in result.stdout and 'Signature check failed' not in result.stdout
    indexes = list((filesystem / 'var/opkg-lists').glob('ax3000t_custom'))
    if not indexes:
        indexes = list((filesystem / 'tmp').rglob('ax3000t_custom'))
    assert indexes, 'opkg did not store a downloaded package index'
    index = indexes[0].read_text()
    expected = '6.6.133~a4123ef5a0c462947780a438299a4fb8-r1'
    for paragraph in index.split('\n\n'):
        if paragraph.startswith('Package: kmod-'):
            assert re.search(r'kernel\s*\(=\s*' + re.escape(expected) + r'\)', paragraph), paragraph
    print('Online opkg update, signature and kernel ABI verification passed')
