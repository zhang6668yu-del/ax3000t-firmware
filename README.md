# AX3000T H-Uboot 112 MiB builds

The workflow builds two independent images from the pinned `openwrt-24.10-6.6`
source: MT7531 and AN8855. This is a third-party 24.10 branch build, not an
official stable release image. Neither image includes PassWall, PassWall2,
OpenClash or SSR+. Required proxy infrastructure is checked against the actual
installed package manifest before uploading firmware.

## Source audit

Source commit: `ec9ef10efc65da1e6d1de4e2c043c0e13d08eed8` in
`padavanonly/immortalwrt-mt798x-6.6`.

The upstream `xiaomi_mi-router-ax3000t-mtkuboot` profile uses
`IMAGE_SIZE := 114688k`, `KERNEL_IN_UBI := 1`, and
`mt7981b-xiaomi-mi-router-ax3000t-mtkuboot.dts`.
Its UBI partition is `<0x600000 0x7000000>` with NMBM enabled.
The inherited common DTS explicitly contains both `mediatek,mt7531` and
`airoha,an8855-switch`; the Filogic kernel enables both driver families.

`scripts/prepare.py` derives separate profiles and compatible IDs, disables the
other switch's parent node, retains the same partition layout and updates
network, failsafe and U-Boot environment board handling. This fork ships the
MTK vendor Wi-Fi driver rather than the upstream mt76 package. Only radio,
connection and warp settings are imported from its MT7981 defconfig; the old
multi-device and application package selections are discarded.

The partition map matches hanwckf `bl-mt798x`'s AX3000T
`immortalwrt-112m` layout (6 MiB prefix, 112 MiB UBI, KF at 0x7600000).
The U-Boot layout selection on each physical router must still be verified.
112 MiB is the total UBI partition, not guaranteed writable free space.

## Fixed failure

Run `37348806817`, job `111894147902`, failed during `package/install`:
`libustream-openssl20201210` collided with `libustream-mbedtls20201210` at
`/lib/libustream-ssl.so`. The old workflow copied a broad preconfigured image
and added `luci-ssl` (mbedTLS) over OpenSSL base defaults.
The new workflow starts with a clean configuration and uses
`luci-ssl-openssl` plus `libustream-openssl`.

## Artifacts and flashing

Each variant artifact contains factory.bin, sysupgrade.bin, sha256sums,
config.buildinfo, profiles.json, package manifest, feed/source revisions and DTS.
Keep the switch variants separate. The new compatible IDs intentionally differ;
migration from an older generic firmware requires separate verification.

`factory.bin` is a raw UBI image for compatible H-Uboot firmware upload.
`sysupgrade.bin` is the sysupgrade tar image for a matching running system.
Neither image is a bootloader, calibration partition, or whole-flash backup.
Do not write them to BL2, FIP or Factory. Successful CI verifies the build;
physical boot, Ethernet and Wi-Fi tests remain necessary.
