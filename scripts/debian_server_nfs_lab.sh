#!/usr/bin/env bash
set -Eeuo pipefail

package="${1:?Debian asset path required}"
package_sha="${2:?Debian asset SHA-256 required}"
output="${3:?NFS capture output required}"
export PYTHONPATH=/src PYTHONDONTWRITEBYTECODE=1 LC_ALL=C
python -c 'from scripts.isolated_linux_fixture import require_offline_container; require_offline_container()'
test ! -e "$output"
test "$package_sha" != ""
printf '%s  %s\n' "$package_sha" "$package" | sha256sum --check --strict
dpkg --install "$package"

work="$(mktemp -d /tmp/row-nfs-lab.XXXXXX)"
kernel_root=/opt/row-guest-kernel
guest="$work/guest"
initrd="$work/initrd"
mkdir -p "$guest" "$initrd"/{bin,dev,proc,sys,newroot}
kernel="$(find "$kernel_root/boot" -maxdepth 1 -type f -name 'vmlinuz-*' -print -quit)"
test -n "$kernel"
version="${kernel##*/vmlinuz-}"
if [[ ! -e "$kernel_root/lib" ]]; then ln -s usr/lib "$kernel_root/lib"; fi
depmod -b "$kernel_root" "$version"
install -m 0755 /bin/busybox "$initrd/bin/busybox"
ln -s busybox "$initrd/bin/sh"
install -m 0755 /src/scripts/debian_server_lab_init.sh "$initrd/init"
modules="/lib/modules/$version"
mkdir -p "$initrd$modules"
for index in modules.dep modules.alias modules.softdep modules.builtin; do
    cp "$kernel_root$modules/$index" "$initrd$modules/"
done
for needed in virtio_pci virtio_blk crc32c_generic ext4; do
    modprobe -d "$kernel_root" -S "$version" --show-depends "$needed"
done | while read -r command module rest; do
    if [[ "$command" == insmod ]]; then
        install -Dm0644 "$module" "$initrd${module#"$kernel_root"}"
    fi
done
(cd "$initrd"; find . -print0 | cpio --null -o --format=newc | gzip -1 > "$work/initramfs.gz")

tar -C / --one-file-system --exclude='./tmp' --exclude='./run' --exclude='./proc' \
    --exclude='./dev' --exclude='./sys' --exclude='./opt/row-guest-kernel' \
    --exclude='./src' --exclude='./release' --exclude='./proof' --exclude='./input' \
    -cf - . | tar -xf - -C "$guest"
mkdir -p "$guest"/{proc,sys,dev,run,tmp,lib/modules,qualification/release,qualification/repo}
chmod 1777 "$guest/tmp"
cp -a "$kernel_root$modules" "$guest/lib/modules/"
cp -r /src/scripts /src/src "$guest/qualification/repo/"
install -m 0755 /src/scripts/debian_server_lab_guest.sh "$guest/qualification/guest.sh"
cp -- "$package" "$guest/qualification/release/"
if [[ -f /input/source.json ]]; then cp /input/source.json "$guest/qualification/source.json"; fi

disk="$work/guest.img"
truncate -s 3G "$disk"
mke2fs -q -t ext4 -d "$guest" -m 0 -F "$disk"
timeout 240 qemu-system-x86_64 -machine q35 -cpu max -smp 2 -m 1024 -accel tcg,thread=multi \
    -display none -serial stdio -monitor none -nic none -no-reboot -kernel "$kernel" \
    -initrd "$work/initramfs.gz" -append 'console=ttyS0 rdinit=/init loglevel=4 panic=1' \
    -drive "file=$disk,format=raw,if=none,id=root" -device virtio-blk-pci,drive=root
mkdir "$work/export"
debugfs -R "dump /qualification/capture-complete $work/export/capture-complete" "$disk"
test -f "$work/export/capture-complete"
debugfs -R "rdump /qualification/captures $work/export" "$disk"
test -s "$work/export/captures/captures.json"
cp -r -- "$work/export/captures" "$output"
