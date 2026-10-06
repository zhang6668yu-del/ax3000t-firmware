#!/usr/bin/env python3
"""Publish only this build's signed IPKs to the non-default ipk-feeds branch."""
import base64
import gzip
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import io
import tempfile
import time

root = pathlib.Path(sys.argv[1]).resolve()
variant = sys.argv[2]
assert variant in ('mt7531', 'an8855')
build_id = os.environ['FEED_BUILD_ID']
assert re.fullmatch(r'build-[0-9]+-[0-9]+', build_id)
repository = os.environ['GITHUB_REPOSITORY']
assert repository == 'zhang6668yu-del/ax3000t-firmware'
profile = f'xiaomi_mi-router-ax3000t-{variant}-mtkuboot'
target = root / 'bin/targets/mediatek/filogic'
manifest = next(target.glob(f'*{profile}*.manifest')).read_text()
kernel = next(line.split(' - ', 1)[1] for line in manifest.splitlines() if line.startswith('kernel - '))
expected = '6.6.133~a4123ef5a0c462947780a438299a4fb8-r1'
assert kernel == expected, f'Kernel ABI changed: {kernel} != {expected}'
repo = pathlib.Path('package-repository').resolve()
repo.mkdir(exist_ok=True)
for ipk in sorted((root / 'bin').rglob('*.ipk')):
    destination = repo / ipk.name
    if destination.exists():
        assert destination.read_bytes() == ipk.read_bytes(), f'Conflicting IPK {ipk.name}'
    else:
        shutil.copy2(ipk, destination)
assert list(repo.glob('*.ipk')), 'No IPKs generated'
kernel_ipk = next(repo.glob('kernel_*.ipk'))
with tarfile.open(kernel_ipk) as archive:
    control = next(m for m in archive if m.name.lstrip('./') == 'control.tar.gz')
    with tarfile.open(fileobj=io.BytesIO(archive.extractfile(control).read())) as nested:
        control_file = next(m for m in nested if m.name.lstrip('./') == 'control')
        kernel_control = nested.extractfile(control_file).read().decode()
assert f'Version: {expected}\n' in kernel_control, kernel_control
index_env = os.environ.copy()
index_env['MKHASH'] = str(root / 'staging_dir/host/bin/mkhash')
index = subprocess.check_output([str(root / 'scripts/ipkg-make-index.sh'), '.'], cwd=repo, env=index_env)
# The build's own index generator produces control metadata. Keep dependency fields.
lines = [line for line in index.decode().splitlines() if not re.match(
    r'^(Maintainer|LicenseFiles|Source|SourceName|Require|SourceDateEpoch):', line)]
index = ('\n'.join(lines) + '\n').encode()
if (64 + len(index)) % 128 in (110, 111):
    index += b'\n\n'
(repo / 'Packages').write_bytes(index)
with gzip.GzipFile(str(repo / 'Packages.gz'), 'wb', mtime=0) as output:
    output.write(index)
paragraphs = [dict(line.split(': ', 1) for line in paragraph.splitlines() if ': ' in line and not line.startswith(' '))
              for paragraph in index.decode().split('\n\n') if paragraph.strip()]
assert not any(p.get('Package') in ('kernel', 'libc') for p in paragraphs)
for package in paragraphs:
    if package.get('Package', '').startswith('kmod-'):
        assert re.search(r'kernel\s*\(=\s*' + re.escape(expected) + r'\)', package.get('Depends', '')), package
    file = repo / package['Filename'].removeprefix('./')
    assert hashlib.sha256(file.read_bytes()).hexdigest() == package['SHA256sum']
usign = root / 'staging_dir/host/bin/usign'
subprocess.run([str(usign), '-S', '-m', str(repo / 'Packages'), '-s', str(root / 'key-build')], check=True)
subprocess.run([str(usign), '-V', '-m', str(repo / 'Packages'), '-p', str(root / 'key-build.pub')], check=True)
shutil.copy2(root / 'key-build.pub', repo / 'repo.pub')
(repo / 'build.json').write_text(json.dumps({'source': subprocess.check_output(
    ['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip(),
    'profile': profile, 'kernel': kernel, 'build_id': build_id,
    'package_count': len(paragraphs)}, indent=2) + '\n')
# Use the workflow token only for this auxiliary branch. Never expose it in logs.
env = os.environ.copy()
header = base64.b64encode(('x-access-token:' + env.pop('GH_TOKEN')).encode()).decode()
env.update(GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='http.https://github.com/.extraheader',
           GIT_CONFIG_VALUE_0='AUTHORIZATION: basic ' + header)
with tempfile.TemporaryDirectory() as temporary:
    checkout = pathlib.Path(temporary)
    def git(*args, check=True):
        return subprocess.run(['git', *args], cwd=checkout, env=env, check=check,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    git('init')
    git('remote', 'add', 'origin', f'https://github.com/{repository}.git')
    git('config', 'user.name', 'github-actions[bot]')
    git('config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com')
    published = False
    for attempt in range(5):
        exists = bool(git('ls-remote', '--heads', 'origin', 'ipk-feeds').stdout.strip())
        if exists:
            git('fetch', '--depth=1', 'origin', 'refs/heads/ipk-feeds')
            git('checkout', '-B', 'ipk-feeds', 'FETCH_HEAD')
        else:
            assert attempt == 0, 'Initial feed publication failed; contents-write access is required'
            git('symbolic-ref', 'HEAD', 'refs/heads/ipk-feeds')
        destination = checkout / build_id / variant
        if destination.exists():
            assert (destination / 'Packages').read_bytes() == index, 'Refusing to replace a published build'
            published = True
            break
        shutil.copytree(repo, destination)
        git('add', f'{build_id}/{variant}')
        git('commit', '-m', f'Publish signed {variant} packages for {build_id}')
        result = git('push', 'origin', 'HEAD:refs/heads/ipk-feeds', check=False)
        if result.returncode == 0:
            published = True
            break
        # A concurrent switch build may have advanced the same auxiliary branch.
        if attempt < 4:
            git('reset', '--hard', 'HEAD')
            time.sleep(3)
    assert published, 'Publishing ipk-feeds failed; check Actions contents-write permissions'
url = f'https://raw.githubusercontent.com/{repository}/ipk-feeds/{build_id}/{variant}'
print(f'Published {len(paragraphs)} signed packages: {url}')
print(f'All kmod dependencies match: {kernel}')
