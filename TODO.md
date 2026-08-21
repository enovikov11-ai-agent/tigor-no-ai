# VM runner

Make VM have full inet; Move hermes to docker
Harden vm.sh, because it runs as root
Compare qemu command with libvirt command, and research overall security

# Infra

.hermes publish
Download models
Dflash
Gpu burn telegraf
pages deployment in my infra
Wpex & udp punch
telegraf: fix host, vm
control plane via tg/web

cloud init: ssh host key, podman compose up -d, network config

# Data diode & data hoarding /internet

download dockers
proxy: hermes tg
proxy: nix copy, podman load, git clone
nix builder VM with persistent store

# General security

Lightweight repo and nix build github:owner/repo
nixos config compartmentalization, less privileged code

Security tests
git scanner for license check
tigor-ai git code monitoring agent

userspace VPN
nosuid img mount
secureboot

gpu reset http://10.67.69.1:3000/hermes/tigor/compare/main...gpu-reset
isolate host params http://10.67.69.1:3000/hermes/tigor/compare/main...isolate-host-params

simplify nix on amount of hidden options, shown via full eval

better hash algo: mkpasswd -m yescrypt -R 11

# rtx pro

dump rtx pro Nvidia chip dump for backup

nvidia-smi conf-compute -q

# Big ideas maybe to do

Move to Xen from KVM
Buy CMP 170HX
