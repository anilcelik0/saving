# Proje Tanımı: "Sırala" — Veriye Dayalı Kart Sıralama Oyunu

> **Not (2026-11-21):** Bu, ilk taslak brief'tir. Kesin ad **Line Up** (slug `lineup`). `CLAUDE.md` ile çakışan her
> konuda `CLAUDE.md` geçerlidir (aynı repo, aynı DB, `ClientApp` + paylaşılan `accounts`, ev sunucusu + Cloudflare
> Tunnel). Alınan kararlar ve yol haritası: `PROGRESS_lineup.md`.

> **Bu doküman ne için?** Projenin amacını, alınmış kararları ve üç ana aşamayı tanımlar.
> Claude Code bu dokümanı okuyup **kesin, adım adım bir yol haritası** çıkarmak için kullanacak.
> Buradaki her şey bir kerede uygulanacak bir plan değil, yol haritasının girdisidir.
> "Çalışma adı: Sırala" — kesin isim henüz belli değil.

---

## 1. Proje Özeti

**Ne:** Android öncelikli, Türkçe bir mobil oyun. Oyuncu, ekrana gelen kartları bir niteliğe göre
(yıl, nüfus, yüzölçümü vb.) doğru sıraya dizer. Kartlar tek bir **kart havuzundan** gelir.
Her kartın birden fazla sayısal niteliği ve etiketi vardır.

**Neden tutabilir:**
- **Türkçe ve yerel içerik:** Türkiye illeri, Türk filmleri, Türkiye tarihi, müzik. Bu alanda iyi bir rakip yok.
- **Kategori karıştıran sorular:** "Hangisi önce oldu: Tarkan'ın Kuzu Kuzu'su mu, Galatasaray'ın UEFA Kupası mı?"
  Aynı niteliği taşıyan farklı kategorilerdeki kartlar karşılaştırılabilir.
- **Günlük ortak bulmaca ve paylaşım kartı (Wordle modeli):** Sonuç WhatsApp'ta paylaşılır, paylaşım reklam yerine geçer.
- **Davetli düello:** Arkadaşa link ile meydan okuma. Her meydan okuma yeni oyuncu getirebilir.

**Bölüm tasarımı yok:** İçerik tamamen veriden üretilir. Yeni içerik = havuza yeni kart.
Yeni mod = yeni bir üretici kural.

**Geliştirici profili:** Tek geliştirici. Python/Django güçlü, Dart/Flutter yeni öğreniliyor.
Kodun büyük kısmı Claude Code ile yazılacak. Geliştirici kodu okuyup anlayabilmeli, gerçek cihazda test edecek.

---

## 2. Alınmış Kararlar

### Teknoloji
| Katman | Seçim |
|---|---|
| Mobil istemci | **Flutter** (Dart), VS Code ile geliştirme |
| Backend | **Django** + Django REST Framework |
| Gerçek zamanlı | Django Channels + Redis (ileride canlı düello için) |
| Arka plan işleri | Celery + Celery Beat (Redis broker) |
| Veritabanı | PostgreSQL |
| Altyapı | Docker Compose (backend servisleri). Flutter, Docker dışında yerel makinede çalışır. |

**Flet değerlendirildi ve bırakıldı.** Sebep: Flet 1.1.2'de ödüllü reklam, abonelik/uygulama içi satın alma
ve uzaktan push (FCM) için resmi destek yok. Bunların her biri için Dart ile özel eklenti yazmak gerekiyordu.
Flutter'da üçü de olgun, resmi paketlerle hazır.

### Temel ilkeler (her aşamada geçerli)
1. **Sunucu otoriter:** Oyunun bütün kararlarını Django verir. İstemci sadece gösterir.
   Kartın değeri (yıl, nüfus...) **hamleden önce istemciye gönderilmez.** Hamle gönderilince sunucu doğruluğu
   kontrol eder ve değeri o zaman açıklar.
2. **Tohum (seed) tabanlı üretim:** Aynı tohum her zaman aynı kart dizisini üretir. Günlük bulmaca ve asenkron
   düello bu sayede kolaylaşır.
3. **Veriler kaynaktan gelir, uydurulmaz:** Hiçbir kart değeri bir dil modelinin hafızasından yazılmaz.
   Her değerin bir kaynağı (`source_url`) olmalı. Claude kart ve kategori *önerebilir*, değerler kaynaktan çekilir.
