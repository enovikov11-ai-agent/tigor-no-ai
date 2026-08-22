# VM runner

qemu-system-x86_64: warning: IOMMU_IOAS_MAP failed: Bad address, PCI BAR?

Make VM have full inet; Move hermes to docker
Harden vm.sh, because it runs as root
Compare qemu command with libvirt command, and research overall security

# Infra

.hermes publish
Download models
Dflash
Gpu burn telegraf
Pages deployment in my infra
Wpex & udp punch
Telegraf: fix host, vm
Control plane via tg/web
Cloud init: ssh host key, podman compose up -d, network config

# Data diode & data hoarding /internet

Docker images
Telegram proxy
Nix copy
Git clone

# General security

Independent builder

Nested vm run
nosuid img mount
gpu reset http://10.67.69.1:3000/hermes/tigor/compare/main...gpu-reset

multiple VMs

git scan: license
git scan: commits summary and digest
userspace VPN
Secureboot
Nixos config compartmentalization, less privileged code
Decide what sec invariants are
Simplify nix on amount of hidden options, shown via full eval
Better hash algo: mkpasswd -m yescrypt -R 11

# RTX PRO

Dump rtx pro Nvidia chip dump for backup
SEV ES & nvidia-smi conf-compute -q

# Big ideas maybe to do

Move to Xen from KVM
Buy CMP 170HX
