# Home AI Box

find . -type f -exec sha256sum {} +

## Commands

### Host
ssh root@192.168.1.28

### VM (via SSH port forward on host)
ssh -J root@192.168.1.28 root@127.0.0.1 -p 2222

### VM (via vsock — independent of network config)
From host: `ssh -o ProxyCommand='vsock-sendto %h %p' nixos@3`

From laptop (YubiKey on laptop, jump through host):
```
ssh -o ProxyCommand='ssh root@192.168.1.28 vsock-sendto %h %p' nixos@3
```

Or via SSH config (`~/.ssh/config`):
```
Host vm-vsock
  HostName 3
  User nixos
  ProxyCommand ssh root@192.168.1.28 vsock-sendto %h %p
```

Connect with: `ssh vm-vsock`

nix build
mkdir /root/mnt
mount /dev/sde1 /root/mnt
df -h /root/mnt
cd /root/mnt/EFI/BOOT/
mv BOOTX64.efi "$(date '+%Y-%m-%d_%H-%M-%S')_BOOTX64.efi"
cp /root/result/host-*-BOOTX64.efi /root/mnt/EFI/BOOT/BOOTX64.efi
sync
umount /root/mnt
reboot now

diff /etc/stateless/flake.nix /etc/stateless/source.nix
nix build .#host
nixos-rebuild switch --flake .#vm --override flake.nix '{ modules = [{ networking.firewall.enable = true; }]; }'

virsh dumpxml hermes

apt install wireguard-tools
ufw allow 2026/udp
wg-quick up ./wg-hermes.conf

ip addr add 10.67.69.2/24 dev eth0
ip route add 10.67.69.1/32 dev eth0

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

qemu-img create -f qcow2 /ssd/vm/hermes.qcow2 500G
mkfs.ext4 -L data /dev/vda
chown -R nixos:users /home/nixos

## Learnings

Memory can be encrypted with TSME, but it hurts perf
Numa, prefetcher, cpu timings, ram timings, boot guard
UMAF inspect
Editing chmod -x on all made vllm non executable and crashed inference and forgejo

## Ideas

tigor-no-ai
reject unverified

.hermes sec edit & publish

policy flags

Nixos config compartmentalization, less privileged code
Vpn configuration for VM
Nosuid img mount
Commits organization

Dump rtx pro Nvidia chip dump for backup
Hermes VPN sharing OR Digitalocean image + VPS

Cloud init: ssh host key, podman compose up -d, network config
Local portal with VPN
Simplify nix on amount of hidden options, shown via full eval
Control plane via tg/web
Agent usernet: enable firewall, no host wg0:22, --outbound-if4 wg0 --outbound-if6 wg0 not -i wg0, add --no-map-gw --map-host-loopback present

tigor-ai monitoring

http://10.67.69.1:3000/hermes/tigor/compare/main...gpu-reset
http://10.67.69.1:3000/hermes/tigor/compare/main...isolate-host-params

Proxy: hermes tg
Proxy: nix copy, podman load, git clone
Nix builder VM with persistent store

Better hash algo: mkpasswd -m yescrypt -R 11
nvidia-smi conf-compute -q
USB mouse passthrough to VM
Lightweight repo and nix build github:owner/repo
Xen?
