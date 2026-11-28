# Akış Şeması

Sistemin uçtan uca akışı. Her faz tamamlandığında bu dosya güncellenir.
Kesikli çizgili / gri kutular henüz yapılmamış (planlanan) kısımlardır.

**Son güncelleme:** Ekstre okuyucu doğruluk çalışması (özet okuyucu, ek kontroller, olası yorumların denenmesi, satır notları, okuma kalitesi, örnek seti) — 2026-11-28

---

## 1. Genel mimari

```mermaid
flowchart LR
    subgraph Mobil["Android (Flet)"]
        UI[Ekranlar<br/>Özet · Hareketler · Yatırımlar · Diğer]
        API[ApiClient<br/>JWT + otomatik yenileme]
        UI --> API
    end

    subgraph Sunucu["Docker Compose (tek sunucu)"]
        NGINX[Nginx :80]
        WEB[Gunicorn + Django<br/>/api/v1]
        DB[(PostgreSQL)]
        REDIS[(Redis)]
        BEAT[Celery Beat<br/>zamanlayıcı]
        WORKER[Celery Worker]

        NGINX --> WEB
        WEB --> DB
        WEB --> REDIS
        BEAT -->|görev kuyruğa| REDIS
        REDIS --> WORKER
        WORKER --> DB
    end

    API -->|HTTPS/JSON| NGINX

    subgraph Apps["Django uygulamaları"]
        ACC[accounts<br/>ortak: ClientApp, User, JWT]
        BUD[saving_budget<br/>hesap, kategori, işlem, seri, özet, ekstre]
        INV[saving_invest<br/>varlık fiyatları, alış/azaltma, vadeli mevduat, portföy]
        REP[saving_reports<br/>salt okunur raporlar]
    end
    WEB --- Apps
    INV -->|isteğe bağlı gider/gelir kaydı| BUD
    REP -->|okur| BUD
    REP -->|okur| INV
    WORKER -->|17:00 fiyat çek| EXT[TCMB today.xml<br/>Altınkaynak Gold]

    classDef todo fill:#eee,stroke:#999,stroke-dasharray:4 3,color:#777
```

---

## 2. Kimlik doğrulama ve oturum

```mermaid
sequenceDiagram
    participant M as Mobil
    participant A as auth API
    participant B as saving API

    M->>A: register / login (app=saving, kullanıcı adı|e-posta, şifre)
    A-->>M: access (30 dk) + refresh (90 gün), token içinde app=saving
    Note over M: Token'lar cihazda saklanır,<br/>açılışta varsa direkt ana ekran

    M->>B: istek + Bearer access
    B->>B: token geçerli mi? app claim = kullanıcının uygulaması mı?
    B-->>M: 200 veri

    M->>B: istek (access süresi dolmuş)
    B-->>M: 401 token_not_valid
    M->>A: refresh (aynı anda tek istek)
    A->>A: kullanıcı/uygulama aktif mi?<br/>eski refresh kara listeye
    A-->>M: yeni access + yeni refresh (süre 90 gün yeniden başlar)
    M->>B: isteği tekrarla
    B-->>M: 200 veri

    Note over M,A: Refresh de başarısızsa → giriş ekranı<br/>"Oturumunuzun süresi doldu"
```

---

## 3. Yeni kayıt oluşturma (tek form)

