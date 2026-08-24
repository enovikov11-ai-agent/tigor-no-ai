# Tigor no AI Monorepo

> **Note:** Tigor AI Monorepo is autonomously edited by an AI agent under human direction and self-feedback loops. It is not a security boundary or source of truth. Control is primarily retroactive, with traceability enforced by linear git history.

> **Note:** Tigor no AI Monorepo requires human review for all commits. It contains authoritative specifications and security-critical code enforcing compartmentalization, virtualization, ACLs and specifications to build AI code upon.

See also https://github.com/enovikov11/tigor-ai

| Domain  | Internet     | Virtualization | Cache encrypted | File sharing     |
| ------- | ------------ | -------------- | --------------- | ---------------- |
| Public  | Unrestricted | KVM            | No              | Public           |
| Private | Data diode   | KVM            | No              | Public + Private |
| Secret  | No           | KVM + SEV-ES   | Yes             | No               |

## Build

cd /etc/tigor/

diff flake.nix flake.nix.bak
diff vm.sh vm.sh.bak
diff vm.xsl vm.xsl.bak

nix build .#vm
cp ./result/vm-*-BOOTX64.efi /ssd/public/vm/kernels/
echo -e '\a'

nix build .#host
mkdir /root/mnt
mount /dev/sde1 /root/mnt
df -h /root/mnt
mv /root/mnt/EFI/BOOT/BOOTX64.efi /root/mnt/EFI/BOOT/"$(date '+%Y-%m-%d_%H-%M-%S')_BOOTX64.efi"
cp ./result/host-*-BOOTX64.efi /root/mnt/EFI/BOOT/BOOTX64.efi
echo -e '\a'

sync && reboot now

## Code

find . -type f -exec sha256sum {} +

ssh box
ssh -J box root@127.0.0.1 -p 2222

ssh-keygen -R vm
ssh -o 'ProxyCommand=ssh box socat - VSOCK-CONNECT:3:22' root@vm

qemu-img create -f qcow2 /ssd/vm/hermes.qcow2 500G
mkfs.ext4 -L data /dev/vda
chown -R nixos:users /home/nixos

nixos-rebuild switch --flake .#vm --override flake.nix '{ modules = [{ networking.firewall.enable = true; }]; }'

sshfs nixos@10.67.69.2:/home/nixos /home/nixos -o Port=2222,reconnect
echo o > /proc/sysrq-trigger
nft flush ruleset

codeberg.org/forgejo/forgejo:16
podman pull docker.io/vllm/vllm-openai:nightly
podman save docker.io/vllm/vllm-openai:nightly | gzip > /home/nixos/vllm.tar.gz
gunzip -c vllm.tar.gz | podman load

cd /ssd/internet
chown -R nixos:users .
find . -type d -exec chmod 2775 {} +
find . -type f -exec chmod 664 {} +

podman load < result
ls /run/netns
virsh undefine hermes --nvram
xsltproc --nonet vm.xsl vm.xsl

chmod 777 /run/user/1000/podman/podman.sock

## TODO

Download models
Caddy http / no inet on vllm, forgejo, pages.ai.tgr.rs
CA *.tgr
Cloud init ssh host key
Gpu burn & telegraf
Gateway: matrix/mattermost
vm.sh: control plane via tg/web
vm.sh: make all args
vm.sh: non-root + premade sockets by root
vm.sh: test bubblewrap (need nested)
vm.sh: compare with qemu libvirt command
Data diode

Hermes memory setup (honcho.dev), qdrant, graphify

Secrets scanning
Sec invariants check
Secureboot + tpm
Gpu reset
Make a commits scanner with memory and gateway
Experiment with Dflash
Independent builder
Reject GPG unverified
Git scan: license
Git scan: commits summary and digest
Nixos config compartmentalization, less privileged code
Simplify nix on amount of hidden options, shown via full eval
Better hash algo: mkpasswd -m yescrypt -R 11

### Data diode & data hoarding /internet

Docker images
Telegram proxy
Nix copy
Git clone

### Invariants to check via tests

- VM cannot send or receieve any packages outside of wg tunnel
- VM cannot execute any code at host, cannot read its memory via DMA on GPU
- VM cannot login to 10.67.69.1

### Misc

Dump rtx pro Nvidia chip dump for backup
SEV ES & nvidia-smi conf-compute -q
Reproducible builds verifyer for other projects
Libreboot image with disc encryption
Denominations simulator - cash economy math model game
Jetkvm
Move to Xen from KVM
Buy CMP 170HX cluster

## Learnings

Memory can be encrypted with TSME, but it hurts perf
Numa, prefetcher, cpu timings, ram timings, boot guard
UMAF inspect
Editing chmod -x on all made vllm non executable and crashed inference and forgejo