4. **Oyun mantığı saf Python:** Oyun motoru Django view'larından bağımsız, test edilebilir bir modül olur.
5. **Enerji sunucuda hesaplanır:** Cron yok, tembel hesaplama:
   `enerji = min(maks, kayıtlı + (şimdi − son_zaman) / dolum_süresi)`.

---

## 3. Oyun Tasarımı

### Kart havuzu
Örnek kartlar:
```
"İzmir"                     → nüfus, yüzölçümü, plaka, bölge=Ege          etiketler: [il, Ege]
"Kuzu Kuzu (Tarkan)"        → yıl=2001                                      etiketler: [müzik, pop, 2000'ler]
"Galatasaray UEFA Kupası"   → yıl=2000                                      etiketler: [futbol, Galatasaray]
```
Her kartın bir **tanınırlık puanı** (0–100) vardır. Kolay modlarda tanınırlığı yüksek kartlar gelir.
Kimsenin bilmediği kartlar oyunu öldürür.

### Oyun modları

**1. Zaman Çizgisi**
- Masada tek bir kartla başlanır. Her yeni kart, çizgideki doğru boşluğa sürüklenir.
- **Çizgi en fazla 10 kart.** 10 kart doğru yerleştirilince tur kazanılır.
- 3 can (hata hakkı).
- Arayüz: **dikey çizgi.** Yerleşmiş kartlar kompakt şerit (yıl + başlık), yeni kart altta büyük.
- Uzun çizgide sürükleme sırasında otomatik kaydırma gerekir. Yedek etkileşim: boşluklara dokunarak yerleştirme.

**2. Seri Modu**
- Açık bir kart var. Sıradaki kart daha büyük mü, daha küçük mü? Oyuncu yukarı/aşağı sürükleyerek tahmin eder.
- Her doğru tahmin seriyi uzatır. Rekor = seri uzunluğu.
- Can sayısı yol haritasında netleşecek (öneri: 1 can + reklamla 1 devam).

**3. Sıralı Mod (Günlük Bulmaca)**
- Herkese her gün aynı 5–6 kart gelir. Oyuncu bunları doğru sıraya dizer.
- 3 deneme. Her denemeden sonra doğru yerdeki kartlar yeşil gösterilir.
- Sonunda **paylaşılabilir sonuç kartı** üretilir (örnek: `🟩🟩🟨🟩🟥 – 2. deneme`).
- **Her zaman ücretsizdir**, enerji harcamaz.

### Zorluk ayarı
Mod üreticileri şu parametrelerle zorluk ayarlar:
- Kart değerleri arasındaki minimum fark (1950 ile 2010 kolay, 1998 ile 2000 zor)
- Tanınırlık eşiği
- Kategori karışımı (tek kategori veya karışık)

### Multiplayer: sadece davetle
- Rastgele eşleştirme **yok.** Arkadaşa link veya kod ile davet edilir.
- **Aşama A, asenkron meydan okuma (ilk yapılacak):** Aynı tohum, farklı zamanlarda oynanır, skorlar karşılaştırılır.
  Sadece REST yeterli. Davet linki uygulamayı doğrudan açmalı (deep link / App Links).
  Davet edilene push bildirimi gider.
- **Aşama B, canlı yarış (sonra):** İki oyuncu aynı kartları aynı anda oynar, rakibin ilerlemesi canlı görünür.
  Django Channels gerekir.
- Kitle oluşana kadar oyun tek oyunculu modlarla da tam çalışmalı.

---

## 4. Aşama 1: Veri Toplama

### Amaç
Oyunun ilk sürümü için doğrulanmış, tanınırlık puanı olan, Türkçe isimli bir kart havuzu oluşturmak.

### Kaynaklar
| Kaynak | Kullanım | Not |
|---|---|---|
| **Wikidata** (SPARQL) | Ana kaynak: iller, filmler, kişiler, olaylar, albümler | **CC0**, ticari kullanım serbest |
| Wikidata `wikibase:sitelinks` | Tanınırlık puanı (kaç dilde Wikipedia sayfası var) | İsteğe bağlı: Wikipedia sayfa görüntülenme sayıları |
| TÜİK | Türkiye'ye özel resmi istatistikler (il nüfusu vb.) | Wikidata değerleriyle çapraz kontrol |
| Elle seçilen içerik | Kültürel kategoriler (Yeşilçam, nostalji vb.) | Wikidata üzerine ince katman |