```mermaid
flowchart TD
    START([+ Yeni kayıt]) --> HESAP{Hesap var mı?}
    HESAP -- Hayır --> UYARI[Önce Diğer > Hesaplar'dan hesap ekle]
    HESAP -- Evet --> FORM[Tür · Tekrar · Tutar · Tarih · Açıklama<br/>Kategori · Hesap · Otomatik öde]
    FORM --> TEKRAR{Tekrar?}

    TEKRAR -- Tek seferlik --> TARIH{Tarih ≤ bugün?}
    TARIH -- Evet --> PAID1[1 kayıt: ÖDENDİ]
    TARIH -- Hayır --> PEND1[1 kayıt: BEKLİYOR]

    TEKRAR -- Taksitli --> SPLIT[Toplam ÷ taksit sayısı<br/>kuruş farkı son taksite]
    SPLIT --> SERI1[Seri + N kayıt: BEKLİYOR<br/>her biri kendi vadesinde]

    TEKRAR -- Düzenli --> SERI2[Seri + 12 aylık kayıt: BEKLİYOR<br/>bitiş tarihi varsa ona kadar]

    SERI1 --> AUTO{Otomatik öde ve<br/>vade ≤ bugün?}
    SERI2 --> AUTO
    AUTO -- Evet --> PAID2[O kayıtlar: ÖDENDİ]
    AUTO -- Hayır --> BEKLE[Bekleyen listesinde kalır]
```

---

## 4. Bir kaydın yaşam döngüsü

```mermaid
stateDiagram-v2
    [*] --> Bekliyor: ileri tarihli / seri kaydı
    [*] --> Odendi: tarih ≤ bugün (tek seferlik)

    Bekliyor --> Gecikti: vade geçti, ödenmedi
    Gecikti --> Odendi: Öde (tutar değiştirilebilir)
    Bekliyor --> Odendi: Öde (manuel)
    Bekliyor --> Odendi: Gece 00:30 (otomatik öde)
    Odendi --> Bekliyor: Ödenmedi olarak geri al

    Bekliyor --> [*]: Sil (sadece bu / bu ve sonrakiler)
    Odendi --> [*]: Sil

    Odendi: Ödendi (bakiyeyi etkiler)
    Bekliyor: Bekliyor (tahmini bakiyeye girer)
    Gecikti: Gecikti (kırmızı, kendi ayında kalır)
```

**Seri kaydını düzenleme/silme kapsamı**
- *Sadece bu kayıt:* yalnızca o tarihteki kayıt değişir.
- *Bu ve sonraki bekleyenler:* tutar/açıklama/kategori/hesap/otomatik öde sonraki bekleyen kayıtlara ve serinin şablonuna uygulanır (ör. kira zammı). Silmede seri durur, ödenmiş geçmiş korunur.

---

## 5. Gece görevleri (Celery Beat)

```mermaid
flowchart TD
    subgraph G1["00:30 · daily_budget_maintenance"]
        A1[Vadesi gelmiş + otomatik öde + BEKLİYOR<br/>kayıtları ÖDENDİ yap<br/>kaçırılan günler dahil] --> A2{Süresiz düzenli seride<br/>hazır kayıt < 60 gün mü?}
        A2 -- Evet --> A3[+12 aylık yeni BEKLİYOR kayıt üret]
        A2 -- Hayır --> A4[Bir şey yapma]
    end
    subgraph G2["04:00 · flush_expired_tokens"]
        B1[Süresi dolmuş refresh token<br/>kayıtlarını temizle]
    end
    subgraph G3["İstek üzerine"]
        C2[parse_statement_task<br/>ekstre yüklenince çalışır]
    end
    subgraph G4["17:00 · fetch_daily_prices"]
        C1[Katalogdaki varlıkları senkronla] --> C3[TCMB: USD, EUR<br/>Altınkaynak: gram/çeyrek/yarım/tam altın, gram gümüş]
        C3 --> C4[Varlık başına günde 1 fiyat satırı<br/>alış + satış]
        C3 -- kaynak hata verirse --> C5[30 dk arayla 3 kez yeniden dene]
    end
    classDef todo fill:#eee,stroke:#999,stroke-dasharray:4 3,color:#777
```

---

## 6. Bakiye ve Özet hesabı

