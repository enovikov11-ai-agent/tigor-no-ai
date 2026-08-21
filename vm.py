#!/usr/bin/env python3
import ctypes, os, signal, subprocess, sys, time

def main(cfg):
    n = cfg["name"]
    run_dir = f"/run/vm-{n}"

    # sockets dir
    subprocess.run(["rm", "-rf", run_dir], check=False)
    os.makedirs(run_dir)

    def cleanup():
        for p in children:
            try: p.kill()
            except OSError: pass
        for p in children:
            p.wait()
        subprocess.run(["rm", "-rf", run_dir], check=False)
        subprocess.run(["ip", "netns", "del", f"ns-{n}"], check=False)

    # SIGINT/SIGTERM -> cleanup + exit
    def _h(s, _):
        cleanup()
        sys.exit(128 + s)
    for s in (signal.SIGINT, signal.SIGTERM):
        signal.signal(s, _h)

    # children die on parent death
    try:
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGKILL)
    except Exception:
        pass

    ns = f"ns-{n}"
    wg = f"wg-{n}"
    children = []

    def wait_sock(path):
        for _ in range(100):
            if os.path.exists(path): return
            time.sleep(0.01)
        sys.exit(f"socket timeout: {path}")

    # ── ip ──
    subprocess.run(["rm", "-f", f"/run/vm-{n}-passt.sock"], check=False)
    subprocess.run(["ip", "netns", "add", ns], check=True)
    subprocess.run(["ip", "link", "add", wg, "type", "wireguard"], check=True)
    subprocess.run(["wg", "setconf", wg, f"/ssd/vm/ns-wg-{n}.conf"], check=True)
    subprocess.run(["ip", "link", "set", wg, "netns", ns], check=True)
    subprocess.run(["ip", "-n", ns, "addr", "add", "10.67.69.2/24", "dev", wg], check=True)
    subprocess.run(["ip", "-n", ns, "link", "set", wg, "up"], check=True)
    subprocess.run(["ip", "-n", ns, "route", "add", "default", "via", "10.67.69.1", "dev", wg], check=True)

    # ── passt ──
    passt_sock = f"{run_dir}/passt.sock"
    subprocess.run(["rm", "-f", passt_sock], check=False)
    children.append(subprocess.Popen(
        ["ip", "netns", "exec", ns, "passt", "--foreground", "--vhost-user",
         "--socket", passt_sock, "--repair-path", "none",
         "--interface", wg, "--outbound-if4", wg,
         "--ipv4-only", "--mtu", "1420", "--address", "10.67.69.2", "--netmask", "24",
         "--gateway", "10.67.69.1", "--no-map-gw", "--map-host-loopback", "none",
         "--map-guest-addr", "none", "--tcp-ports", "all", "--udp-ports", "all"],
        stdin=subprocess.DEVNULL, stdout=subprocess.STDOUT))
    wait_sock(passt_sock)

    # ── virtiofsd ──
    fs_args = []
    for i, m in enumerate(cfg["mounts"]):
        sock = f"{run_dir}/fs-{i}.sock"
        subprocess.run(["rm", "-f", sock], check=False)
        c = ["virtiofsd", "--socket-path", sock, "--shared-dir", m["src"]]
        if m.get("readonly"):
            c.append("--readonly")
        children.append(subprocess.Popen(c, stdin=subprocess.DEVNULL, stdout=subprocess.STDOUT))
        wait_sock(sock)
        fs_args += ["-chardev", f"socket,id=fs{i},path={sock}",
                    "-device", f"vhost-user-fs-pci,chardev=fs{i},tag={m['dst']}"]

    # ── qemu ──
    a = [
        "-nodefaults", "-no-user-config",
        "-machine", "pc-q35-10.2,memory-backend=ram,usb=off,vmport=off,smm=off,dump-guest-core=off",
        "-accel", "kvm", "-cpu", "host,migratable=off",
        "-object", f"memory-backend-memfd,id=ram,size={cfg['ram']}G,share=on,hugetlb=on,hugetlbsize=1G",
        "-smp", str(cfg["cpu"]), "-rtc", "base=utc",
        "-drive", "if=pflash,format=raw,readonly=on,file=/run/libvirt/nix-ovmf/edk2-x86_64-code.fd",
        "-kernel", cfg["kernel"],
        "-sandbox", "on,obsolete=deny,elevateprivileges=deny,spawn=deny,resourcecontrol=deny",
        "-object", "rng-random,id=rng,filename=/dev/urandom",
        "-device", "virtio-rng-pci,rng=rng", "-display", "none",
    ]
    if cfg["vsock"]:
        a += ["-device", "vhost-vsock-pci,guest-cid=auto"]
    a += ["-serial", "stdio", "-monitor", "none"]
    a += ["-drive", f"file={cfg['disk']},if=virtio,format=qcow2,discard=unmap"]
    if cfg["gpu"]:
        a += ["-object", "iommufd,id=iommufd0",
              "-device", "vfio-pci,host=0000:41:00.0,iommufd=iommufd0",
              "-device", "vfio-pci,host=0000:41:00.1,iommufd=iommufd0"]
    a += ["-chardev", f"socket,id=net0,path={passt_sock}",
          "-netdev", "vhost-user,chardev=net0,id=net",
          "-device", f"virtio-net-pci,netdev=net,mac=52:54:00:a9:f5:da,romfile=,addr=0x0,bus=pcie.{cfg['net_bus'][2:]}"]
    a += fs_args

    r = subprocess.run(["qemu-system-x86_64", *a], stdin=sys.stdin, stdout=subprocess.STDOUT)
    cleanup()
    sys.exit(r.returncode)

if __name__ == "__main__":
    main({
        "name": "hermes",
        "cpu": 64,
        "ram": 128,
        "kernel": "/ssd/vm/vm-r17-nvda-pods-vsock-BOOTX64.efi",
        "gpu": True,
        "vsock": True,
        "ui": True,
        "net_bus": "0x04",
        "disk": "/ssd/vm/hermes.qcow2",
        "mounts": [
            {"src": "/ssd/internet", "dst": "/ssd/internet", "readonly": True},
            {"src": "/hdd/internet/kiwix", "dst": "/hdd/internet/kiwix", "readonly": True},
            {"src": "/hdd/internet/wikipedia", "dst": "/hdd/internet/wikipedia", "readonly": True},
            {"src": "/ssd/vm/hermes", "dst": "/ssd/vm/hermes"},
            {"src": "/ssd/telegraf/hermes", "dst": "/ssd/telegraf/host"},
        ],
    })
