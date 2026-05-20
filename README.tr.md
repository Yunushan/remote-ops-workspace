<div align="center">

# Remote Ops Workspace

### SSH, RDP, VNC, SFTP, Mosh, Telnet, X11, SPICE, X2Go, ICA, HTTP/HTTPS, seri konsol, raw socket, bölünmüş terminal panelleri, kasa/vault, snippet, senkronizasyon, CLI, GUI ve Web/PWA için operatör odaklı uzak erişim çalışma alanı.

![build](https://img.shields.io/badge/build-ready-brightgreen)
![release](https://img.shields.io/badge/release-v0.1.0-blue)
![license](https://img.shields.io/badge/license-MIT-blue)
![runtime](https://img.shields.io/badge/runtime-Python%203.10--3.13-orange)
![interfaces](https://img.shields.io/badge/interfaces-CLI%20%7C%20GUI%20%7C%20Web-purple)
![targets](https://img.shields.io/badge/targets-Windows%20%7C%20Linux%20%7C%20macOS%20%7C%20BSD%20%7C%20Solaris%20%7C%20Android%20%7C%20Web-green)

[English](README.md) • Türkçe

</div>

---

## Proje özeti

**Remote Ops Workspace**, MobaXterm, Remmina, mRemoteNG, Terminator ve Termius araçlarında beklenen özellik ailelerini açık kaynak bir temelde birleştirmeyi hedefleyen, MIT lisanslı ve GitHub'a hazır bir uzak erişim çalışma alanıdır.

Depo; gerçek CLI, profil deposu, protokol başlatıcıları, isteğe bağlı şifreli vault, PyQt6 GUI kabuğu, Web/PWA kabuğu, özellik kapsam manifesti, testler, kurulum betikleri, CI ve yayın otomasyonu içerir.

> Bu proje Mobatek/MobaXterm, Remmina, mRemoteNG, GNOME Terminator veya Termius ile bağlantılı değildir. Ürün adları yalnızca uyumluluk hedeflerini açıklamak için kullanılmıştır.

## Hızlı başlangıç

```bash
git clone https://github.com/YOUR-ORG/remote-ops-workspace.git
cd remote-ops-workspace
python -m venv .venv
. .venv/bin/activate
pip install -e ".[desktop,security]"
row init
row profile add --name lab-ssh --protocol ssh --host 192.0.2.10 --username admin
row connect lab-ssh --dry-run
row doctor
```

Masaüstü arayüzü:

```bash
row gui
```

Web/PWA arayüzü:

```bash
row serve-web --host 127.0.0.1 --port 8765
```

## Desteklenen platformlar

Windows, Windows Server, Linux, Unix, BSD, Solaris/illumos, macOS, Android/Termux-PWA ve Web hedeflenmiştir. Ayrıntılar için `docs/PLATFORM_SUPPORT.md` dosyasına bakın.

## Lisans

MIT. Ayrıntılar için `LICENSE` dosyasına bakın.