```mermaid
flowchart LR
    T[(İşlemler)] --> P[ÖDENDİ olanlar]
    T --> W[BEKLİYOR olanlar]
    T --> X[İPTAL olanlar<br/>iade / atlanan<br/>hiçbir toplama girmez]

    P --> BAL["Hesap bakiyesi =<br/>açılış bakiyesi + ödenen gelir − ödenen gider<br/>(bakiyeden düşülmesin işaretli ekstreler hariç)"]
    BAL --> NOW[Şu anki bakiye<br/>= tüm hesapların toplamı]

    T --> MONTH["Seçili ay — her hesap kendi içinde, sonra toplanır<br/>Kart dışı kayıtlar: takvim ayı<br/>Kart kayıtları: hesabın ekstre döngüsü<br/>(kesim 15 → 16 Ocak–15 Şubat = Şubat)<br/>ekstreden gelenler: bankanın koyduğu ekstreye göre<br/>Gelir: alınan + bekleyen · Gider: ödenen + bekleyen<br/>Ay net = gelir − gider"]

    NOW --> PROJ["Ay sonu tahmini =<br/>şu anki bakiye + ay sonuna kadarki<br/>bekleyen gelir − bekleyen gider<br/>(gecikenler dahil)"]
    W --> PROJ
    W --> OVR[Geciken toplamları<br/>tarih < bugün]
```

---

## 7. Mobil ekran akışı

```mermaid
flowchart TD
    OPEN([Uygulama açılır]) --> TOK{Kayıtlı oturum var mı?}
    TOK -- Evet --> ME[auth/me] --> HOME
    TOK -- Hayır --> LOGIN[Giriş]
    LOGIN --> REG[Kayıt ol] --> HOME
    LOGIN --> HOME

    HOME[Ana ekran<br/>alt menü + ortada + butonu<br/>açık/koyu tema telefona uyar] --> S[Özet<br/>bakiye + tahmin · gelir/gider<br/>harcama halkası · 6 ay çubuk<br/>net varlık çizgisi · yaklaşan ödemeler]
    HOME --> PLUS[+ menüsü<br/>gelir/gider · ekstre yükle<br/>altın/döviz · vadeli mevduat · hesap]
    PLUS --> NEW
    HOME --> H[Hareketler]
    HOME --> D[Diğer]

    H --> HM["Ay görünümü (en fazla +1 ay ileri)<br/>Özet ile aynı kapsam"]
    HM --> HT[Kart dışı hareketler tek tek<br/>bekleyenlerde Öde butonu]
    HM --> HC["Kart dönemi satırı (hesap bazlı)<br/>Enpara Kredi Kartı · Ekstre 15.02<br/>toplam · Ödendi / Ödenmedi / Kısmen"]
    HC --> CYC[Dönem detayı<br/>harcamalar · Tümünü ödendi / ödenmedi]
    NEW[Yeni kayıt formu<br/>tek seferlik / düzenli / taksitli<br/>kredi kartıyla]
    HT --> EDIT[Kayıt düzenle<br/>Ödendi / geri al · İptal et / geri al<br/>kapsam: sadece bu / sonrakiler]
    CYC --> EDIT

    D --> AUTO[Otomatik ödemelerim<br/>düzenli + taksitli planlar<br/>sıradaki ödeme üzerinden düzenle]
    AUTO --> EDIT
    D --> ACC[Hesaplar<br/>banka/nakit · açılış bakiyesi<br/>kart kesim günü · kart adı]
    D --> STM[Ekstreler<br/>yükle · önizle · aktar · sil]
    D --> CAT[Kategoriler]
    D --> RULE[Öğrenilen kategoriler]
    D --> RPT[Raporlar<br/>kategori dağılımı → kayıtlar<br/>aylık trend · net varlık · portföy geçmişi]
    D --> PRO[Profil]
    D --> OUT[Çıkış] --> LOGIN

    HOME --> INVS[Yatırımlar<br/>toplam değer · varlıklarım · mevduatlar · güncel fiyatlar]
    INVS --> AST[Varlık detayı<br/>elimdeki · ort. maliyet · son 30 gün<br/>Alış ekle · Azalt · işlem düzenle]
    INVS --> DEP[Mevduat detayı<br/>Düzenle · Yenile · Kapat · Yeniden aç]
    INVS --> DH[Geçmiş mevduatlar]
    classDef todo fill:#eee,stroke:#999,stroke-dasharray:4 3,color:#777
```

