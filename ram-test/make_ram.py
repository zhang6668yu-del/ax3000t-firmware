import hashlib
import json
import lzma
import os
import pathlib
import struct
import subprocess
import sys
import tarfile
import tempfile
import zlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from fdtlib import parse, build

source, output = map(pathlib.Path, sys.argv[1:3])
image, = source.glob('*sysupgrade.bin')
assert hashlib.sha256(image.read_bytes()).hexdigest() == '872a30c8fbbee393f54f1e28cf0b9e5439d4c26e1a2043671a9d10d8e14a8fbf'
with tarfile.open(image) as tar:
    kernel = tar.extractfile(next(m for m in tar if m.name.endswith('/kernel'))).read()
    rootfs = tar.extractfile(next(m for m in tar if m.name.endswith('/root'))).read()
fit, fr, fc = parse(kernel)
original_kernel = fit['/images/kernel-1']['data']
dt, dr, dc = parse(fit['/images/fdt-1']['data'])
flash = '/soc/spi@1100a000/flash@0'
parts = flash+'/partitions'
# NMBM can write metadata before partition read-only flags apply. Bypass it
# for this physical NAND, read-only diagnostic boot; do not claim a test of
# normal NMBM attachment or persistent boot from this image.
assert 'mediatek,nmbm' in dt[flash]
del dt[flash]['mediatek,nmbm']
for name, props in dt.items():
    if name.startswith(parts+'/') and name.count('/') == parts.count('/')+1:
        props['read-only'] = b''
        if props.get('label') == b'ubi\0':
            props['label'] = b'DIAG_ubi_112m\0'
fit['/images/fdt-1']['data'] = build(dt, dr, dc)

with tempfile.TemporaryDirectory() as temp:
    temp = pathlib.Path(temp)
    squash = temp/'root.squashfs'; squash.write_bytes(rootfs)
    root = temp/'root'
    subprocess.run(['unsquashfs','-d',str(root),str(squash)],check=True)
    # Standard OpenWrt initramfs entry point: start the same procd/userspace
    # from tmpfs with INITRAMFS=1, which prevents mounting NAND rootfs.
    init = root/'init'
    init.write_text('''#!/bin/sh
export INITRAMFS=1
DIRS=$(echo *)
NEW_ROOT=/new_root
mkdir -p "$NEW_ROOT"
mount -t tmpfs tmpfs "$NEW_ROOT"
cp -pr $DIRS "$NEW_ROOT"
exec switch_root "$NEW_ROOT" /sbin/init
''')
    init.chmod(0o755)
    marker = root/'etc/codex-readonly-ram-test'
    marker.write_text('AX3000T 25.12.5 complete custom rootfs; NAND read-only; NMBM bypassed for safety.\n')
    paths = [b'.']
    for current, dirs, files in os.walk(root, followlinks=False):
        for item in sorted(dirs+files):
            paths.append(os.fsencode('./'+str((pathlib.Path(current)/item).relative_to(root))))
    paths = sorted(set(paths))
    cpio = subprocess.run(['cpio','--null','-o','-H','newc','--owner=0:0','--reproducible'],input=b'\0'.join(paths)+b'\0',cwd=root,stdout=subprocess.PIPE,check=True).stdout
    ramdisk = lzma.compress(cpio,format=lzma.FORMAT_ALONE,preset=6)

fit['/images/initrd-1'] = {'description':b'AX3000T 25.12.5 full rootfs RAM test\0','data':ramdisk,'type':b'ramdisk\0','arch':b'arm64\0','os':b'linux\0'}
fit['/images/initrd-1/hash-1'] = {'algo':b'crc32\0','value':struct.pack('>I',zlib.crc32(ramdisk))}
fit['/images/initrd-1/hash-2'] = {'algo':b'sha1\0','value':hashlib.sha1(ramdisk).digest()}
for name,props in fit.items():
    if name.startswith('/configurations/') and 'kernel' in props:
        props['ramdisk'] = b'initrd-1\0'
    if name.startswith('/images/fdt-1/') and 'algo' in props:
        data = fit['/images/fdt-1']['data'];algo = props['algo'].rstrip(b'\0').decode()
        props['value'] = struct.pack('>I',zlib.crc32(data)) if algo=='crc32' else hashlib.new(algo,data).digest()
result = build(fit,fr,fc)
check = parse(result)[0]
assert check == fit
assert check['/images/kernel-1']['data'] == original_kernel
for name,props in check.items():
    if 'algo' in props:
        data = check[name.rsplit('/',1)[0]]['data'];algo = props['algo'].rstrip(b'\0').decode()
        actual = struct.pack('>I',zlib.crc32(data)) if algo=='crc32' else hashlib.new(algo,data).digest()
        assert props['value']==actual
assert len(result)<32*1024*1024 and len(cpio)<80*1024*1024
output.mkdir(exist_ok=True,parents=True)
name='AX3000T-25.12.5-112M-readonly-RAM-test.itb'
(output/name).write_bytes(result)
report={'file':name,'sha256':hashlib.sha256(result).hexdigest(),'size':len(result),'uncompressed_cpio_size':len(cpio),'kernel_sha256':hashlib.sha256(original_kernel).hexdigest(),'source_sysupgrade_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),'all_nand_partitions_readonly':True,'nmbm_disabled_for_safety':True,'old_ubi_not_attached':True,'full_custom_rootfs_used':True}
(output/'ram-image-verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
