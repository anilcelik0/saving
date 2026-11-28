# Google Play · Uygulama içeriği beyanları (Bütçe Defteri · slug `saving`)

Play Console > uygulama > **Politika > Uygulama içeriği** altındaki formlar için hazır cevaplar.
Hesap tipi: **kişisel** → üretime çıkmadan önce kapalı test zorunlu (bkz. son bölüm).

| Alan | Değer |
|---|---|
| Uygulama adı (başlık, en fazla 30 karakter) | Bütçe Defteri: Harcama Takibi |
| Ana ekrandaki ad | Bütçe Defteri |
| Paket adı | `tr.com.appmanager.saving` (yayından sonra değiştirilemez) |
| Kategori | Finans |
| Gizlilik politikası URL'si | https://appmanager.com.tr/legal/saving/privacy/ |
| KVKK aydınlatma metni | https://appmanager.com.tr/legal/saving/kvkk/ |
| Hesap silme URL'si | https://appmanager.com.tr/account/delete/saving/ |

> Sayfaların açılması için sunucuda metinlerin yayınlanmış olması gerekir:
> `docker compose exec web python manage.py publish_legal_documents saving`

---

## 1. Gizlilik politikası
URL: `https://appmanager.com.tr/legal/saving/privacy/`

## 2. Uygulama erişimi (App access)
"Uygulamanın tamamı veya bir kısmı kısıtlı" → **Talimat ekle**:
- Ad: `İnceleme hesabı`
- Kullanıcı adı / şifre: sunucuda oluşturulan inceleme hesabı (ör. `seed_demo_data` ile `demo` kullanıcısı, şifreyi
  değiştirerek)
- Not: "Uygulama açılınca kullanıcı adı ve şifreyle giriş yapın. Hesapta örnek veriler vardır."

## 3. Reklamlar
**Hayır**, uygulamada reklam yok.

## 4. İçerik derecelendirmesi (IARC anketi)
- Kategori: **Diğer tüm uygulama türleri** (oyun, sosyal, haber değil)
- Şiddet, cinsellik, küfür, uyuşturucu, kumar: **Hayır**
- Kullanıcılar birbirleriyle etkileşim kurabiliyor / içerik paylaşabiliyor mu: **Hayır**
- Konum paylaşımı: **Hayır** · Dijital ürün satın alma: **Hayır**
- Beklenen sonuç: **3+ / Herkes**

## 5. Hedef kitle ve içerik
- Hedef yaş grubu: **18 ve üzeri** (finans uygulaması; gizlilik politikasıyla uyumlu)
- Uygulama çocukların ilgisini çekecek şekilde tasarlandı mı: **Hayır**

## 6. Finansal özellikler
Uygulama kredi, ödeme/para transferi, kripto, yatırım/aracılık veya sigorta hizmeti **sunmaz**; yalnızca kullanıcının
kendi girdiği gelir/gider ve birikim kayıtlarını takip eder (bütçe takibi). Formda bu hizmetlerin hiçbirini seçme;
"finansal özellik sunmuyor" seçeneğini (veya listede varsa kişisel bütçe/finans yönetimi seçeneğini) işaretle.

## 7. Diğer beyanlar
Haber uygulaması: **Hayır** · Sağlık uygulaması: **Hayır** · Devlet uygulaması: **Hayır** ·
Hassas izinler (konum, SMS, arama kaydı, tüm dosyalara erişim): **Kullanılmıyor** (yalnızca İnternet izni).

## 8. Veri güvenliği (Data safety)