---

## 8. Ekstre aktarma

```mermaid
flowchart TD
    UP([Diğer > Ekstreler > Yükle<br/>hesap seç + PDF/Excel<br/>☐ bakiyeden düşülmesin]) --> V{Uzantı pdf/xlsx<br/>ve ≤ 10 MB?}
    V -- Hayır --> E400[400: Türkçe hata]
    V -- Evet --> SAVE[Dosya gizli klasöre<br/>/vol/private · nginx sunmaz]
    SAVE --> TASK[Celery: parse_statement_task]
    TASK --> ENG["Tek genel okuyucu (tüm bankalar)<br/>kelimeler + sayfadaki konumları → tarihle başlayan satırlar<br/>tutar sütunları hizalamadan bulunur, başlıktan adlandırılır<br/>(Tutar · Borç/Alacak · Bakiye · Taksit · Puan)<br/>sayı biçimi her sayıda ayrı: 1.234,56 / 1,234.56<br/>Excel: başlık satırı aynı kelimelerle bulunur"]
    ENG --> META[Banka + tür metinden tanınır<br/>kart: hesap kesim, dönem · hesap: tarih aralığı, bakiye]
    META --> SUM["Kart özeti okunur (banka kodu yok)<br/>'etiket : tutar' · ızgara / denklem (etiketler üstte, tutarlar altta)<br/>· tablodaki özet satırı<br/>kendi içinde tutan okumalar: önceki + harcama − ödeme = borç"]
    SUM --> DET["Tarihsiz satırlar üstteki işleme bağlanır<br/>metin: açıklama / 'N / M taksidi' · tutarlar: döküm<br/>(Anapara+Faiz+BSMV = işlem) ya da tarihi düşmüş satır adayı"]
    DET --> HYP["Olası yorumların hepsi denenir:<br/>alışveriş işareti × tarihsiz tutarlar × özet okumaları<br/>ekstrenin en iyi doğruladığı seçilir (eşitlikte en olası)"]
    HYP --> OK{Satır bulundu mu?}
    OK -- Hayır --> FAIL[Durum: Hata<br/>'Bu ekstreden hareket okunamadı' + Sorun bildir]
    OK -- Evet --> CHK{"Öz-denetim (her kontrol ayrı)<br/>kart: önceki + satırlar = dönem borcu,<br/>harcamalar, ödemeler (özette basılıysa)<br/>hesap: satır satır bakiye + kapanış bakiyesi"}
    CHK -- Tutuyor --> GOOD[Önizlemede ✓ doğrulandı<br/>dönem borcu, harcamalar, ödemeler]
    CHK -- Tutmuyor --> WARN["Önizlemede ⚠ fark X TL + kontrol listesi<br/>farkı açıklayan satırlar işaretli<br/>(aynı tutar / iki katı = yön ters / tarihsiz tutar)<br/>PDF ise Excel önerisi + 'bu ekstreyi bize bildirin'"]
    CHK -- Toplam yok --> UNK[Önizlemede 'kontrol edin' + Excel önerisi]
    GOOD --> RULES
    WARN --> RULES
    UNK --> RULES
    ENG --> DEL[Dosya silinir<br/>sadece satırlar kalır]
    CHK --> LOG[("Okuma kaydı (anonim)<br/>banka · tür · dosya türü · motor sürümü<br/>kontroller · işaretli satır sayısı")]

    subgraph RULES["Her satır için kurallar"]
        K1{Daha önce aktarıldı mı?<br/>banka ref no / hash /<br/>aynı tarih+tutar+tür} -- Evet --> SK1[Atla: mükerrer]
        K1 -- Hayır --> K2{Kart borcu ödemesi<br/>(hesapta ya da kart ekstresinde) /<br/>kendi hesabına virman /<br/>fon, vadeli, yatırım?}
        K2 -- Evet --> SK2[Atla önerisi<br/>işaretsiz gelir]
        K2 -- Hayır --> K3{Aynı hesap + tutar,<br/>±7 gün bekleyen kayıt?<br/>taksitte: ekstre dönemi}
        K3 -- Evet --> MT[Eşleştir önerisi]
        K3 -- Hayır --> IM[Yeni kayıt]
        IM --> CAT["Kategori önerisi (asla boş kalmaz)<br/>1 bilinen işyeri: Migros→Market, Uber Eats→Yeme-İçme<br/>2 amaç: kira bedeli/aidat→Kira, maaş→Maaş<br/>3 kanal: ATM→Nakit Çekim, FAST/EFT→Para Transferi,<br/>masraf/ücret→Banka Masrafı<br/>4 online: .com, iyzico, paytr→Online Alışveriş<br/>5 kart iadesi→İade<br/>6 yedek: Diğer Gider / Diğer Gelir"]
        MT --> CAT
    end

    RULES --> READY[Durum: Onay bekliyor]
    READY --> REVIEW["Önizleme: işaretle / kaldır<br/>satır notları: ⚠ kontrol edin · bilgi (taksit asıl tarihi)<br/>'yalnızca kontrol gereken satırlar' filtresi<br/>kategori değişince öğrenilir ve<br/>aynı işyerinin satırlarına uygulanır<br/>eşleştir / iade / yeni kayıt"]
    REVIEW --> CONF["Aktar<br/>☑ aktardıktan sonra ekstre bilgilerini sil"]
    CONF --> LOG2[("Okuma kaydına: önerilenden farklı<br/>dahil edilen/çıkarılan satır ve<br/>değiştirilen kategori sayısı")]
    CONF --> T1[Yeni kayıtlar: ÖDENDİ<br/>kaynak=ekstre · kartsa ekstre kesim tarihi]
    CONF --> T2[Eşleşen bekleyen kayıt: ÖDENDİ<br/>ekstre tarihi ve tutarıyla]
    CONF --> T3[İade: ilgili harcama İPTAL]
    T1 --> DONE[Durum: Aktarıldı<br/>ham ekstre metni temizlenir]
    T2 --> DONE
    T3 --> DONE
    DONE --> DEL{Silme seçili mi?}
    DEL -- Evet --> GONE[Ekstre kaydı + satırlar silinir<br/>harcamalar kalır]
    DEL -- Hayır --> KEEP[Ekstreler listesinde kalır<br/>istenirse sonradan silinir]
```