**Kısıtlar:**
- **Futbol ikinci aşamaya kalır.** Transfermarkt kullanım şartları veri kazımayı yasaklıyor.
  Açık futbol veri setlerinin lisansı tek tek kontrol edilmeli. Kulüp logoları kullanılmaz.
- **Görseller ilk sürümde yok.** Wikimedia Commons lisansları değişken (bazıları atıf zorunlu).
  İkon, bayrak veya emoji kullanılır.
- Türkçe etiket yoksa İngilizceye düşülür. Bu kartlar admin onayında işaretlenir.

### Veri modeli (taslak)
```
Card          → title, title_lang, popularity (0-100), source_url, fetched_at, status (staging/approved/rejected)
Tag           → name, parent (hiyerarşik: Futbol > Galatasaray)
CardTag       → card, tag
Attribute     → key (year, population, area...), unit, value_type (sayı/tarih), compare_label ("daha eski", "daha kalabalık")
CardAttribute → card, attribute, value, source_url
CardReport    → card, user, reason, created_at   ("hata bildir" butonu)
```

### Veri akışı
```
manage.py fetch_wikidata --category <kategori>
   → staging tablosu
   → otomatik doğrulama: eksik değer, aykırı değer, mükerrer kayıt, Türkçe isim yok, tanınırlık çok düşük
   → Django admin'de onay / ret
   → yayındaki kart havuzu
```
- Her kategori için ayrı ve tekrar çalıştırılabilir (idempotent) bir komut olur.
- Celery Beat ile ayda bir yenileme. Değişen değerler tekrar onaya düşer.
- Oyuncuların hata bildirimleri admin'de bir kuyrukta toplanır.

### İlk sürüm kategorileri (öneri)
1. Türkiye illeri: nüfus, yüzölçümü, plaka. En kolay kategori, ilk test için.
2. Türk filmleri ve dizileri: yayın yılı
3. Türkiye ve dünya tarihinden olaylar: yıl
4. Türk müziği (albüm/şarkı): çıkış yılı

### Aşama 1 çıktısı
- Çalışan veri çekme komutları ve doğrulama hattı
- Her kategoride yeterli sayıda onaylı kart (hedef sayı yol haritasında belirlenecek)
- Kategori ve nitelik bazında kart dağılımını gösteren basit bir rapor

---

## 5. Aşama 2: Backend ve Frontend

### Repo yapısı (öneri: monorepo)
```
/backend          Django projesi
/mobile           Flutter projesi
/data             SPARQL sorguları, ham veri örnekleri
/docs             Bu doküman, mimari notlar, kararlar
docker-compose.yml
CLAUDE.md
```

### Backend (Django)
**Docker Compose servisleri:** `web` (Daphne/Uvicorn), `db` (Postgres), `redis`, `celery-worker`, `celery-beat`.
Üretimde bunlara `nginx` eklenir.

**Django app'leri (öneri):**
| App | Sorumluluk |
|---|---|
| `cards` | Kart havuzu, etiketler, nitelikler, veri çekme komutları |
| `engine` | Saf Python oyun motoru: tohumdan deste üretimi, mod üreticileri, hamle doğrulama |
| `games` | Oyun oturumları (run), hamleler, skorlar, günlük bulmaca |
| `accounts` | Kullanıcılar, kimlik doğrulama (misafir hesap → sonradan kayıt) |
| `energy` | Enerji ve can hesapları, reklam ödülü (SSV) uç noktası |
| `social` | Davetler, meydan okumalar, arkadaşlar |
| `notifications` | Cihaz token'ları, FCM gönderimi (Celery) |
| `billing` | Abonelik durumu, mağaza/RevenueCat webhook'ları |

**Oyun motoru taslağı:**
```python
generate_deck(mode, seed, params) -> list[Card]
start_run(user, mode, seed=None) -> RunState      # değerler gizli
apply_move(run, move) -> MoveResult                # doğru/yanlış + açılan değer
legal_moves(run) -> list[Move]
```
Her mod (Zaman Çizgisi, Seri, Sıralı) ayrı bir **üretici sınıf** olur. Zorluk parametreleri bu sınıflarda tutulur.
Motor bolca birim testiyle korunur.