### Genel sorular
| Soru | Cevap |
|---|---|
| Uygulama gerekli kullanıcı veri türlerini topluyor veya paylaşıyor mu? | **Evet** |
| Toplanan tüm veriler aktarım sırasında şifreleniyor mu? | **Evet** (HTTPS) |
| Kullanıcıların verilerinin silinmesini isteyebileceği bir yol sunuyor musunuz? | **Evet** (uygulama içi + web URL'si) |

### Veri türleri
Hiçbir veri üçüncü taraflarla **paylaşılmaz** (Cloudflare yalnızca bizim adımıza bağlantı hizmeti verir; Google'ın
tanımına göre "paylaşım" sayılmaz). Tüm satırlarda: **Toplanır · Paylaşılmaz · Geçici işlenmez**.

| Kategori > Veri türü | Zorunlu mu | Amaç |
|---|---|---|
| Kişisel bilgiler > **Ad** | İsteğe bağlı | Hesap yönetimi |
| Kişisel bilgiler > **E-posta adresi** | Zorunlu | Hesap yönetimi |
| Kişisel bilgiler > **Kullanıcı kimlikleri** (kullanıcı adı) | Zorunlu | Hesap yönetimi, Uygulama işlevselliği |
| Finansal bilgiler > **Satın alma geçmişi** (harcama kayıtları, ekstre satırları) | Zorunlu | Uygulama işlevselliği |
| Finansal bilgiler > **Diğer finansal bilgiler** (hesap bakiyeleri, gelir, yatırım/mevduat kayıtları) | Zorunlu | Uygulama işlevselliği |
| Dosyalar ve dokümanlar > **Dosyalar ve dokümanlar** (yüklenen ekstre: işlendikten sonra silinir; sorun bildirimine onayla eklenen ekstre/ekran görüntüsü: en geç 30 gün) | İsteğe bağlı | Uygulama işlevselliği |
| Uygulama etkinliği > **Diğer kullanıcı tarafından oluşturulan içerik** (sorun bildirimi mesajları) | İsteğe bağlı | Uygulama işlevselliği |
| Uygulama bilgileri ve performansı > **Diğer uygulama performans verileri** (yalnızca bildirimle: sürüm, cihaz türü, açık ekran, hata mesajı) | İsteğe bağlı | Uygulama işlevselliği |

**Toplanmayanlar:** konum, kişiler, fotoğraf/video (bildirime kullanıcı eklemedikçe), ses, takvim, SMS/arama,
sağlık, analiz/izleme, web geçmişi, cihaz/reklam kimliği, kilitlenme günlükleri.

## 9. Hesap silme
Play Console > Uygulama içeriği > **Veri güvenliği** formundaki silme sorularında ve "Hesap silme" bölümünde:
- Uygulama içi yol: **Diğer > Hesap > Hesabı sil** (şifre + onay)
- Web bağlantısı: **https://appmanager.com.tr/account/delete/saving/** (uygulamayı kurmadan, kullanıcı adı/e-posta +
  şifre ile)
- İşleyiş: talep → hesap kilitlenir, tüm oturumlar kapanır → **30 gün** içinde giriş yapılırsa iptal edilebilir →
  süre dolunca hesap ve tüm verileri (finansal kayıtlar, ekstre satırları, bildirimler ve ekleri, onay kayıtları)
  kalıcı olarak silinir. Kısmi veri silme sunulmaz (verilerin tamamı hesapla birlikte silinir).
- Hesabı dondurma (**Diğer > Hesap > Hesabı dondur**) silme değildir; veriler korunur, girişte yeniden açılır.

## 10. Kapalı test (kişisel hesap)
- Play Console > Test > **Kapalı test** kanalı oluştur, AAB yükle, test kullanıcılarını (Google hesabı e-postaları
  ya da bir Google Grubu) ekle ve katılım bağlantısını paylaş.
- En az **12 test kullanıcısı**, üretim başvurusundan önceki **14 gün boyunca kesintisiz** katılmış olmalı.
- 14 gün dolunca Kontrol paneli > **Üretim erişimi başvurusu** (test sürecine dair birkaç soru sorulur).

---

### Hukuki notlar (yayından önce kontrol edilmesi önerilir)
- Metinler (`backend/legal_texts/saving/*.md`) uygulamanın gerçek veri işleyişine göre hazırlandı; bir hukukçunun
  gözden geçirmesi önerilir.
- **Yurt dışına aktarım (KVKK md. 9):** trafik Cloudflare (ABD) altyapısından geçiyor; bunun hangi aktarım
  mekanizmasıyla yürütüleceği (ör. standart sözleşme ve Kurum'a bildirim) netleştirilmeli.
- **VERBİS:** gerçek kişi veri sorumluları belirli eşiklerin altında kayıt yükümlülüğünden muaf olabilir; durumun
  kontrol edilmesi önerilir.
- Release derlemesinde Inter fontu uygulamaya gömülmeli (`mobile/assets/fonts/Inter.ttf`); aksi halde font
  GitHub'dan indirilir ve kullanıcının IP adresi üçüncü tarafa gider.
