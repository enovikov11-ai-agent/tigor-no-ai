# Tigor no AI Monorepo

> **Note:** Tigor AI Monorepo is autonomously edited by an AI agent under human direction and self-feedback loops. It is not a security boundary or source of truth. Control is primarily retroactive, with traceability enforced by linear git history.

> **Note:** Tigor no AI Monorepo requires human review for all commits. It contains authoritative specifications and security-critical code enforcing compartmentalization, virtualization, ACLs and specifications to build AI code upon.

See also https://github.com/enovikov11/tigor-ai

## Learnings

Memory can be encrypted with TSME, but it hurts perf
Numa, prefetcher, cpu timings, ram timings, boot guard
UMAF inspect
Editing chmod -x on all made vllm non executable and crashed inference and forgejo

## Code

find . -type f -exec sha256sum {} +

ssh box
ssh -J box root@127.0.0.1 -p 2222

ssh-keygen -R vm
ssh -o 'ProxyCommand=ssh box socat - VSOCK-CONNECT:3:22' root@vm

cd /etc/stateless/
nix build .#vm
cp /etc/stateless/result/vm-*-BOOTX64.efi /ssd/vm

cd /etc/stateless/
nix build .#host
mkdir /root/mnt
mount /dev/sde1 /root/mnt
df -h /root/mnt
cd /root/mnt/EFI/BOOT/
mv BOOTX64.efi "$(date '+%Y-%m-%d_%H-%M-%S')_BOOTX64.efi"
cp /etc/stateless/result/host-*-BOOTX64.efi /root/mnt/EFI/BOOT/BOOTX64.efi
sync
reboot now

diff /etc/stateless/flake.nix /etc/stateless/source.nix
nix build .#host
nixos-rebuild switch --flake .#vm --override flake.nix '{ modules = [{ networking.firewall.enable = true; }]; }'

apt install wireguard-tools
ufw allow 2026/udp
wg-quick up ./wg-hermes.conf

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
  
chmod 777 /run/hermes-passt.sock

podman load < result

ls /run/netns

tmux new-session -d -s hermes 'bash /etc/stateless/vm.sh'
tmux attach -t hermes
tmux new-session -s hermes 'bash /etc/stateless/vm.sh'
