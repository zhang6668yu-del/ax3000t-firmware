REQUIRE_IMAGE_METADATA=1
PART_NAME=firmware

# This image is only for the merged H-Uboot 112 MiB layout.
# Refuse to write if a stock/split layout is visible to the running kernel.
ax3000t_112m_layout_ok() {
	[ "$(board_name)" = "xiaomi,mi-router-ax3000t" ] || return 1
	[ -z "$(find_mtd_index ubi_kernel)" ] || return 1
	local index="$(find_mtd_index ubi)"
	[ -n "$index" ] || return 1
	[ "$(cat /sys/class/mtd/mtd${index}/size)" = "117440512" ] || return 1
	[ "$(hexdump -v -e '1/1 "%02x"' /sys/class/mtd/mtd${index}/of_node/reg)" = "0060000007000000" ] || return 1
}

platform_check_image() {
	ax3000t_112m_layout_ok || {
		echo 'Requires migrated H-Uboot single 112 MiB UBI layout; do not force sysupgrade from 34+78 MiB.'
		return 1
	}
	nand_do_platform_check "$(board_name)" "$1"
}

platform_do_upgrade() {
	ax3000t_112m_layout_ok || {
		echo 'Wrong NAND layout. Refusing flash write.'
		nand_do_upgrade_failed
		return 1
	}
	CI_UBIPART=ubi
	CI_KERN_UBIPART=
	CI_ROOT_UBIPART=
	CI_KERNPART=kernel
	CI_ROOTPART=rootfs
	nand_do_upgrade "$1"
}
