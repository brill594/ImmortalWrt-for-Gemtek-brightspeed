include $(TOPDIR)/rules.mk

PKG_NAME:=iperf3-server
PKG_VERSION:=1.0
PKG_RELEASE:=1
PKG_LICENSE:=GPL-2.0-only
PKGARCH:=all

include $(INCLUDE_DIR)/package.mk

define Package/iperf3-server
  SECTION:=net
  CATEGORY:=Network
  TITLE:=LAN-only iperf3 server
  DEPENDS:=+iperf3 +netifd
endef

define Package/iperf3-server/description
 Start an iperf3 server on the LAN IPv4 address and device, using port 5201.
 Restart the listener when the LAN interface changes.
endef

define Build/Compile
endef

define Package/iperf3-server/install
	$(INSTALL_DIR) $(1)/etc/init.d
	$(INSTALL_BIN) ./files/iperf3-server.init $(1)/etc/init.d/iperf3-server
endef

$(eval $(call BuildPackage,iperf3-server))
