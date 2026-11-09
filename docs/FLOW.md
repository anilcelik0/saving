# Akış Şeması

Sistemin uçtan uca akışı. Her faz tamamlandığında bu dosya güncellenir.
Kesikli çizgili / gri kutular henüz yapılmamış (planlanan) kısımlardır.

**Son güncelleme:** Faz 2b (ekstre aktarma) — 2026-11-09

---

## 1. Genel mimari

```mermaid
flowchart LR
    subgraph Mobil["Android (Flet)"]
        UI[Ekranlar<br/>Özet · Hareketler · Diğer]
        API[ApiClient<br/>JWT + otomatik yenileme]
        UI --> API
    end

    subgraph Sunucu["Docker Compose (tek sunucu)"]
        NGINX[Nginx :8080]
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
        INV[saving_invest]:::todo
        REP[saving_reports]:::todo
    end
    WEB --- Apps

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
    subgraph G4["Planlanan"]
        C1[Günlük altın/gümüş/döviz fiyatı çek]:::todo
    end
    classDef todo fill:#eee,stroke:#999,stroke-dasharray:4 3,color:#777
```

---

## 6. Bakiye ve Özet hesabı

```mermaid
flowchart LR
    T[(İşlemler)] --> P[ÖDENDİ olanlar]
    T --> W[BEKLİYOR olanlar]

    P --> BAL["Hesap bakiyesi =<br/>açılış bakiyesi + ödenen gelir − ödenen gider"]
    BAL --> NOW[Şu anki bakiye<br/>= tüm hesapların toplamı]

    T --> MONTH["Seçili ay (sadece o ayın tarihleri)<br/>Gelir: alınan + bekleyen<br/>Gider: ödenen + bekleyen<br/>Ay net = gelir − gider"]

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

    HOME[Ana ekran] --> S[Özet<br/>ay seçimi · gelir/gider · bakiye · tahmin]
    HOME --> H[Hareketler]
    HOME --> D[Diğer]

    H --> HB[Bekleyen 30 gün + gecikenler<br/>Öde butonu]
    H --> HG[Geçmiş: ödenenler<br/>tür filtresi · daha fazla yükle]
    H --> NEW[+ Yeni kayıt formu]
    HB --> EDIT[Kayıt düzenle<br/>Ödendi işaretle / geri al<br/>kapsam: sadece bu / sonrakiler]
    HG --> EDIT

    D --> ACC[Hesaplar<br/>banka/nakit · açılış bakiyesi]
    D --> STM[Ekstreler<br/>yükle · önizle · aktar]
    D --> CAT[Kategoriler]
    D --> PRO[Profil]
    D --> OUT[Çıkış] --> LOGIN

    D -.-> INVS[Yatırımlar]:::todo
    classDef todo fill:#eee,stroke:#999,stroke-dasharray:4 3,color:#777
```

---

## 8. Ekstre aktarma

```mermaid
flowchart TD
    UP([Diğer > Ekstreler > Yükle<br/>hesap seç + PDF/Excel]) --> V{Uzantı pdf/xlsx<br/>ve ≤ 10 MB?}
    V -- Hayır --> E400[400: Türkçe hata]
    V -- Evet --> SAVE[Dosya gizli klasöre<br/>/vol/private · nginx sunmaz]
    SAVE --> TASK[Celery: parse_statement_task]
    TASK --> DET{Bankaya özel parser<br/>tanıdı mı?}
    DET -- Evet --> PARSE["Özel parser<br/>VakıfBank hesap (PDF/Excel) · VakıfBank kart<br/>QNB kart · Garanti kart · Enpara kart"]
    DET -- "Hayır (PDF)" --> GEN["Genel okuyucu (son çare)<br/>bozuk karakter çözücü (cid) +<br/>'tarih ... tutar' satır kalıpları"]
    GEN --> GENOK{Satır bulundu mu?}
    GENOK -- Hayır --> FAIL[Durum: Hata<br/>'Bu ekstreden hareket okunamadı']
    GENOK -- Evet --> WARN[Önizlemede uyarı:<br/>'genel okuyucu kullanıldı, kontrol edin']
    WARN --> RULES
    PARSE --> DEL[Dosya silinir<br/>sadece satırlar kalır]
    GEN --> DEL
    PARSE --> RULES

    subgraph RULES["Her satır için kurallar"]
        K1{Daha önce aktarıldı mı?<br/>banka ref no / hash} -- Evet --> SK1[Atla: mükerrer]
        K1 -- Hayır --> K2{Kart borcu ödemesi /<br/>kendi hesabına virman /<br/>fon, vadeli, yatırım?}
        K2 -- Evet --> SK2[Atla önerisi<br/>işaretsiz gelir]
        K2 -- Hayır --> K3{Aynı hesap + tutar,<br/>±7 gün bekleyen kayıt?<br/>taksitte: ekstre dönemi}
        K3 -- Evet --> MT[Eşleştir önerisi]
        K3 -- Hayır --> IM[Yeni kayıt]
        IM --> CAT[Anahtar kelimeyle kategori önerisi<br/>Migros→Market, Uber Eats→Yeme-İçme...]
        MT --> CAT
    end

    RULES --> READY[Durum: Onay bekliyor]
    READY --> REVIEW[Önizleme: işaretle / kaldır<br/>kategori · eşleştir ya da yeni kayıt]
    REVIEW --> CONF[Aktar]
    CONF --> T1[Yeni kayıtlar: ÖDENDİ<br/>kaynak=ekstre]
    CONF --> T2[Eşleşen bekleyen kayıt: ÖDENDİ<br/>ekstre tarihi ve tutarıyla]
    T1 --> DONE[Durum: Aktarıldı]
    T2 --> DONE
```

**Kart ekstresi kuralları**
- Önceki dönem bakiyesi, toplam ve "ödemeniz için teşekkürler" satırları hiç gelmez; harcamalar tek tek gelir.
- Hesap ekstresindeki "Kredi Kartı Borç Ödeme" satırı atlanır (çift sayım olmasın).
- Önceki dönemde başlamış taksit (ekstrede eski alışveriş tarihiyle görünür) → ekstre kesim tarihine yazılır.
- İade (eksi tutar) → gelir.

---

## 9. Planlanan fazlar (henüz yok)

```mermaid
flowchart LR
    F3["3 · saving_invest<br/>günlük fiyat (altın, gümüş, USD, EUR)<br/>portföy + değerleme"]:::todo
    F4["4 · saving_reports<br/>kategori dağılımı, aylık trend"]:::todo
    F5["5 · Mobil son<br/>güvenli token, APK, tasarım"]:::todo
    F3 --> F4 --> F5
    classDef todo fill:#eee,stroke:#999,stroke-dasharray:4 3,color:#777
```