**Gizlilik**
- Ekstre dosyası okunduktan hemen sonra silinir; okunamamış dosyalar gece görevinde (1 saatten eski) silinir.
- Kart numarası ve kişisel bilgiler ekstreden okunmaz/saklanmaz. Kart adı sadece banka adından oluşur.
- Aynı ekstre tekrar yüklenirse (ekstre kaydı silinmiş olsa bile) aktarılan harcamaların anahtarlarıyla mükerrer yakalanır.

**Kart ekstresi kuralları**
- Önceki dönem bakiyesi, toplam ve "ödemeniz için teşekkürler" satırları hiç gelmez; harcamalar tek tek gelir.
- Hesap ekstresindeki "Kredi Kartı Borç Ödeme" satırı atlanır (çift sayım olmasın).
- Önceki dönemde başlamış taksit (ekstrede eski alışveriş tarihiyle görünür) → ekstre kesim tarihine yazılır
  (bilgi notu: asıl işlem tarihi). Taksit bilgisi alttaki satırdan da okunur ("… işlemin 20 / 40 taksidi").
- Taksit bilgisi olmayan ama dönemden 45 günden eski tarihli satır → kesim tarihine yazılır, ⚠ "tarihi kontrol edin".
- Kesim tarihinden sonraki tarih → ⚠ "dönemin dışında".
- İade (eksi tutar) → gelir.

