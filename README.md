# Xiaomi AX3000T (MT7531 & AN8855) 112M UBI Firmware

本项目为 **小米路由器 AX3000T (RD03 / MT7981 / 128MB NAND)** 定制固件构建，完全基于 **官方 ImmortalWrt v24.10.2 正式发布版源码**。

---

## 核心特性

1. **官方 Release 基线 & 完整 ABI 匹配**：
   - 基于官方 `immortalwrt/immortalwrt` release tag `v24.10.2`；
   - 内核版本与 kmod ABI 与官方 24.10.2 发布版 100% 完全匹配；
   - **直接支持官方 ImmortalWrt 24.10.2 软件源**（以及国内清华镜像源 `mirrors.tuna.tsinghua.edu.cn/immortalwrt`），告别不稳定的第三方自建源。

2. **无线功能原生恢复 (修复无 Wi-Fi Bug)**：
   - 彻底废弃导致无 Wi-Fi 菜单的 MTK 闭源驱动方案；
   - 全面采用官方标准的开源 Linux mac80211 / mt76 驱动栈（`kmod-mt7915e` + `kmod-mt7981-firmware` + `mt7981-wo-firmware` + `wpad-openssl`）；
   - 开机自动生成 `/etc/config/wireless`，LuCI 后台【网络】->【无线】原生显示，2.4G / 5G 信号正常发射并支持标准 Web 配置。

3. **双硬件版本完整支持 (严禁混刷)**：
   - **MT7531** 交换芯片版本：`xiaomi_mi-router-ax3000t-mtkuboot` (`xiaomi,mi-router-ax3000t-mtkuboot`)
   - **AN8855** 交换芯片版本：`xiaomi_mi-router-ax3000t-an8855-mtkuboot` (`xiaomi,mi-router-ax3000t-an8855-mtkuboot`)
   - 官方内核原生内建 AN8855 DSA / PHY / MFD 驱动，免打补丁，免破坏 ABI。

4. **保持已实机验证的 H-Uboot 112M 布局**：
   - 适配 H大 / hanwckf U-Boot multi-layout 中的 `immortalwrt-112m` 布局；
   - UBI 分区偏移 `0x600000`，长度 `0x7000000`（112 MiB 总容量）；
   - 保留原机 Nvram (mtd1)、Bdata (mtd2)、Factory (mtd3)、FIP (mtd4) 等基础关键分区；
   - 每个硬件版本均提供 `factory.bin`（H-Uboot Web 刷入）与 `sysupgrade.bin`（后台系统升级）。

---

## 构建与固件文件

GitHub Actions 自动为两款硬件独立构建：
- `AX3000T-MT7531-H-Uboot-112M-24.10.2-factory.bin`
- `AX3000T-MT7531-H-Uboot-112M-24.10.2-sysupgrade.bin`
- `AX3000T-AN8855-H-Uboot-112M-24.10.2-factory.bin`
- `AX3000T-AN8855-H-Uboot-112M-24.10.2-sysupgrade.bin`
