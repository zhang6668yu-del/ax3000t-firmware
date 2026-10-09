"""Fail closed on wrong layout, image hash, board or upgrade routing."""
import hashlib
import json
import pathlib
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import zlib


def fdt(data):
    h = struct.unpack_from('>10I', data)
    assert h[0] == 0xd00dfeed and h[1] <= len(data)
    strings = data[h[3]:h[3]+h[8]]
    pos, stack, nodes = h[2], [], {}
    while pos < h[1]:
        token = struct.unpack_from('>I', data, pos)[0]
        pos += 4
        if token == 1:
            end = data.index(0, pos)
            stack.append(data[pos:end].decode())
            nodes['/'.join(stack)] = {}
            pos = (end + 4) & ~3
        elif token == 2:
            stack.pop()
        elif token == 3:
            size, offset = struct.unpack_from('>II', data, pos)
            pos += 8
            key = strings[offset:strings.index(0, offset)].decode()
            nodes['/'.join(stack)][key] = data[pos:pos+size]
            pos = (pos + size + 3) & ~3
        elif token == 9:
            break
        else:
            assert token == 4
    return nodes


def verify(image, output):
    board = 'xiaomi,mi-router-ax3000t'
    raw = image.read_bytes()
    marker = raw.index(b'"metadata_version"')
    start = raw.rfind(b'{', 0, marker)
    metadata, _ = json.JSONDecoder().raw_decode(raw[start:].decode('utf-8', 'replace'))
    assert metadata['supported_devices'] == [board], metadata
    assert metadata['version']['version'] == '25.12.0', metadata
    with tarfile.open(image) as archive:
        members = {pathlib.PurePosixPath(m.name).name: m for m in archive if m.isfile()}
        assert set(members) == {'CONTROL', 'kernel', 'root'}, members
        kernel = archive.extractfile(members['kernel']).read()
        root = archive.extractfile(members['root']).read()
    fit = fdt(kernel)
    hashes = []
    for name, props in fit.items():
        if 'algo' in props:
            algorithm = props['algo'].rstrip(b'\0').decode()
            data = fit[name.rsplit('/', 1)[0]]['data']
            actual = struct.pack('>I', zlib.crc32(data)) if algorithm == 'crc32' else hashlib.new(algorithm, data).digest()
            assert actual == props['value'], name
            hashes.append(name)
    assert len(hashes) >= 2
    dt = fdt(fit['/images/fdt-1']['data'])
    assert board.encode() in dt['']['compatible'].split(b'\0')
    flash = '/soc/spi@1100a000/flash@0'
    assert 'mediatek,nmbm' in dt[flash]
    partitions = {}
    for name, props in dt.items():
        if name.startswith(flash+'/partitions/') and name.count('/') == 5:
            partitions[props['label'].rstrip(b'\0').decode()] = list(struct.unpack('>II', props['reg']))
    expected = {'BL2': [0, 0x100000], 'Nvram': [0x100000, 0x40000], 'Bdata': [0x140000, 0x40000], 'Factory': [0x180000, 0x200000], 'FIP': [0x380000, 0x200000], 'crash': [0x580000, 0x40000], 'crash_log': [0x5c0000, 0x40000], 'KF': [0x7600000, 0x40000], 'ubi_kernel': [0x600000, 0x2200000], 'ubi': [0x2800000, 0x4e00000]}
    assert partitions == expected, partitions
    assert any(b'airoha,an8855-switch' in p.get('compatible', b'') for p in dt.values())
    assert len(kernel) < 30*1024*1024 and len(root) < 70*1024*1024
    assert root[:4] == b'hsqs'
    with tempfile.TemporaryDirectory() as tmp:
        rootpath = pathlib.Path(tmp)/'root.squashfs'
        rootpath.write_bytes(root)
        platform = subprocess.check_output(['unsquashfs', '-cat', str(rootpath), 'lib/upgrade/platform.sh']).decode()
        assert 'CI_KERN_UBIPART=ubi_kernel' in platform
        assert 'CI_ROOT_UBIPART=ubi' in platform
        release = subprocess.check_output(['unsquashfs', '-cat', str(rootpath), 'etc/openwrt_release']).decode()
        assert "DISTRIB_RELEASE='25.12.0'" in release
    output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(image, output/image.name)
    report = {'image': image.name, 'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw), 'metadata': metadata, 'partitions': partitions, 'fit_hashes_verified': hashes, 'an8855_present': True, 'nmbm_present': True, 'upgrade_split_ubi_present': True, 'kernel_sha256': hashlib.sha256(kernel).hexdigest(), 'device_tree_sha256': hashlib.sha256(fit['/images/fdt-1']['data']).hexdigest(), 'hardware_boot_tested': False}
    (output/'verification.json').write_text(json.dumps(report, indent=2)+'\n')
    (output/'sha256sums').write_text(report['sha256']+'  '+image.name+'\n')
    for pattern in ['*.manifest', 'profiles.json', 'config.buildinfo', 'version.buildinfo', 'feeds.buildinfo']:
        for path in image.parent.glob(pattern):
            shutil.copy2(path, output/path.name)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    images = list(pathlib.Path(sys.argv[1]).glob('*xiaomi_mi-router-ax3000t-squashfs-sysupgrade.bin'))
    assert len(images) == 1, images
    verify(images[0], pathlib.Path(sys.argv[2]))
