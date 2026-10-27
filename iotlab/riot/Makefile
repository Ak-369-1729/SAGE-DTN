# SAGE-DTN testbed node for FIT IoT-LAB (RIOT OS).
#   make BOARD=iotlab-m3 RIOTBASE=~/RIOT          (default board: IoT-LAB M3, AT86RF231 802.15.4 radio)
#   make BOARD=nrf52dk / nrf52840dk / samr21-xpro  (other IoT-LAB boards with an 802.15.4 radio)
APPLICATION = sage-node
BOARD ?= iotlab-m3
RIOTBASE ?= $(HOME)/RIOT

# 802.15.4 channel; pick one other IoT-LAB users are unlikely to use (11-26)
SAGE_CHANNEL ?= 22
DEFAULT_CHANNEL = $(SAGE_CHANNEL)

EXTERNAL_MODULE_DIRS += $(CURDIR)/..
USEMODULE += sage_app
INCLUDES += -I$(CURDIR)/../sage_app

# one-hop link-local multicast over 6LoWPAN/IPv6/UDP
USEMODULE += netdev_default
USEMODULE += auto_init_gnrc_netif
USEMODULE += gnrc_netif_single
USEMODULE += gnrc_ipv6_default
USEMODULE += gnrc_sock_udp
USEMODULE += shell
USEMODULE += ztimer_msec
USEMODULE += ztimer_usec
USEMODULE += hashes

# local test on BOARD=native64 with an emulated 802.15.4 radio (RIOT's ZEP dispatcher)
ifeq (native64,$(BOARD))
  USEMODULE += socket_zep
endif

FEATURES_REQUIRED += cpp
CXXEXFLAGS += -std=gnu++17

# machine-readable serial output: no shell prompt or echo
CFLAGS += -DSHELL_NO_PROMPT=1 -DSHELL_NO_ECHO=1

DEVELHELP ?= 0
QUIET ?= 1

include $(RIOTBASE)/Makefile.include
include $(RIOTMAKE)/default-radio-settings.inc.mk
