# AX3000T MT7531 / H-Uboot 112 MiB / OpenWrt 25.12.5

Built with the official 25.12.5 ImageBuilder and kernel, using the AX3000T device tree with its upstream MT7531 and AN8855 detection support preserved. Only the stock split UBI partitions are merged into a single 112 MiB UBI partition at 0x600000. MT7531 MDIO address, CPU port, WAN/LAN labels and fixed link are checked explicitly. This is not a relabelled binary artifact.

Reference U-Boot SHA256: 226c4bce28d6b7574f0f98f8eee52ea291c49dc2c9ba35626651bbbea1b0ec6e
Reference old factory SHA256: 108bd8c4ab2bd18cade5730f90e3128a2cd637b337c348f9d6fadc455efdbc1d
Both supplied reference files declare the 0x600000 / 0x7000000 UBI layout. Reference files are not redistributed or installed. No bootloader flashing is part of these images.

Features: LuCI Chinese, HTTPS, ttyd, dnsmasq-full, TUN, nftables TProxy/socket/NAT, Ruby YAML, Lua compatibility, DNS helper tools. Uses matching OpenWrt release/kmod APK repositories and signed PassWall release repositories. GitHub checks apk update and simulated installation of Sing-box and PassWall against the shipped package database and keys. Does not preinstall PassWall/OpenClash UI, Xray, Sing-box or Mihomo. Unneeded microsocks and ipt2socks are omitted from this build.

## Installation scope
Use only on Xiaomi AX3000T MT7531 with a compatible H-Uboot 112 MiB layout. On the supplied multi-layout U-Boot, choose immortalwrt-112m and upload the factory image through the firmware page. Do not use the U-Boot update page. Do not force sysupgrade from stock 34+78 MiB. Sysupgrade is for an already compatible 112 MiB system. Back up the individual device first.

No MT7531 hardware was available. Static image/layout/hash checks and repository dependency resolution are not physical boot, Wi-Fi, WAN or power-cycle tests. The earlier AN8855 hardware result does not constitute MT7531 validation. Do not promise verified customer deployment until a matching unit has passed these tests.
