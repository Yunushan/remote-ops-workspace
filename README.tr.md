<div align="center">

# Remote Ops Workspace

### SSH, RDP, VNC, SFTP, Mosh, Telnet, X11, SPICE, X2Go, ICA, HTTP/HTTPS, seri konsollar, raw socket'ler, bolunmus paneller, vault, snippet, sync, CLI, GUI ve Web/PWA icin operator odakli uzak erisim calisma alani.

![build](https://img.shields.io/badge/build-source--available-brightgreen)
![release](https://img.shields.io/badge/release-v0.1.0-blue)
![license](https://img.shields.io/badge/license-MIT-blue)
![runtime](https://img.shields.io/badge/runtime-Python%203.10--3.14-orange)
![interfaces](https://img.shields.io/badge/interfaces-CLI%20%7C%20GUI%20%7C%20Web-purple)
![targets](https://img.shields.io/badge/targets-Windows%20%7C%20Linux%20%7C%20macOS%20%7C%20BSD%20%7C%20Solaris%20%7C%20Android%20%7C%20Web-green)
![protocols](https://img.shields.io/badge/protocols-SSH%20%7C%20RDP%20%7C%20VNC%20%7C%20SFTP%20%7C%20Mosh%20%7C%20Telnet%20%7C%20SPICE%20%7C%20X2Go-yellow)

[Hizli Baslangic](#hizli-baslangic) - [CLI](#cli) - [GUI](#gui) - [Web/PWA](#webpwa) - [Ozellik Kapsami](#ozellik-kapsami) - [Platformlar](#platformlar) - [Guvenlik](#guvenlik) - [Lisans](#lisans)

[English](README.md) - Turkce

</div>

---

## Bu Proje Nedir?

**Remote Ops Workspace**, MobaXterm, Remmina, mRemoteNG, Terminator ve Termius gibi araclarda beklenen ozellik aileleri icin MIT lisansli, capraz platform bir uzak erisim calisma alanidir.

Proje bilincli olarak **adapter-first** tasarlanmistir: CLI, profil deposu, guvenli argv tabanli baslaticilar, istege bagli sifreli vault, PyQt6 GUI kabugu, Web/PWA kabugu, ozellik kapsami manifesti, testler, kurulum betikleri, CI ve yayin iskeleti bulunur. Protokol motorlari yeniden yazilmaz; OpenSSH, FreeRDP, TigerVNC, x2goclient, virt-viewer, PuTTY, Windows MSTSC, XQuartz/VcXsrv/Xorg gibi yerel istemciler veya ileride eklenebilecek protokol eklentileri kullanilir.

> Bu proje Mobatek/MobaXterm, Remmina, mRemoteNG, GNOME Terminator veya Termius ile baglantili degildir. Urun adlari yalnizca uyumluluk hedeflerini ve ozellik kapsamini aciklamak icin kullanilir.

---

## Hizli Baslangic

```bash
git clone https://github.com/YOUR-ORG/remote-ops-workspace.git
cd remote-ops-workspace

python -m venv .venv
# Linux/macOS/BSD/Solaris
. .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1

pip install -e ".[desktop,security]"
row init
row profile add --name lab-ssh --protocol ssh --host 192.0.2.10 --username admin
row connect lab-ssh --dry-run
row doctor
```

Masaustu arayuzu:

```bash
row gui
```

Tarayici/PWA arayuzu:

```bash
row serve-web --host 127.0.0.1 --port 8765
```

---

## CLI

```bash
row init
row profile add --name core-rdp --protocol rdp --host 192.0.2.20 --username administrator
row profile add --name switch-console --protocol serial --path /dev/ttyUSB0 --option baud=115200
row profile add --name jump-ssh --protocol ssh --host 192.0.2.10 --username admin --option proxy_jump=bastion --option keepalive_interval=30
row profile add --name lab-vnc --protocol vnc --host 192.0.2.30 --option fullscreen=true --option shared=true
row profile list
row profile show core-rdp
row connect core-rdp --dry-run
row connect core-rdp
row features
row platforms
row vault init
row vault status
row vault set prod/router-password --secret-env ROW_ROUTER_PASSWORD
row vault list
row vault delete old/router-password --force
row plugins list
row features --coverage
row files ls lab-ssh /var/log --dry-run
row files get lab-ssh /etc/hosts --local ./hosts.copy --dry-run
row files queue lab-ssh --op "get /etc/hosts ./hosts.copy" --op "put ./build.tar.gz /tmp/build.tar.gz" --dry-run
row files preview-local ./README.md --json
row snippet add --name uptime --command "uptime" --tag ops
row layout save triage --pane profile:lab-ssh --pane command:top --orientation horizontal
row layout run triage --dry-run
row broadcast --group prod --command "hostname" --timeout 10 --json
row keygen --out ~/.ssh/id_ed25519_row --comment row
row nettool ping example.com --dry-run
row sync push --to ~/RemoteOpsSync
row export --out backups/remote-ops-export.json
row import --in backups/remote-ops-export.json
row import --in confCons.xml --format mremoteng
row import --in ~/.local/share/remmina --format remmina
```

Profiller kayit, import, GUI duzenleme ve baslatma oncesinde ortak dogrulamadan gecer. Baslaticilar shell string birlestirme kullanmaz; komutlar argv listesi olarak uretilir ve `--dry-run` ile incelenebilir. Protokol secenekleri icin [`docs/PROTOCOLS.md`](docs/PROTOCOLS.md), import akislari icin [`docs/IMPORTERS.md`](docs/IMPORTERS.md), SFTP kuyruklari ve `--force` kurallari icin [`docs/FILE_TRANSFER.md`](docs/FILE_TRANSFER.md) dosyalarina bakin.

---

## GUI

PyQt6 masaustu kabugu su akislari saglar:

- oturum agaci ve hizli baglanti paneli;
- CLI ile ayni profil deposunu kullanan profil olusturma/duzenleme/silme diyaloglari;
- SSH/SFTP profilleri icin interaktif SFTP dosya panelleri ve transfer kuyrugu onizleme diyalogu;
- calisan surecler icin kapatma onayi ve temizleme yapan sekmeli calisma alani;
- stdout/stderr yakalama, stdin gonderme ve yonetilen Start/Stop durumuna sahip surec destekli terminal panelleri;
- yatay/dikey bolunmus panel kabuklari;
- Native, MobaXterm-style, SecureCRT-style, Termius-style, Remmina-style ve mRemoteNG-style gorunum presetleri;
- kayitli layout secici ve layout panellerini dogrudan acan olusturma/duzenleme/silme diyaloglari;
- `row plugins list` ile de gorulebilen Python entry-point protokol baslatma eklentileri.

```bash
pip install -e ".[desktop,security]"
row gui
```

---

## Web/PWA

`apps/web`, PWA olarak calisabilen statik bir tarayici calisma alanidir. Android/tarayici is akislari, dokumantasyon demoları ve ileride eklenebilecek API katmani icin kullanislidir.

```bash
row serve-web --host 127.0.0.1 --port 8765
```

`0.0.0.0`, `::` veya loopback olmayan baska bir adrese bind etmek icin `--allow-public-bind` gerekir. Bunu yalnizca guvenilir aglarda veya sertlestirilmis Docker giris noktasinda kullanin. Compose varsayilan olarak `127.0.0.1:8765` yayinlar.

---

## Ozellik Kapsami

Hedef, istenen araclar icin **%100 genel ozellik ailesi haritalamasi** saglamak ve bunu urun-hazirlik olgunlugundan ayri izlemektir.

Kapsam [`configs/feature_manifest.json`](configs/feature_manifest.json) dosyasindan uretilir. Haritalama, bir ozellik ailesinin built-in kod, harici adapter, istege bagli bagimlilik, CLI/GUI akisi, platform betigi veya eklenti noktasi ile temsil edilip edilmedigini gosterir. Product-ready skor ise adapter, optional, shell, script ve kismi is akislarini %100 hazir gibi gostermemek icin ayri agirliklar kullanir.

```bash
row features --coverage
row features --coverage --json
```

Tam manifest ve skor aciklamalari icin [`docs/FULL_FEATURE_COVERAGE.md`](docs/FULL_FEATURE_COVERAGE.md) dosyasina bakin.

---

## Platformlar

| Platform | Hedef mod | Not |
|---|---|---|
| Windows 10/11 | CLI, GUI, Web/PWA | x86, x64 ve ARM64 yayin hedefleri; OpenSSH, MSTSC, PuTTY, VcXsrv, TigerVNC adapterleri |
| Windows 8.1 | CLI/Web best effort, uzak hedef | Kaynak kurulum uyumlu Python stack ister; RDP/VNC/SSH/Telnet/seri/raw ile uzak yonetim |
| Windows 8/7 | Legacy kaynak, uzak hedef | Modern native runtime icin ayri legacy bagimlilik stack gerekir |
| Windows Vista/XP | Yalnizca uzak hedef | Harici istemcilerle baglanilir; modern Python/PyQt installer hedefi degildir |
| Windows Server 2012-2025 | CLI, GUI optional, Web/PWA | Operator jump host olarak uygundur |
| Linux | CLI, GUI, Web/PWA | i386, x86_64, armhf ve arm64 paket haritalari |
| Unix/BSD/Solaris | CLI, Web/PWA, Qt varsa GUI | POSIX shell ve OpenSSH onceliklidir |
| macOS Intel/Apple Silicon | CLI, GUI, Web/PWA | OpenSSH, XQuartz, Microsoft Remote Desktop/FreeRDP, VNC viewer |
| Android | Web/PWA, Termux CLI | ARMv7 ve ARM64 Termux/Web; APK gelecek isidir |
| Web | PWA shell | Statik PWA kabugu; API/backend sonradan eklenebilir |

Ayrintilar icin [`docs/PLATFORM_SUPPORT.md`](docs/PLATFORM_SUPPORT.md) dosyasina bakin.

---

## Guvenlik

- Gercek profilleri, parolalari, private key'leri, vault dosyalarini veya musteri host adlarini commit etmeyin.
- Tasınabilir/ozel operator verisi icin `ROW_HOME` kullanin.
- Yeni import edilen profilleri baslatmadan once `row connect NAME --dry-run` ile inceleyin.
- Vault sifreleme istege bagli `security` extra'sini gerektirir: `pip install -e ".[security]"`.
- Otomasyon icin `row vault set NAME --secret-env ENV` veya `row vault set NAME --stdin` kullanin; secret degerlerini argv'ye veya shell history'ye koymayin.
- `row vault get`, `--show` veya `--out` verilmeden secret yazdirmaz.
- `row vault status`, secret isimlerini veya degerlerini gostermeden yol, baslatilma durumu ve sayim bilgisi verir.
- `row keygen --passphrase-env`, yazilim key passphrase'ini `ssh-keygen` argv'sine koymadan in-process uretim yapar.
- Yikici SFTP islemleri ve overwrite riski olan transferler `--force` olmadan calistirilmaz.
- `row serve-web` varsayilan olarak loopback'e bind eder; loopback disi bind icin `--allow-public-bind` gerekir.
- SSHv1 profilleri yalnizca `ssh1`/`sshv1` protokolu ve `allow_insecure_sshv1=true` secenegi birlikte verildiginde baslatilabilir; protokol v1 yine de guvensizdir.
- Ayrintilar icin [`SECURITY.md`](SECURITY.md) ve [`docs/SECURITY_MODEL.md`](docs/SECURITY_MODEL.md) dosyalarina bakin.

---

## Gelistirme ve Yayin

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[desktop,security,dev]"
python scripts/verify.py
```

Bagimlilik kisitli inceleme ortamlarinda `pytest` yoksa `python scripts/verify.py --quick` kullanilabilir. Ayrintilar icin [`docs/VERIFYING.md`](docs/VERIFYING.md) dosyasina bakin.

Yayin akisi `v0.1.0` gibi tag'lerde wheel/sdist, kaynak zip, platform tar/zip paketleri, native Windows/macOS/Linux placeholder/manifest paketleri, release manifestleri ve `remote-ops-workspace-v0.1.0-SHA256SUMS.txt` uretir. CI checkout credential'lari final publish adimina kadar read-only kalir.

| Faz | Paketler | Durum |
|---|---|---|
| 1 | Python wheel/sdist ve zip/tar.gz hedef paketleri | Aktif |
| 2 | Windows `.exe`, `.msi` ve tasinabilir `.zip` | Aktif |
| 3 | macOS `.dmg` ve `.pkg` | Aktif |
| 4 | Linux `.deb`, `.rpm`, AppImage ve native tarball | Aktif |

Ayrintilar icin [`docs/RELEASE_STRATEGY.md`](docs/RELEASE_STRATEGY.md) dosyasina bakin.

---

## Lisans

MIT. Ayrintilar icin [`LICENSE`](LICENSE) dosyasina bakin.