**Okuyucuyu geliştirme (geliştirici)**
- Örnek seti: `backend/statement_samples/` (git'e ve Docker imajına girmez). Gerçek ekstre
  `make_statement_sample <dosya>` ile maskelenir (isim, adres, kart/IBAN/müşteri no, e-posta; konum, tutar ve
  tarih korunur) ve orijinal gibi okunduğu doğrulanır; asıl dosya sonra silinebilir.
- Her motor değişikliğinden sonra `check_statements`: tüm örnekleri okur, beklenen sonuçla farkları gösterir;
  farklar kontrol edilince `--accept`.
- Admin › Ekstre okuma kayıtları › **Okuma kalitesi**: banka / tür / dosya türü / motor sürümü bazında doğrulanma
  oranı, tutmayan ve okunamayan okumalar, işaretli satır oranı, kullanıcının değiştirdiği satır ve kategori oranı.

---

## 9. Yatırımlar (saving_invest)

```mermaid
flowchart TD
    subgraph Varlik["Altın / gümüş / döviz"]
        B[Alış<br/>miktar + birim fiyat<br/>fiyat: güncel satış fiyatı önerilir] --> BA{Hesap seçildi mi?}
        BA -- Evet --> BE[Hesaptan Yatırım gideri<br/>bakiye düşer]
        BA -- Hayır --> BP[Yalnızca portföy]
        R[Azaltma<br/>yalnızca miktar · satış kârı izlenmez] --> RA{TL tutarı + hesap?}
        RA -- Evet --> RI[Hesaba Yatırım geliri]
        RA -- Hayır --> RP[Yalnızca miktar düşer]
        G[Kontrol: hiçbir tarihte<br/>elde olan miktar eksiye düşemez<br/>ekle / düzenle / sil]
    end
    subgraph Mevduat["Vadeli mevduat"]
        O[Aç: anapara, yıllık faiz %, başlangıç, vade sonu<br/>vade sonu tutarı: kullanıcı girer<br/>boşsa basit faiz − %17,5 stopaj] --> OA[isteğe bağlı: anapara hesaptan düşer]
        O --> M{Vade doldu}
        M --> RN[Yenile<br/>yeni anapara = vade sonu tutarı<br/>yeni oran + vade]
        M --> CL[Kapat<br/>tutar isteğe bağlı hesaba gelir]
        CL --> RO[Yeniden aç<br/>kapanış kaydı silinir]
    end
    subgraph Portfoy["Portföy"]
        V[Varlık değeri = miktar × güncel ALIŞ fiyatı<br/>maliyet = ortalama maliyet × miktar<br/>fark ve %] --> TOT[Toplam yatırım değeri]
        DV[Aktif mevduat bugünkü değeri<br/>faiz vade boyunca gün gün işler] --> TOT
    end
```

---

## 10. Raporlar (saving_reports)

```mermaid
flowchart TD
    P["Dönem: bitiş ayı + tek ay / son 3 / 6 / 12 ay<br/>ay kapsamı Özet ile aynı<br/>(kart: ekstre dönemi · iptaller sayılmaz)"]
    P --> C["Kategori dağılımı<br/>gider veya gelir · tutar, %, kayıt sayısı<br/>önceki eşit döneme göre fark"]
    C --> CT[Kategoriye dokun → o dönemin kayıtları]
    P --> T["Aylık trend (6/12/24 ay)<br/>gelir, gider, net<br/>birikim = (gelir − yatırımdan gelen) − (gider − yatırıma giden)<br/>birikim oranı · ortalamalar (kaydı olan aylar)"]
    W["Ay sonu anlık görüntüleri (bu ay: bugün)"] --> N["Net varlık = hesap bakiyeleri<br/>(o güne kadar ödenmiş hareketler)<br/>+ yatırımlar"]
    W --> PF["Portföy geçmişi<br/>altın/döviz: o günkü son alış fiyatı<br/>fiyat yoksa maliyet (*)<br/>mevduat: işleyen faiz · maliyete göre fark"]
```

---

## 11. Planlanan fazlar (henüz yok)

```mermaid
flowchart LR
    F5["5 · Mobil son<br/>güvenli token, APK, tasarım"]:::todo
    F5
    classDef todo fill:#eee,stroke:#999,stroke-dasharray:4 3,color:#777
```
