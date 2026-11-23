#!/bin/busybox sh
set -e
export PATH=/bin
busybox mount -t proc proc /proc
busybox mount -t sysfs sys /sys
busybox mount -t devtmpfs dev /dev
busybox ln -s /proc/self/fd /dev/fd
busybox ln -s /proc/self/fd/0 /dev/stdin
busybox ln -s /proc/self/fd/1 /dev/stdout
busybox ln -s /proc/self/fd/2 /dev/stderr
busybox modprobe virtio_pci
busybox modprobe virtio_blk
busybox modprobe crc32c_generic
busybox modprobe ext4
busybox mount -t ext4 -o rw /dev/vda /newroot
busybox mount --move /dev /newroot/dev
busybox mount --move /sys /newroot/sys
busybox mount --move /proc /newroot/proc
exec busybox switch_root -c /dev/console /newroot /qualification/guest.sh
