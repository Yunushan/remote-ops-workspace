<div align="center">

# Remote Ops Workspace

### SSH, RDP, VNC, SFTP, Mosh, Telnet, X11, SPICE, X2Go, ICA, HTTP/HTTPS, seri konsollar, raw socket'ler, bolunmus paneller, vault, snippet, sync, CLI, GUI ve Web/PWA icin operator odakli uzak erisim calisma alani.

![build](https://img.shields.io/badge/build-source--available-brightgreen)
![release](https://img.shields.io/badge/release-v1.0.1-blue)
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
git clone https://github.com/Yunushan/remote-ops-workspace.git
cd remote-ops-workspace

python -m venv .venv
# Linux/macOS/BSD/Solaris
. .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1

pip install -e ".[desktop,security]"
row init
row welcome
row profile add --name lab-ssh --protocol ssh --host ssh.example.invalid --username admin
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
row welcome
row profile add --name core-rdp --protocol rdp --host rdp.example.invalid --username administrator
row profile add --name switch-console --protocol serial --path /dev/ttyUSB0 --option baud=115200
row profile add --name jump-ssh --protocol ssh --host ssh.example.invalid --username admin --option proxy_jump=bastion --option keepalive_interval=30
row profile add --name lab-vnc --protocol vnc --host vnc.example.invalid --option fullscreen=true --option shared=true
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
row plugins validate
row plugins scaffold --out ./row-demo-plugin --name row-demo-plugin --module row_demo_plugin --protocol demo --client demo-client
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

Profiller kayit, import, GUI duzenleme ve baslatma oncesinde ortak dogrulamadan gecer. Baslaticilar shell string birlestirme kullanmaz; komutlar argv listesi olarak uretilir ve `--dry-run` ile incelenebilir. Protokol secenekleri icin [`docs/PROTOCOLS.md`](docs/PROTOCOLS.md), import akislari icin [`docs/IMPORTERS.md`](docs/IMPORTERS.md), SFTP kuyruklari ve `--force` kurallari icin [`docs/FILE_TRANSFER.md`](docs/FILE_TRANSFER.md), eklenti gelistirme icin [`docs/PLUGIN_DEVELOPMENT.md`](docs/PLUGIN_DEVELOPMENT.md) dosyalarina bakin.

---

## GUI

PyQt6 masaustu kabugu su akislari saglar:

- oturum agaci ve hizli baglanti paneli;
- CLI ile ayni profil deposunu kullanan profil olusturma/duzenleme/silme diyaloglari;
- SSH/SFTP profilleri icin interaktif SFTP dosya panelleri ve transfer kuyrugu onizleme diyalogu;
- calisan surecler icin kapatma onayi ve temizleme yapan sekmeli calisma alani;
- stdout/stderr yakalama, stdin gonderme ve yonetilen Start/Stop durumuna sahip surec destekli terminal panelleri;
- yatay/dikey bolunmus panel kabuklari;
- Native, MobaXterm-style, SecureCRT-style, Termius-style, Remmina-style ve mRemoteNG-style gorunum presetleri; statik preview uretimi ve canli PyQt6 render smoke kontrolu [`docs/GUI_DESIGN.md`](docs/GUI_DESIGN.md) icinde belgelenir;
- kayitli layout secici ve layout panellerini dogrudan acan olusturma/duzenleme/silme diyaloglari;
- `row plugins list` ve `row plugins validate` ile de gorulebilen/dogrulanabilen Python entry-point protokol baslatma eklentileri.

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

Hedef, istenen araclar icin **%100 genel ozellik ailesi haritalamasi**, **%100 adapter-ready coverage** ve **%100 release-backed product workflow parity** saglamaktir. Platform verified readiness verified default native ve mobile Web/PWA hedefleri icin ayri 100% scope kullanir; manual native ve legacy Windows hedefleri denominator disinda compatibility satirlari olarak izlenir.

Kapsam [`configs/feature_manifest.json`](configs/feature_manifest.json) dosyasindan uretilir. Haritalama, bir ozellik ailesinin built-in kod, harici adapter, istege bagli bagimlilik, CLI/GUI akisi, platform betigi veya eklenti noktasi ile temsil edilip edilmedigini gosterir. Adapter-ready skor, executable evidence ile dogrulanan implemented adapter, optional, CLI, GUI ve combined workflow satirlarini hazir sayar. `production_parity_coverage` JSON anahtari geriye uyumluluk icin kalir, ama acik sozlesme release-backed product workflow parity'dir: implemented workflow satirlari yalnizca executable release evidence ile sayilir, seam-only veya docs-only satirlar kismi kalir. Bu proprietary native clone iddiasi degildir. Platform verified readiness verified default native ve mobile Web/PWA hedefleri icin 100% scope kullanir; manual native ve legacy Windows hedefleri denominator disinda ayri compatibility satirlari olarak kalir. `scripts/check_feature_reality.py` ve `scripts/check_product_readiness.py` bu iddialari dogrular.

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
| Windows Vista/XP | Yalnizca uzak hedef | Windows XP x86/x64 uzak hedef kapsami 100.0%'dir; modern Python/PyQt installer hedefi degildir |
| Windows Server 2012-2025 | CLI, GUI optional, Web/PWA | Operator jump host olarak uygundur |
| Linux | CLI, GUI, Web/PWA | Varsayilan GitHub release is akisi x86_64/amd64 ve aarch64/arm64 native paketleri uretir; i386/i686 ve armhf haritalari eslesen builder ile betik desteklidir |
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
- SSHv1 profilleri yalnizca `ssh1`/`sshv1`, `allow_insecure_sshv1=true`,
  `legacy_target=windows-xp-32` veya `windows-xp-64` ve
  `allow_legacy_crypto=true` birlikte verildiginde baslatilabilir; protokol v1
  yine de guvensizdir.
- Zayif SSH algoritmalari ve RDP `security=rdp` modern profillerde kapali
  kalir; Windows XP x86/x64 uzak hedefleri icin sadece profil bazli legacy
  opt-in kullanilir.
- Protokol eklentilerini guvenilir yerel Python kodu gibi ele alin; eklenti destekli profilleri kullanmadan once `row plugins validate` ile yukleme hatalarini ve gecersiz ornek launch planlarini yakalayin.
- Ayrintilar icin [`SECURITY.md`](SECURITY.md) ve [`docs/SECURITY_MODEL.md`](docs/SECURITY_MODEL.md) dosyalarina bakin.

---

## Gelistirme ve Yayin

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[desktop,security,dev]"
python scripts/verify.py
```

Pull request ve push CI akisi Python/OS matrisi uzerinde
`python scripts/verify.py --lint` calistirir. Ayrica ayri bir Linux isi desktop
extra'yi kurup canli offscreen PyQt6 penceresi icin
`python scripts/check_real_gui_render.py --require-pyqt6` calistirir.
`python scripts/check_ci_workflow.py` bu kapilarin workflow'dan dusmesini
engeller.

Bagimlilik kisitli inceleme ortamlarinda `pytest` yoksa `python scripts/verify.py --quick` kullanilabilir. Ayrintilar icin [`docs/VERIFYING.md`](docs/VERIFYING.md) dosyasina bakin.

Repository cleanup before tagging:

```bash
python scripts/check_repository_cleanup.py
python scripts/check_repository_cleanup.py --require-clean
```

Yayin akisi `v1.0.1` gibi tag'lerde wheel/sdist, kaynak zip, platform tar/zip paketleri, Windows `x86`/`x64`/`arm64`, macOS `x64`/`arm64` ve Linux `x86_64`/`aarch64` native paketleri, release manifestleri ve `remote-ops-workspace-v1.0.1-SHA256SUMS.txt` uretir. Linux `i386`/`i686` ve `armhf` ciktisi eslesen builder ile betik desteklidir, fakat varsayilan GitHub release is akisinda yuklenmez. Makine tarafindan okunabilen yayin karari `configs/release_matrix.json` icindedir; `configs/platform_targets.json` ise `row platforms --json` tarafindan gosterilen daha genis platform katalogudur. Native installer smoke kapsami `configs/native_installer_smoke.json` icindedir ve `python scripts/check_native_installer_smoke.py` ile denetlenir; release workflow Windows, macOS ve Linux native islerinden sonra install, verify, upgrade and uninstall yollarini calistirir. Release workflow once `release-preflight` isinde `python scripts/verify.py --quick --no-cli-smoke` ve `python scripts/check_repository_cleanup.py --require-clean` calistirir; source, native ve publish isleri bu kapiya baglidir. Publish isi upload oncesinde `python scripts/check_release_publish_assets.py --assets-dir release-assets --tag` calistirip indirilen asset setini, checksum yan dosyalarini ve release manifestini `configs/release_matrix.json` ile karsilastirir. Python yayin araclari `requirements-release.txt` ile sabitlenir ve release manifestine `configs/release_toolchain.json` uzerinden yazilir. Native Windows, macOS ve Linux isleri kendi `native-SHA256SUMS.txt` yan dosyalarini da uretir. CI checkout credential'lari final publish adimina kadar read-only kalir.

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
