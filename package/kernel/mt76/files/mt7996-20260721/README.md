# MT7996 firmware 20260721

Unmodified WM, WA, DSP and ROM patch from MediaTek's unified Filogic 25.12
feed. The pinned source revision, original URLs, SHA256, sizes and internal
build dates are recorded in `manifest.json`.

The standard `kmod-mt7996-firmware` package installs the new WM, WA and ROM
patch; `kmod-mt7996-firmware-common` installs the matching DSP when the
standard package is selected. EEPROM files still come from the pinned mt76
source. An image selecting only the 2+3+3 firmware variant retains its
original upstream DSP and variant binaries. Do not mix standard and 2+3+3
firmware packages in one image.

This checkout is based on `20260923-ba2d9bc4`
(`512ea01c99775f4d780dbfbc48dcb4a43f1638f5`), the running XR1710G firmware
release. It preserves the original `gemtek,xr1710g-ubi` image layout, mt76
`be5ce7910521492d4a2e4ce7ee3843680a46c047`, kernel/NPU integration and
board patches. `PKG_RELEASE` is incremented to 2 so rebuilt packages can be
distinguished from the existing release.

Use the repository's `1710.config` and build workflow to prepare feeds,
apply feed patches and configure the image. Select only the
`gemtek_xr1710g-ubi` sysupgrade artifact for the existing AP layout.
Do not substitute current master device-tree/bootloader files: master has
introduced a different XR1710G UBI layout since this release.

The binaries' packaging can be checked without compiling the kernel.
Their AN7581/NPU 0.1111 runtime compatibility, throughput and stability
have not been verified. Loading them on the router requires a separate
wireless/device restart and a recovery path. No router deployment is part
of this source change.
