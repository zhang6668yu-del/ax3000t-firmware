import hashlib
import json
import pathlib
import struct
import sys
import zlib
from fdtlib import parse, build

base = pathlib.Path(sys.argv[1])
matches = list(base.rglob('*mt7981b-xiaomi-mi-router-ax3000t.dtb'))
assert matches, 'Official stock AX3000T DTB was not found'
changed = []
for path in matches:
    data = path.read_bytes()
    dt, reserve, cpu = parse(data)
    original = {p: dict(v) for p, v in dt.items()}
    parts = '/soc/spi@1100a000/flash@0/partitions'
    first, second = parts+'/partition@600000', parts+'/partition@2800000'
    assert dt[first]['reg'] == struct.pack('>II', 0x600000, 0x2200000)
    assert dt[second]['reg'] == struct.pack('>II', 0x2800000, 0x4e00000)
    dt[first]['label'] = b'ubi\0'
    dt[first]['reg'] = struct.pack('>II', 0x600000, 0x7000000)
    del dt[second]
    assert 'mediatek,nmbm' in dt['/soc/spi@1100a000/flash@0']
    assert any(b'airoha,an8855-switch' in v.get('compatible', b'') for v in dt.values())
    assert {p:v for p,v in original.items() if p not in (first,second)} == {p:v for p,v in dt.items() if p != first}
    result = build(dt, reserve, cpu)
    assert parse(result)[0] == dt
    path.write_bytes(result)
    changed.append({'path':str(path.relative_to(base)), 'old_sha256':hashlib.sha256(data).hexdigest(), 'new_sha256':hashlib.sha256(result).hexdigest()})

# ImageBuilder ships a ready-made FIT kernel; changing the loose DTB alone
# does not rebuild that FIT. Replace its embedded DTB and update every hash.
fits_changed = []
for path in base.rglob('*xiaomi_mi-router-ax3000t*'):
    if not path.is_file() or path.suffix not in ('.bin', '.itb'):
        continue
    payload = path.read_bytes()
    if payload[:4] != b'\xd0\x0d\xfe\xed':
        continue
    fit, fr, fc = parse(payload)
    if '/images/fdt-1' not in fit:
        continue
    embedded = fit['/images/fdt-1']['data']
    assert hashlib.sha256(embedded).hexdigest() in {c['old_sha256'] for c in changed}, str(path)
    original_kernel = fit['/images/kernel-1']['data']
    fit['/images/fdt-1']['data'] = result
    for name, props in fit.items():
        if name.startswith('/images/fdt-1/') and 'algo' in props:
            algo = props['algo'].rstrip(b'\0').decode()
            props['value'] = struct.pack('>I', zlib.crc32(result)) if algo == 'crc32' else hashlib.new(algo, result).digest()
    rebuilt = build(fit, fr, fc)
    assert parse(rebuilt)[0] == fit
    assert parse(rebuilt)[0]['/images/kernel-1']['data'] == original_kernel
    path.write_bytes(rebuilt)
    fits_changed.append(str(path.relative_to(base)))
assert fits_changed, 'Prebuilt FIT was not found; refusing an unmodified stock kernel'
print('Patched prebuilt FIT files:', fits_changed)

path = base/'target/linux/mediatek/image/filogic.mk'
text = path.read_text()
start = text.index('define Device/xiaomi_mi-router-ax3000t\n')
end = text.index('\nendef', start)
text = text[:start] + '''define Device/xiaomi_mi-router-ax3000t
  DEVICE_VENDOR := Xiaomi
  DEVICE_MODEL := Mi Router AX3000T H-Uboot 112M
  DEVICE_DTS := mt7981b-xiaomi-mi-router-ax3000t
  DEVICE_DTS_DIR := ../dts
  DEVICE_COMPAT_VERSION := 2.0
  DEVICE_COMPAT_MESSAGE := Single 112 MiB UBI layout only. Migration required. Do not force upgrade from stock 34+78 layout.
  UBINIZE_OPTS := -E 5
  BLOCKSIZE := 128k
  PAGESIZE := 2048
  IMAGE_SIZE := 114688k
  KERNEL_IN_UBI := 1
  DEVICE_PACKAGES := kmod-mt7915e kmod-mt7981-firmware mt7981-wo-firmware
  IMAGES := sysupgrade.bin factory.bin
  IMAGE/factory.bin := append-ubi | check-size $$$$(IMAGE_SIZE)
  IMAGE/sysupgrade.bin := sysupgrade-tar | append-metadata''' + text[end:]
path.write_text(text)
(base/'112m-dtb-changes.json').write_text(json.dumps(changed, indent=2)+'\n')
print(json.dumps(changed, indent=2))
