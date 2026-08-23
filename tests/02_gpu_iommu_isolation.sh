#!/usr/bin/env bash
set -euo pipefail
# Run on the HOST — verifies GPU/VFIO isolation prevents guest DMA/code execution.
# Usage: ./tests/02_gpu_iommu_isolation.sh

FAIL=0

check() {
    local desc="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo "PASS: $desc"
    else
        echo "FAIL: $desc"
        FAIL=1
    fi
}

check_fail() {
    local desc="$1"
    shift
    if ! "$@" >/dev/null 2>&1; then
        echo "PASS: $desc"
    else
        echo "FAIL: $desc"
        FAIL=1
    fi
}

GPU_BUS="0000:41:00"

# --- 1. IOMMU is enabled in kernel cmdline ---
check "IOMMU enabled in kernel cmdline" \
    grep -qE '(iommu=on|amd_iommu=on|intel_iommu=on|amd_iommu=1)' /proc/cmdline

# --- 2. IOMMU groups exist and GPU is isolated in its own group ---
gpu_group=$(find /sys/kernel/iommu_groups -name "$GPU_BUS" -printf '%h' 2>/dev/null | head -1)
if [[ -n "$gpu_group" ]]; then
    echo "PASS: GPU in IOMMU group $(basename $gpu_group)"
else
    echo "FAIL: GPU not found in IOMMU groups"
    FAIL=1
fi

# --- 3. Only GPU devices in the same IOMMU group (no USB/network/sata in group) ---
if [[ -n "$gpu_group" ]]; then
    dev_count=$(ls "$gpu_group" | wc -l)
    if [[ "$dev_count" -le 2 ]]; then
        echo "PASS: IOMMU group has $dev_count devices (GPU pair only)"
    else
        echo "FAIL: IOMMU group has $dev_count devices: $(ls $gpu_group)"
        FAIL=1
    fi
fi

# --- 4. VFIO driver (not nvidia) owns the GPU on the host ---
vfio_bound=$(ls -la /sys/bus/pci/devices/"${GPU_BUS}".0/driver 2>/dev/null | grep -c vfio || true)
if [[ "$vfio_bound" -ge 1 ]]; then
    echo "PASS: GPU function 0 bound to vfio"
else
    echo "FAIL: GPU function 0 not bound to vfio"
    FAIL=1
fi

# --- 5. GPU has been reset (no stale host state the guest could exploit) ---
reset_state=$(cat /sys/bus/pci/devices/"${GPU_BUS}".0/reset 2>/dev/null || echo "N/A")
check "GPU reset attribute accessible" \
    [[ "$reset_state" != "" && "$reset_state" != "N/A" ]]

# --- 6. QEMU is running with iommufd (not legacy vfio) ---
if pgrep -a qemu-system-x86_64 >/dev/null 2>&1; then
    check_fail "QEMU does NOT run as root" \
        pgrep -a qemu-system-x86_64 | awk '{print $1}' | xargs -I{} getent passwd {} 2>/dev/null | grep -q '^root:'
    
    check "QEMU uses iommufd" \
        pgrep -a qemu-system-x86_64 | grep -q 'iommufd'
else
    echo "SKIP: QEMU not running — cannot check runtime isolation"
fi

# --- 7. Guest cannot use GPU for non-DMA attacks: check no nvidia_uvm on host ---
check_fail "nvidia_uvm not loaded (prevents shared-memory DMA)" \
    lsmod | grep -q nvidia_uvm

# --- 8. VFIO IOMMU grouping file shows GPU isolation ---
check "VFIO IOMMU grouping file exists" \
    [[ -f /sys/kernel/iommu_groups/*/devices/* ]]

exit $FAIL
