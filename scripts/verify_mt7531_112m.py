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
from fdtlib import parse

source, output = map(pathlib.Path, sys.argv[1:3])
image, = source.glob('*xiaomi_mi-router-ax3000t-squashfs-sysupgrade.bin')
factory, = source.glob('*xiaomi_mi-router-ax3000t-squashfs-factory.bin')
raw = image.read_bytes()
pos = raw.index(b'"metadata_version"')
metadata, _ = json.JSONDecoder().raw_decode(raw[raw.rfind(b'{', 0, pos):].decode('utf-8', 'replace'))
assert metadata['compat_version'] == '2.0', metadata
assert metadata['new_supported_devices'] == ['xiaomi,mi-router-ax3000t'], metadata
assert metadata['version']['version'] == '25.12.5', metadata
with tarfile.open(image) as tar:
    entries = {pathlib.PurePosixPath(m.name).name:m for m in tar if m.isfile()}
    assert set(entries) == {'CONTROL', 'kernel', 'root'}
    kernel = tar.extractfile(entries['kernel']).read()
    root = tar.extractfile(entries['root']).read()
fit = parse(kernel)[0]
checks = []
for name, props in fit.items():
    if 'algo' in props:
        algorithm = props['algo'].rstrip(b'\0').decode()
        data = fit[name.rsplit('/', 1)[0]]['data']
        actual = struct.pack('>I', zlib.crc32(data)) if algorithm == 'crc32' else hashlib.new(algorithm, data).digest()
        assert actual == props['value'], name
        checks.append(name)
assert len(checks) >= 2
dt = parse(fit['/images/fdt-1']['data'])[0]
flash = '/soc/spi@1100a000/flash@0'
assert 'mediatek,nmbm' in dt[flash]
assert any(b'mediatek,mt7531' in p.get('compatible', b'') for p in dt.values())
switch = next(n for n,p in dt.items() if b'mediatek,mt7531' in p.get('compatible',b''))
assert dt[switch].get('status',b'okay\0') != b'disabled\0'
assert dt[switch]['reg'] == struct.pack('>I',31)
for port,label in [(0,'wan'),(1,'lan2'),(2,'lan3'),(3,'lan4')]:
    assert dt[switch+'/ports/port@'+str(port)]['label'] == label.encode()+b'\0'
assert dt[switch+'/ports/port@6']['phy-mode'] == b'2500base-x\0'
partitions = {p['label'].rstrip(b'\0').decode():list(struct.unpack('>II',p['reg'])) for n,p in dt.items() if n.startswith(flash+'/partitions/') and n.count('/')==5}
expected = {'BL2':[0,0x100000], 'Nvram':[0x100000,0x40000], 'Bdata':[0x140000,0x40000], 'Factory':[0x180000,0x200000], 'FIP':[0x380000,0x200000], 'crash':[0x580000,0x40000], 'crash_log':[0x5c0000,0x40000], 'KF':[0x7600000,0x40000], 'ubi':[0x600000,0x7000000]}
assert partitions == expected, partitions
with tempfile.TemporaryDirectory() as tmp:
    rootfile = pathlib.Path(tmp)/'root.squashfs'
    rootfile.write_bytes(root)
    def read(path):
        return subprocess.check_output(['unsquashfs','-cat',str(rootfile),path]).decode()
    platform = read('lib/upgrade/platform.sh')
    assert 'ax3000t_112m_layout_ok' in platform and 'CI_UBIPART=ubi' in platform
    assert 'CI_KERN_UBIPART=ubi_kernel' not in platform
    assert '0060000007000000' in platform and '117440512' in platform
    assert 'ucidef_set_compat_version "2.0"' in read('etc/board.d/99-ax3000t-h112m')
    assert "DISTRIB_RELEASE='25.12.5'" in read('etc/openwrt_release')

# Verify that raw UBI factory volumes contain exactly the same kernel/rootfs.
ubi = factory.read_bytes()
assert len(ubi) % 131072 == 0 and len(ubi) < 0x7000000
volumes = {}
for offset in range(0, len(ubi), 131072):
    block = ubi[offset:offset+131072]
    assert block[:4] == b'UBI#'
    vid, dataoff = struct.unpack_from('>II', block, 16)
    assert vid == 2048 and dataoff == 4096
    # ubinize -E adds erased reserve PEBs with only an EC header.
    if block[vid:vid+4] == b'\xff'*4:
        assert block[vid:] == b'\xff'*(len(block)-vid)
        continue
    assert block[vid:vid+4] == b'UBI!'
    volume, lnum = struct.unpack_from('>II', block, vid+8)
    volumes.setdefault(volume,{})[lnum] = block[dataoff:]
contents = {v:b''.join(parts[i] for i in sorted(parts)) for v,parts in volumes.items()}
assert contents[0][:len(kernel)] == kernel
root_used = struct.unpack_from('<Q', root, 40)[0]
assert contents[1][:root_used] == root[:root_used]
manifest, = source.glob('*xiaomi_mi-router-ax3000t.manifest')
packages = {line.split(' - ',1)[0] for line in manifest.read_text().splitlines()}
required = set('dnsmasq-full luci-compat ruby ruby-yaml kmod-inet-diag kmod-tun kmod-nft-tproxy kmod-nft-socket kmod-nft-nat ip-full bash curl ca-bundle unzip coreutils-base64 coreutils-nohup coreutils-timeout chinadns-ng dns2socks resolveip tcping libuci-lua lua luci-lib-jsonc lyaml'.split())
assert required <= packages, sorted(required-packages)
assert 'dnsmasq' not in packages
assert not {'xray-core','sing-box','luci-app-passwall','luci-app-openclash'} & packages
output.mkdir(parents=True, exist_ok=True)
hashes = {}
for original, kind in [(image,'sysupgrade'),(factory,'factory')]:
    name = 'AX3000T-MT7531-H-Uboot-112M-OpenWrt-25.12.5-deps-'+kind+'.bin'
    shutil.copy2(original, output/name)
    hashes[name] = hashlib.sha256(original.read_bytes()).hexdigest()
shutil.copy2(manifest, output/'packages.manifest')
shutil.copy2(source.parents[3]/'112m-dtb-changes.json',output/'112m-dtb-changes.json')
report = {'metadata':metadata, 'partitions':partitions, 'fit_hashes_verified':checks, 'factory_sysupgrade_content_identical':True, 'required_dependencies_present':sorted(required), 'sha256':hashes, 'factory_size':len(ubi), 'kernel_size':len(kernel), 'rootfs_size':len(root), 'hardware_boot_tested':False, 'switch_target':'mediatek,mt7531', 'mt7531_ports_verified':True, 'migration_required':True}
(output/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
(output/'sha256sums').write_text(''.join(h+'  '+n+'\n' for n,h in hashes.items()))
print(json.dumps(report,indent=2))
