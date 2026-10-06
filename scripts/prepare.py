#!/usr/bin/env python3
"""Derive switch-specific profiles from the audited 112 MiB upstream profile."""
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1])
variant = sys.argv[2]
assert variant in ('mt7531', 'an8855')
base = 'xiaomi_mi-router-ax3000t-mtkuboot'
profile = f'xiaomi_mi-router-ax3000t-{variant}-mtkuboot'
dtsdir = root / 'target/linux/mediatek/dts'
image = root / 'target/linux/mediatek/image/filogic.mk'
text = image.read_text()
block = re.search(r'define Device/' + base + r'\n.*?\nendef', text, re.S).group()
assert 'IMAGE_SIZE := 114688k' in block
assert 'KERNEL_IN_UBI := 1' in block
block = block.replace(base, profile)
block = block.replace(base.replace('_', '-'), profile.replace('_', '-'))
block = block.replace('  DEVICE_VARIANT := (MTK U-Boot layout)', f'  DEVICE_VARIANT := ({variant.upper()}, H-Uboot 112M)')
block = block.replace('  DEVICE_DTS_DIR := ../dts', '  DEVICE_DTS_DIR := ../dts\n  DEVICE_PACKAGES := kmod-mt_wifi mtwifi-cfg luci-app-mtwifi-cfg')
image.write_text(text + f'\n{block}\nTARGET_DEVICES += {profile}\n')
base_dts = (dtsdir / f'mt7981b-{base.replace("_", "-")}.dts').read_text()
assert 'reg = <0x600000 0x7000000>' in base_dts
common = (dtsdir / 'mt7981b-xiaomi-mi-router-common.dtsi').read_text()
assert 'mediatek,mt7531' in common and 'airoha,an8855-switch' in common
dts = base_dts.replace('xiaomi,mi-router-ax3000t-mtkuboot', 'xiaomi,mi-router-ax3000t-' + variant + '-mtkuboot')
dts = dts.replace('(MTK U-Boot layout)', f'({variant.upper()}, H-Uboot 112M)')
dts += '\n&switch { status = "' + ('okay' if variant == 'mt7531' else 'disabled') + '"; };\n'
dts += '&mfd { status = "' + ('okay' if variant == 'an8855' else 'disabled') + '"; };\n'
(dtsdir / f'mt7981b-{profile.replace("_", "-")}.dts').write_text(dts)
for relative in ('target/linux/mediatek/filogic/base-files/etc/board.d/02_network',
                 'target/linux/mediatek/base-files/lib/preinit/05_set_preinit_iface',
                 'package/boot/uboot-envtools/files/mediatek_filogic'):
    path = root / relative
    contents = path.read_text()
    old = 'xiaomi,mi-router-ax3000t-mtkuboot|'
    assert old in contents
    path.write_text(contents.replace(old, f'xiaomi,mi-router-ax3000t-{variant}-mtkuboot|\\\n' + old))
# Keep the fork's essential base defaults, remove its unrelated USB/NAS apps.
target = root / 'target/linux/mediatek/Makefile'
t = target.read_text()
t = re.sub(r'DEFAULT_PACKAGES \+=.*?(?=\n\$\(eval)', 'DEFAULT_PACKAGES += kmod-leds-gpio kmod-gpio-button-hotplug ethtool\n', t, flags=re.S)
target.write_text(t)
packages = '''luci luci-ssl-openssl luci-i18n-base-zh-cn luci-i18n-firewall-zh-cn
luci-app-ttyd luci-i18n-ttyd-zh-cn luci-compat luci-lua-runtime
ca-bundle ca-certificates bash curl wget-ssl unzip openssh-sftp-server
ip-full iptables-nft ip6tables-nft nftables-json ipset
iptables-mod-tproxy iptables-mod-extra iptables-mod-socket
kmod-ipt-nat kmod-ipt-nat6 kmod-ipt-conntrack kmod-mediatek_hnat
kmod-tun kmod-nft-socket kmod-nft-tproxy kmod-nft-queue kmod-inet-diag
kmod-netlink-diag coreutils coreutils-base64 libustream-openssl
kmod-mt_wifi mtwifi-cfg luci-app-mtwifi-cfg luci-i18n-mtwifi-cfg-zh-cn'''.split()
config = ['CONFIG_TARGET_mediatek=y', 'CONFIG_TARGET_mediatek_filogic=y', f'CONFIG_TARGET_mediatek_filogic_DEVICE_{profile}=y', 'CONFIG_TARGET_ROOTFS_SQUASHFS=y', 'CONFIG_JSON_OVERVIEW_IMAGE_INFO=y', 'CONFIG_INCLUDE_CONFIG=y']
# This fork carries the MTK vendor Wi-Fi driver, not the upstream mt76 package.
# Import only its radio/connection/warp settings, never its package or target list.
radio = (root / 'defconfig/mt7981-ax3000.config').read_text().splitlines()
config += [line for line in radio if re.match(r'CONFIG_(MTK_|CONNINFRA_|WARP_|WED_)', line)]
config += [f'CONFIG_PACKAGE_{p}=y' for p in packages]
config += ['# CONFIG_PACKAGE_luci-ssl is not set', '# CONFIG_PACKAGE_libustream-mbedtls is not set', '# CONFIG_PACKAGE_libustream-wolfssl is not set', '# CONFIG_PACKAGE_nftables-nojson is not set']
(root / '.config').write_text('\n'.join(config) + '\n')
print(profile)
