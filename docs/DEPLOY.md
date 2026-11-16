# Sunucu kurulumu (ev sunucusu · Windows 11 · Cloudflare Tunnel)

Yayın adresi: **https://appmanager.com.tr** (API: `/api/v1/`, yönetim: `/admin/`).
HTTPS'i Cloudflare sağlar; tünel `cloudflared` konteyneriyle `http://nginx:80`'e bağlanır. Sunucuda port açmaya,
sertifikaya veya modemde port yönlendirmeye gerek yoktur.

| Ortam | Compose dosyası | Mobil |
|---|---|---|
| Geliştirme (bu bilgisayar) | `docker-compose.yml` → http://localhost | `flet run` / `flet run --android` → localhost |
| Yayın (ev sunucusu) | `docker-compose.prod.yml` (aynı servisler + Cloudflare Tunnel) → https://appmanager.com.tr | `flet build apk/aab` → domain (otomatik) |

Sunucuda `.env`'deki `COMPOSE_FILE=docker-compose.prod.yml` satırı sayesinde komutlar iki ortamda da aynıdır
(`docker compose up -d`, `docker compose exec web ...`). Ortak servislerde bir değişiklik yapılırsa iki dosyaya da
uygulanır.

## 0. Mevcut sunucuyu iki dosyalı yapıya geçirme (bir kez)
**Önce `.env`'i düzenle, sonra çek** (aksi halde `docker compose` tünelsiz geliştirme dosyasını kullanır):
1. Sunucudaki `.env`: `COMPOSE_FILE=docker-compose.prod.yml` satırını ekle; `COMPOSE_PROFILES=tunnel` satırını sil
   (artık gerekmiyor). Sunucuda `GUNICORN_CMD_ARGS` içinde `--reload` varsa onu da kaldır.
2. ```powershell
   git pull
   docker compose up -d --build
   docker compose ps          # cloudflared dahil hepsi "running"
   ```
3. `https://appmanager.com.tr/admin/` açılıyorsa geçiş tamam.

---

## 1. Kod: GitHub private repo (yapıldı: `origin` = github.com/anilcelik0/saving)
Geliştirme bilgisayarında commit → `git push`; sunucu aynı depodan `git pull` yapar.
`.env`, `mobile/local_config.py`, `docs/extre_example/` git'e girmez; repoda gizli bilgi yoktur.

## 2. Sunucu bilgisayarı hazırlığı (bir kez)
- **Docker Desktop** (WSL 2) ve **Git for Windows** kur.
- Docker Desktop > Settings > General: **Start Docker Desktop when you sign in** açık.
- Elektrik kesintisi / güncelleme sonrası kendiliğinden kalkması için:
  - Güç ayarları: **Uyku = Hiçbir zaman**, ekran kapanabilir.
  - Otomatik oturum açma (Docker Desktop oturum açılınca başlar): `netplwiz` ile ya da Windows Hello ayarından.
  - BIOS'ta varsa **Restore on AC power loss = Power On**.
- Windows Update > Etkin saatler: gece dışında yeniden başlatmasın.

## 3. Projeyi sunucuya kur (bir kez)
```powershell
cd C:\srv            # istediğin klasör
git clone https://github.com/anilcelik0/saving.git app_manager
cd app_manager
Copy-Item .env.example .env
```
`.env` içinde **yayın değerleri** (diğerleri örnekteki gibi kalabilir):
```ini
DJANGO_SECRET_KEY=<uzun rastgele değer>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=appmanager.com.tr,localhost
DJANGO_CSRF_TRUSTED_ORIGINS=https://appmanager.com.tr
DJANGO_SECURE_COOKIES=True
POSTGRES_PASSWORD=<uzun rastgele değer>
GUNICORN_CMD_ARGS=--workers 3 --timeout 60
COMPOSE_FILE=docker-compose.prod.yml
CLOUDFLARE_TUNNEL_TOKEN=<Cloudflare'deki tünelin token'ı>
```
Rastgele değer üretmek için (PowerShell):
```powershell
-join ((48..57) + (65..90) + (97..122) | Get-Random -Count 60 | ForEach-Object { [char]$_ })
```
Başlat ve veritabanını hazırla:
```powershell
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py bootstrap
docker compose exec web python manage.py createsuperuser
```
`bootstrap`: istemci uygulamalarını kaydeder (`CLIENT_APPS`) ve gizlilik/KVKK metinlerini yayınlar
(`backend/legal_texts/<app>/`). Kaç kez çalıştırılırsa çalıştırılsın güvenlidir; metin değişmediyse yeni sürüm açmaz.
Fiyatlar günlük görevle gelir; hemen görmek için: `docker compose exec web python manage.py fetch_prices`.

## 4. Cloudflare ayarları (bir kez)
- Zero Trust > Networks > Tunnels > tünel > **Public hostname**: `appmanager.com.tr` → Service **HTTP**, URL `nginx:80`.
- SSL/TLS > Edge Certificates: **Always Use HTTPS** açık.
- Kontrol: tarayıcıda `https://appmanager.com.tr/admin/` giriş sayfası açılmalı.

## 5. Güncelleme (her yeni sürümde)
Geliştirme bilgisayarında commit + `git push`, sonra sunucuda:
```powershell
cd C:\srv\app_manager
git pull
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py bootstrap
```
Migration yoksa "No migrations to apply" der, zararı yoktur. Gizlilik/KVKK metni değiştiyse `bootstrap` yeni
sürümü yayınlar ve kullanıcılardan uygulamada yeniden onay istenir.

## 6. Yedek (önerilir)
Veritabanı yedeği (Görev Zamanlayıcı ile her gece çalıştırılabilir):
```powershell
cd C:\srv\app_manager
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/backup.dump'
docker compose cp db:/tmp/backup.dump "C:\srv\backup\app_manager_$(Get-Date -Format yyyyMMdd).dump"
```
(PowerShell'de `>` ile yönlendirme ikili dosyayı bozar; bu yüzden dosya konteynerde yazılıp kopyalanır.)
Geri yükleme:
```powershell
docker compose cp "C:\srv\backup\<dosya>.dump" db:/tmp/backup.dump
docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean /tmp/backup.dump'
```
Yedekleri ara sıra sunucu dışına (bulut/USB) kopyala.

## 7. Mobil
- **Geliştirme:** `cd mobile; .venv\Scripts\flet run` (masaüstü) veya `flet run --android` (telefonda Flet uygulaması,
  QR ile). Python bu bilgisayarda çalıştığı için local sunucuyu (`http://localhost`) kullanır.
- **Yayın:** `cd mobile; .venv\Scripts\flet build apk` (deneme) / `flet build aab` (Play Store). Paketlenmiş uygulama
  otomatik olarak `https://appmanager.com.tr/api/v1` kullanır (`mobile/config.py`).
