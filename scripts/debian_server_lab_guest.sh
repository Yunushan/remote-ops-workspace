#!/bin/bash
set -Eeuo pipefail
export PATH=/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin LC_ALL=C ROW_HOME=/run/row
umask 077
root=/qualification
port=12049
account=rownfs
realm=ROW.TEST
fqdn=nfs.row.test
logs=/run/row-fixture-logs

finish() {
    status=$?
    trap - EXIT
    set +e
    if (( status )); then echo "Debian NFS guest failed with exit status $status" >&2; fi
    sync
    /bin/busybox poweroff -f
}
trap finish EXIT

mount -t tmpfs tmpfs /run
mkdir -p /dev/pts /run/rpc_pipefs /run/gssproxy /run/krb5kdc /run/lock "$logs" /etc/nfs.conf.d
mount -t devpts devpts /dev/pts
ip link set lo up
hostname "$fqdn"
printf '127.0.0.1 %s localhost\n::1 localhost ip6-localhost\n' "$fqdn" > /etc/hosts

/usr/bin/row servers config-plan nfs --host 127.0.0.1 --port "$port" --json |
    python -c '
import json
import sys
from pathlib import Path

plan = json.load(sys.stdin)
if not plan["auth_required"] or plan["settings"]["auth"]["source"] != "kerberos-rpcsec-gss":
    raise ValueError("packaged NFS plan does not require the expected Kerberos authentication")
sections = plan["settings"]["host_config"]["nfs.conf"]
config = "".join(f"[{name}]\n" + "".join(f"{key}={value}\n" for key, value in rows.items())
                 for name, rows in sections.items())
Path("/etc/nfs.conf.d/99-row-fixture.conf").write_text(config, encoding="utf-8")
    '

cat > /etc/krb5.conf <<'EOF'
[libdefaults]
 default_realm = ROW.TEST
 dns_lookup_realm = false
 dns_lookup_kdc = false
 rdns = false
 dns_canonicalize_hostname = false
[realms]
 ROW.TEST = {
  kdc = 127.0.0.1:88
 }
[domain_realm]
 .row.test = ROW.TEST
 row.test = ROW.TEST
EOF
cat > /etc/krb5kdc/kdc.conf <<'EOF'
[kdcdefaults]
 kdc_listen = 127.0.0.1:88
 kdc_tcp_listen = 127.0.0.1:88
[realms]
 ROW.TEST = {
  database_name = /var/lib/krb5kdc/row-fixture
  key_stash_file = /run/krb5kdc/row-fixture-stash
 }
EOF
cat > /etc/idmapd.conf <<'EOF'
[General]
 Domain = row.test
[Mapping]
 Nobody-User = nobody
 Nobody-Group = nogroup
EOF
kdb5_util -r "$realm" create -s -P "$(openssl rand -hex 24)" > "$logs/realm.log" 2>&1
useradd -m -s /bin/sh "$account"
kadmin.local -r "$realm" -q "addprinc -randkey nfs/$fqdn" > "$logs/principals.log" 2>&1
kadmin.local -r "$realm" -q "ktadd -k /etc/krb5.keytab nfs/$fqdn" >> "$logs/principals.log" 2>&1
kadmin.local -r "$realm" -q "addprinc -randkey $account" >> "$logs/principals.log" 2>&1
client_keytab=/run/krb5kdc-client.keytab
kadmin.local -r "$realm" -q "ktadd -k $client_keytab $account" >> "$logs/principals.log" 2>&1
chown "$account:$account" "$client_keytab"
chmod 0600 /etc/krb5.keytab "$client_keytab"
/usr/sbin/krb5kdc -n -r "$realm" > "$logs/kdc.log" 2>&1 &
for attempt in {1..20}; do
    if runuser -u "$account" -- kinit -k -t "$client_keytab" "$account@$realm" > "$logs/ticket.log" 2>&1; then break; fi
    if (( attempt == 20 )); then echo "Kerberos client could not obtain a ticket" >&2; exit 1; fi
    sleep 0.25
done

modprobe nfsd
modprobe nfs
modprobe rpcsec_gss_krb5
mount -t nfsd nfsd /proc/fs/nfsd
mount -t rpc_pipefs rpc_pipefs /run/rpc_pipefs
install -d -m 0755 /export/row-proof
marker=/export/row-proof/marker.txt
printf 'row-nfs-fixture-%s\n' "$(openssl rand -hex 24)" > "$marker"
chown "$account:$account" "$marker"
chmod 0640 "$marker"
printf '/export/row-proof 127.0.0.1(ro,fsid=0,sync,root_squash,no_subtree_check,sec=krb5p)\n' > /etc/exports
exportfs -r
gssproxy -i > "$logs/gssproxy.log" 2>&1 &
for attempt in {1..20}; do
    if grep -qx 1 /proc/net/rpc/use-gss-proxy; then break; fi
    if (( attempt == 20 )); then echo "kernel GSS proxy did not become ready" >&2; exit 1; fi
    sleep 0.25
done
rpc.mountd -F -N 2 -N 3 > "$logs/mountd.log" 2>&1 &
rpc.gssd -f -p /run/rpc_pipefs > "$logs/gssd.log" 2>&1 &
nfsdcld > "$logs/nfsdcld.log" 2>&1 &

mapfile -t packages < <(find "$root/release" -maxdepth 1 -type f -name '*.deb')
test "${#packages[@]}" = 1
mode=(--local)
if [[ -f "$root/source.json" ]]; then mode=(--source "$root/source.json"); fi
python "$root/repo/scripts/capture_debian_server_clients.py" \
    --deb "${packages[0]}" "${mode[@]}" --out "$root/captures" \
    nfs --hostname "$fqdn" --port "$port" --account "$account" --challenge "$marker"
test "$(cat /proc/fs/nfsd/threads)" = 0
touch "$root/capture-complete"