**Kimlik doğrulama:** İlk açılışta otomatik misafir hesap oluşturulur. İlerleme kaybolmasın diye sonradan
Google ile giriş yapılarak hesap bağlanabilir. Kesin yöntem yol haritasında belirlenecek.

### Frontend (Flutter)
**Temel paketler (öneri):** `flutter_riverpod` (durum yönetimi), `go_router` (yönlendirme), `dio` (API istemcisi).

**Ekranlar:**
- Açılış / misafir giriş
- Ana menü: mod seçimi, enerji göstergesi, günlük bulmaca durumu
- Zaman Çizgisi oyun ekranı (dikey çizgi, sürükle-bırak)
- Seri oyun ekranı
- Sıralı mod ekranı + sonuç ve paylaşım kartı
- Meydan okuma: oluştur, link paylaş, gelen meydan okumalar, sonuç karşılaştırma
- Profil ve istatistikler (seriler, rekorlar)
- Pro / ödeme ekranı
- Ayarlar (bildirimler, hesap bağlama, gizlilik)

**Etkileşim notları:**
- Sürükle-bırak: `Draggable` / `DragTarget` veya `ReorderableListView`.
  Akıcılık ilk prototipte **gerçek cihazda** test edilmeli.
- Kart açılma animasyonları ve doğru/yanlış geri bildirimi (renk, titreşim) oyun hissi için kritik.
- Paylaşım kartı, sistem paylaşım menüsü (`share_plus`) ile metin olarak paylaşılır.

### Aşama 2 çıktısı
- Üç mod tek oyunculu olarak uçtan uca oynanabilir
- Günlük bulmaca ve paylaşım çalışıyor
- Asenkron meydan okuma (link ile) çalışıyor
- Backend testleri ve temel Flutter widget testleri yazılmış

---

## 6. Aşama 3: Dağıtım ve Para Kazanma

### Gelir modeli
**Oyun içi can (bir tur boyunca):**
- Zaman Çizgisi'nde 3 can. Canlar bitince "reklam izle, devam et" teklifi çıkar. **Tur başına en fazla bir kez.**
- Pro üyeler reklamsız devam eder.

**Enerji (kaç tur oynanabileceği):**
- Öneri: en fazla 5 enerji, her 20–30 dakikada 1 dolar. Kesin değerler test edilip ayarlanacak.
- Enerji bitince: "ödüllü reklamla +1" veya "Pro ile sınırsız".
- **İlk günler cömert:** Yeni oyuncuya enerji sınırı uygulanmayabilir.

**Her zaman ücretsiz olanlar (büyüme döngüsü kilitlenmez):**
- Günlük Sıralı bulmaca
- Gelen bir meydan okumayı kabul etmek

**Pro abonelik:**
- Sınırsız enerji, reklamsız deneyim, ücretsiz devam hakkı, geçmiş günlük bulmaca arşivi
- Aylık ve yıllık plan. Türkiye için düşük fiyat ve mağazanın bölgesel fiyatlandırması.

**Reklam kuralları:**
- Ana format **ödüllü reklam.** Her kayıptan sonra zorunlu geçiş reklamı yok.
- Günlük reklam sayısına bir üst sınır.

### Teknik uygulama
| İhtiyaç | Çözüm |
|---|---|
| Ödüllü reklam | `google_mobile_ads` (AdMob) RewardedAd |
| Ödül doğrulama | AdMob **sunucu tarafı doğrulama (SSV)** → Django uç noktası. Enerji sadece SSV doğrulanınca verilir, istemcinin "ödül kazandım" mesajına güvenilmez. |
| Reklam onayı (GDPR) | Google UMP (AB kullanıcıları için) |
| Abonelik | **RevenueCat** (`purchases_flutter`) önerilir. Alternatif: `in_app_purchase` |
| Abonelik doğrulama | RevenueCat webhook'ları → Django. Alternatif: Play Developer API `subscriptionsv2` + RTDN (Pub/Sub). Satın alma **3 gün içinde onaylanmazsa (acknowledge) Google otomatik iade eder.** |
| Billing Library | **PBL 8 veya üzeri zorunlu.** Yeni projede PBL 9 kullanan paket sürümleri hedeflenmeli. |
| Uzaktan push | `firebase_messaging` (FCM) → Django'dan `firebase-admin` / `fcm-django`, Celery task'ı ile |
| Yerel bildirim | `flutter_local_notifications`: "enerji doldu", "günlük bulmaca hazır" (sunucu gerekmez) |

