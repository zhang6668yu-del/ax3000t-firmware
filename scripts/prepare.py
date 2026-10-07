#!/usr/bin/env python3
"""Prepare switch-specific profiles for Xiaomi AX3000T on official ImmortalWrt v24.10.2."""
import pathlib
import sys

root = pathlib.Path(sys.argv[1]).resolve()
variant = sys.argv[2]
assert variant in ('mt7531', 'an8855'), f"Invalid variant {variant}"

profile = f'xiaomi_mi-router-ax3000t-{variant}-mtkuboot'
compat_name = 'xiaomi,mi-router-ax3000t-mtkuboot' if variant == 'mt7531' else 'xiaomi,mi-router-ax3000t-an8855-mtkuboot'

dtsdir = root / 'target/linux/mediatek/dts'
image = root / 'target/linux/mediatek/image/filogic.mk'

# 1. Append Device Profile to target/linux/mediatek/image/filogic.mk
image_content = image.read_text()
device_block = f"""
define Device/{profile}
  DEVICE_VENDOR := Xiaomi
  DEVICE_MODEL := Mi Router AX3000T
  DEVICE_VARIANT := ({variant.upper()}, H-Uboot 112M)
  DEVICE_DTS := mt7981b-{profile.replace("_", "-")}
  DEVICE_DTS_DIR := ../dts
  UBINIZE_OPTS := -E 5
  BLOCKSIZE := 128k
  PAGESIZE := 2048
  IMAGE_SIZE := 114688k
  KERNEL_IN_UBI := 1
  SUPPORTED_DEVICES := {compat_name}
  DEVICE_PACKAGES := kmod-mt7915e kmod-mt7981-firmware mt7981-wo-firmware
  IMAGES += factory.bin
  IMAGE/factory.bin := append-ubi | check-size $$$$(IMAGE_SIZE)
  IMAGE/sysupgrade.bin := sysupgrade-tar | append-metadata
endef
TARGET_DEVICES += {profile}
"""
if f'define Device/{profile}' not in image_content:
    image.write_text(image_content + '\n' + device_block + '\n')

# 2. Create switch-specific DTS with 112M UBI partition layout and upstream mt76 Wi-Fi
dts_path = dtsdir / f'mt7981b-{profile.replace("_", "-")}.dts'
switch_status = 'okay' if variant == 'mt7531' else 'disabled'
mfd_status = 'okay' if variant == 'an8855' else 'disabled'

dts_content = f"""// SPDX-License-Identifier: GPL-2.0-or-later OR MIT

/dts-v1/;
#include "mt7981b-xiaomi-mi-router-ax3000t.dtsi"

/ {{
	model = "Xiaomi Mi Router AX3000T ({variant.upper()}, H-Uboot 112M)";
	compatible = "{compat_name}", "mediatek,mt7981";
}};

&spi_nand {{
	mediatek,nmbm;
	mediatek,bmt-max-ratio = <1>;
	mediatek,bmt-max-reserved-blocks = <64>;
	mediatek,bmt-mtd-overridden-oobsize = <64>;
}};

&partitions {{
	partition@600000 {{
		label = "ubi";
		reg = <0x600000 0x7000000>;
	}};
}};

&switch {{
	status = "{switch_status}";
}};

&mfd {{
	status = "{mfd_status}";
}};
"""
dts_path.write_text(dts_content)

# 3. Patch board.d and preinit files for switch recognition and MAC setup
for relative in (
    'target/linux/mediatek/filogic/base-files/etc/board.d/02_network',
    'target/linux/mediatek/base-files/lib/preinit/05_set_preinit_iface',
    'package/boot/uboot-envtools/files/mediatek_filogic'
):
    target_file = root / relative
    content = target_file.read_text()
    anchor = 'xiaomi,mi-router-ax3000t|'
    patch_line = f'{compat_name}|\\\n\t'
    if compat_name not in content and anchor in content:
        content = content.replace(anchor, patch_line + anchor)
        target_file.write_text(content)

# 4. Configure .config for build
packages = '''
luci
luci-ssl-openssl
luci-i18n-base-zh-cn
luci-i18n-firewall-zh-cn
luci-app-ttyd
luci-i18n-ttyd-zh-cn
luci-compat
luci-lua-runtime
ca-bundle
ca-certificates
bash
curl
wget-ssl
unzip
openssh-sftp-server
ip-full
iptables-nft
ip6tables-nft
nftables-json
ipset
iptables-mod-tproxy
iptables-mod-extra
iptables-mod-socket
kmod-ipt-nat
kmod-ipt-nat6
kmod-ipt-conntrack
kmod-mediatek_hnat
kmod-tun
kmod-nft-socket
kmod-nft-tproxy
kmod-nft-queue
kmod-inet-diag
kmod-netlink-diag
coreutils
coreutils-base64
libustream-openssl
kmod-mt7915e
kmod-mt7981-firmware
mt7981-wo-firmware
wpad-openssl
wireless-tools
iw
'''.split()

config_lines = [
    'CONFIG_TARGET_mediatek=y',
    'CONFIG_TARGET_mediatek_filogic=y',
    f'CONFIG_TARGET_mediatek_filogic_DEVICE_{profile}=y',
    'CONFIG_TARGET_ROOTFS_SQUASHFS=y',
    'CONFIG_JSON_OVERVIEW_IMAGE_INFO=y',
    'CONFIG_INCLUDE_CONFIG=y',
    '# CONFIG_PACKAGE_luci-ssl is not set',
    '# CONFIG_PACKAGE_libustream-mbedtls is not set',
    '# CONFIG_PACKAGE_libustream-wolfssl is not set',
    '# CONFIG_PACKAGE_nftables-nojson is not set',
]
config_lines += [f'CONFIG_PACKAGE_{p}=y' for p in packages]

(root / '.config').write_text('\n'.join(config_lines) + '\n')
print(f"Prepared official v24.10.2 profile: {profile} (compat: {compat_name})")
