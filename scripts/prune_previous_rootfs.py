import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tarfile

base, previous = (pathlib.Path(p).resolve() for p in sys.argv[1:3])
image, = previous.glob('*sysupgrade.bin')
manifest, = previous.glob('packages.manifest')
baseline = dict(line.split(' - ', 1) for line in manifest.read_text().splitlines())
with tarfile.open(image) as archive:
    kernel = archive.extractfile(next(m for m in archive if m.name.endswith('/kernel'))).read()
    squashfs = archive.extractfile(next(m for m in archive if m.name.endswith('/root'))).read()
assert hashlib.sha256(kernel).hexdigest() == 'ac512b799f1fac8e0ad0f364e4161a8bc8890c02a6a3d1ece697f2f89cc81ae5'
root, = [p.parent.parent for p in base.glob('build_dir/target-*/root-*/etc/openwrt_release')]
assert root.is_relative_to(base/'build_dir')
shutil.rmtree(root)
raw = base/'previous-root.squashfs'
raw.write_bytes(squashfs)
unpack = subprocess.run(['unsquashfs', '-d', str(root), str(raw)], stderr=subprocess.PIPE, text=True)
if unpack.returncode:
    errors = [line for line in unpack.stderr.splitlines() if line.strip()]
    assert unpack.returncode == 2 and len(errors) == 1 and 'could not create character device ' + str(root/'dev/console') in errors[0], unpack.stderr
    print('The unprivileged extractor omitted dev/console; ImageBuilder recreates that device with its standard pseudo-file definition.')
raw.unlink()

def fingerprints():
    return {str(p.relative_to(root)): ('symlink:' + str(p.readlink()) if p.is_symlink() else hashlib.sha256(p.read_bytes()).hexdigest())
            for p in root.rglob('*') if p.is_symlink() or p.is_file()}

before = fingerprints()
apk = base/'staging_dir/host/bin/apk'
command = [str(apk), '--root', str(root), '--arch', 'aarch64_cortex-a53', '--no-network', '--repositories-file', '/dev/null']
removed = set('luci-compat luci-lib-jsonc coreutils-base64 coreutils-nohup coreutils-timeout ruby ruby-yaml libuci-lua lua lyaml chinadns-ng dns2socks microsocks resolveip tcping ipt2socks'.split())
subprocess.run(command + ['del', '--no-scripts'] + sorted(removed & baseline.keys()), check=True)
install_log = root/'tmp/log/apk.log'
if 'tmp/log/apk.log' not in before and install_log.is_file():
    install_log.unlink()
after = fingerprints()
changed = {p for p in before.keys() & after.keys() if before[p] != after[p]}
assert all(p == 'etc/apk/world' or p.startswith(('lib/apk/db/', 'usr/lib/apk/db/')) for p in changed), changed
added = after.keys() - before.keys()
assert all(p.startswith(('lib/apk/db/', 'usr/lib/apk/db/')) for p in added), sorted(added)
text = subprocess.check_output(command + ['list', '--quiet', '--manifest'], text=True)
installed = dict(line.split(' ', 1) for line in text.splitlines())
assert not (installed.keys() - baseline.keys())
assert all(baseline[p] == version for p, version in installed.items())
assert not (removed & installed.keys())

printer = base/'.print-root-paths.mk'
printer.write_text('print-root-paths:\n\t@echo $(TARGET_DIR_ORIG)\n')
original = pathlib.Path(subprocess.check_output(['make', '--no-print-directory', '-s', '-f', 'Makefile', '-f', printer.name, 'print-root-paths'], cwd=base, text=True).strip())
printer.unlink()
assert original.is_relative_to(base) and original != root
if original.exists():
    shutil.rmtree(original)
shutil.copytree(root, original, symlinks=True)
for p in base.glob('build_dir/target-*/linux-*/root.squashfs*'):
    if p.is_file():
        p.unlink()
subprocess.run(['make', 'build_image', 'USER_PROFILE=DEVICE_xiaomi_mi-router-ax3000t'], cwd=base, check=True)
report = {'source_image_sha256': hashlib.sha256(image.read_bytes()).hexdigest(),
          'retained_package_versions_unchanged': True, 'retained_files_unchanged_except_package_database': True,
          'changed_package_database_files': sorted(changed), 'removed_packages': sorted(baseline.keys() - installed.keys()),
          'added_packages': [], 'changed_versions': {}, 'source_file_count': len(before), 'remaining_file_count': len(after)}
(base/'previous-root-prune-audit.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))