**Bildirim dağılımı:**
- Yerel: enerji doldu, günlük bulmaca hazır
- Uzaktan (FCM): meydan okuma geldi, meydan okuma sonucu

### Backend dağıtımı
- VPS + Docker Compose + nginx + TLS (Let's Encrypt)
- Postgres otomatik yedekleri
- Ortam değişkenleri ve gizli anahtarların yönetimi (API anahtarları, service account dosyaları repoya girmez)
- Hata takibi (Sentry) ve temel loglama
- Basit CI: testler + lint

### Google Play yayını
- İmzalı AAB (`flutter build appbundle`)
- Gizlilik politikası sayfası, Play "Veri güvenliği" formu, içerik derecelendirmesi
- **Yeni kişisel geliştirici hesapları için kapalı test zorunluluğu** var (bilinen şart: 12 testçi, 14 gün;
  güncel şart Play Console'dan kontrol edilmeli). Testçi listesi erkenden hazırlanmalı.
- Önce internal testing kanalında: test reklamları, test aboneliği, push akışı

### Ölçülecek metrikler
- D1 / D7 / D30 elde tutma (retention)
- Günlük bulmaca tamamlama ve paylaşım oranı
- Meydan okuma gönderme ve kabul oranı (davetle gelen oyuncu sayısı)
- Reklam izleme oranı, Pro'ya geçiş oranı

---

## 7. Riskler ve Açık Sorular

**Riskler:**
1. **Veri kalitesi:** Yanlış bir yıl ya da nüfus değeri oyuncuyu kızdırır. Doğrulama hattı ve hata bildirimi kritik.
2. **Tanınırlık:** Havuz bilinmeyen kartlarla dolarsa oyun sıkıcı olur.
3. **Dart öğrenme eğrisi:** Geliştirici Flutter'da yeni. Önce basit bir uygulamanın Flet'ten Flutter'a çevrilmesi
   öğrenme egzersizi olarak planlanabilir.
4. **Gelir altyapısı:** Ödüllü reklam, SSV, abonelik ve push, oyun mekaniklerinden **önce** küçük bir test uygulamasında
   kanıtlanmalı.
5. **Tek geliştirici kapasitesi:** Kapsam küçük tutulmalı. Her aşamanın sonunda oynanabilir bir şey olmalı.

**Yol haritasında netleşmesi gereken açık sorular:**
- Oyunun kesin adı
- Seri modunda can sayısı ve devam kuralı
- Enerji değerleri (maksimum, dolum süresi) ve Pro fiyatı
- Kimlik doğrulama yöntemi (misafir + Google ile giriş?)
- İlk sürüm için kategori başına hedef kart sayısı
- RevenueCat mi, `in_app_purchase` mı?
- Backend barındırma sağlayıcısı
- iOS ne zaman? (Şimdilik sadece Android)

---

## 8. Claude Code'dan Beklenen

1. Bu dokümanı ve repo durumunu incele.
2. Önce **açık soruları ve gördüğün riskleri** listele, karar gerektirenleri sor.
3. Üç aşamayı **kilometre taşlarına** ve **küçük, tek oturumda bitebilecek görevlere** böl. Her görev için:
   - Net tanım ve kabul kriterleri
   - Bağımlılıklar (hangi görevden sonra gelir)
   - Kabaca zorluk (küçük / orta / büyük)
4. **Aşama 0'ı** (kurulum + gelir altyapısını test uygulamasında kanıtlama) yol haritasının başına koy.
5. Yol haritası onaylanmadan büyük kod yazmaya başlama.
6. Onaylanan yol haritasını `docs/ROADMAP.md` olarak kaydet. Kalıcı proje kurallarını ve komutlarını `CLAUDE.md`'ye yaz.
7. Kod yazarken kart değeri uydurma. Değerler her zaman veri çekme hattından gelir.
