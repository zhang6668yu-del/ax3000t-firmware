# AX3000T 34+78 MiB build

This workflow assembles OpenWrt 25.12.0 with its official ImageBuilder, kernel, drivers and release package repositories. It does not rebuild the kernel from source.

Target: `xiaomi_mi-router-ax3000t` (not `ubootmod` or `mtkuboot`). Includes AN8855 support, Chinese LuCI, HTTPS UI, ttyd and network tools.

Required layout: `ubi_kernel` at 0x600000, size 0x2200000; `ubi` at 0x2800000, size 0x4e00000. Intended for the already-recovered device with matching running layout. It is not a universal H-Uboot 112 MiB image.

Deliverable: sysupgrade.bin, checksums, manifest and verification.json. No bootloader or whole-flash image is delivered. Do not upload this sysupgrade archive as a raw U-Boot factory image.

Checks inspect the firmware's embedded DTB and FIT hashes, board metadata, NMBM, AN8855 and split-UBI upgrade code. Passing CI is not a hardware boot test. No firmware is flashed by this workflow.
