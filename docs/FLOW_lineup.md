# Akış Şeması: Line Up

Line Up istemcisinin uçtan uca akışı. Her faz tamamlandığında bu dosya güncellenir.
Kesikli çizgili / gri kutular henüz yapılmamış (planlanan) kısımlardır.

**Son güncelleme:** Faz 5 (ödüllü reklam, Pro, bulmaca arşivi; mağaza bağlantısı yayından önce) — 2026-11-22

---

## 1. Genel mimari

```mermaid
flowchart LR
    subgraph Mobil["Android (Flutter) · mobile_lineup"]
        UI[Ekranlar<br/>Başlangıç · Metin onayı · Giriş · Ana ekran + enerji<br/>Profil · Hesabını kaydet]
        DEV[Geliştirici araçları<br/>test reklamı · push]
        MODES[Zaman Çizgisi · Seri · Günlük bulmaca<br/>sürükle-bırak · kaydır · dokun]
        SHARE[Paylaşım<br/>🟩🟨🟥 sonuç metni]
        ADS[Ödüllü reklam · Pro ekranı<br/>UMP izni]
        LATER[Google ile giriş · meydan okuma ·<br/>mağazadan Pro satın alma]
        API[ApiClient<br/>JWT + yenileme + misafir girişi]
        STORE[(Şifreli depo<br/>token + misafir şifresi)]
        UI --> API
        MODES --> API
        MODES --> SHARE
        MODES --> ADS
        ADS --> API
        API --- STORE
    end

    subgraph Sunucu["Docker Compose (Saving ile ortak sunucu)"]
        ACC[accounts<br/>misafir hesap, hesabı kaydetme, giriş,<br/>metin onayı, dondurma / silme]
        NOTIF[notifications<br/>FCM gönderimi]
        CARDS[lineup_cards<br/>kart havuzu + içe aktarma]
        GAMES[lineup_games<br/>tur, hamle, enerji, ana ekran,<br/>günlük bulmaca, profil]
        ENGINE[engine<br/>saf Python: deste, eşitlik, kurallar, enerji]
        SUP[support<br/>kart hata bildirimi]
        BILL[billing<br/>ödül niyeti, SSV, Pro hakkı]
        BILL --> DB
        GAMES --> BILL
        DB[(PostgreSQL)]
        ACC --> DB
        CARDS --> DB
        GAMES --> DB
        GAMES --> ENGINE
        SUP --> DB
    end

    API -->|/api/v1/ · app=lineup| ACC
    API --> GAMES
    API -->|lineup.card| SUP
    NOTIF -->|firebase-admin| FCM[Firebase Cloud Messaging]
    FCM -->|bildirim| DEV
    SHARE -->|Android paylaş menüsü| WA[WhatsApp vb.]
    DEV -->|test reklam birimi| ADMOB[AdMob]
    ADS -->|reklam + SSV seçenekleri| ADMOB
    ADMOB -.->|SSV geri çağrısı: yayından sonra| BILL
    RC[RevenueCat] -.->|webhook: yayından sonra| BILL
    ADM[Django admin<br/>şablon → yükle → önizle → onay] --> CARDS

    classDef planned stroke-dasharray: 5 5,fill:#eee,color:#555
    class LATER planned
```

## 2. İlk açılış ve oturum

```mermaid
sequenceDiagram
    participant M as Mobil
    participant S as Sunucu (accounts)
    M->>M: Şifreli depoda oturum var mı?
    alt Oturum var
        M->>S: GET /auth/me/
        S-->>M: kullanıcı + onaylanmamış metinler + hesap durumu
        Note over M: Yeni metin sürümü varsa → onay ekranı → POST /auth/consents/
        Note over M: Dondurulmuş / silinmeyi bekliyor → "Yeniden aç" (POST /auth/account/reactivate/) ya da çıkış
    else Kayıtlı hesap vardı ama oturum yok (çıkış, dondurma, süre doldu)
        M->>M: Giriş ekranı (e-posta dolu) · ya da "Misafir olarak yeni başla"
    else İlk açılış
        M->>S: GET /legal/lineup/
        S-->>M: gizlilik + KVKK (güncel sürümler)
        M->>M: Onay ekranı (oku, işaretle, devam) · "Zaten hesabın var mı? Giriş yap"
        M->>S: POST /auth/guest/ {app, accepted_documents}
        S-->>M: kullanıcı + misafir şifresi (bir kez) + JWT
        M->>M: Şifre ve token'ları şifreli depoya yaz
    end
    Note over M,S: 401 → refresh token ile yenile; misafirse misafir şifresiyle yeniden giriş, kayıtlıysa giriş ekranı
    M->>M: Ana ekran
```

## 2b. Hesabı kaydetme ve başka cihazda giriş

```mermaid
sequenceDiagram
    participant M as Mobil
    participant S as Sunucu (accounts)
    M->>S: POST /auth/guest/claim/ {email, password, username?}
    S->>S: aynı kullanıcı satırı: e-posta + şifre, misafir değil · eski oturumlar kapanır
    S-->>M: kullanıcı + yeni JWT
    M->>M: misafir şifresini sil, giriş adını sakla
    Note over M,S: Yeni cihaz: onay ekranı → "Giriş yap" → POST /auth/login/ {app, identifier, password} → ilerleme geri gelir
    M->>S: Profil: çıkış (POST /auth/logout/) · dondur / sil (şifreyle; misafir saklı şifresiyle)
    Note over M,S: Google ile giriş: ertelendi (Faz 4.1b)
```

## 3. Kart havuzu ve içe aktarma

```mermaid
flowchart LR
    T[Kart türü<br/>nitelikler + ek alanlar] -->|Şablon indir| X[Excel / CSV]
    X -->|Dosya yükle| V[Doğrulama<br/>tarih/sayı biçimi, eksik değer,<br/>Türkçe başlık, tekrar]
    V --> P[Önizleme<br/>yeni · güncelle · değişmedi · hata]
    P -->|İçe aktar| S[Onay bekliyor<br/>dış anahtar ile güncelleme]
    S -->|Onayla: eksiksiz + Türkçe başlık| A[Onaylı kartlar<br/>oyun havuzu]
    W[Wikidata vb. kaynaklar] -.->|Faz 7: aynı hat| V
    D[seed_lineup_demo<br/>uydurma demo kartlar] --> A
```

## 4. Zaman Çizgisi turu

```mermaid
sequenceDiagram
    participant M as Mobil
    participant S as Sunucu (lineup_games)
    participant E as Motor (saf Python)
    M->>S: POST /lineup/games/runs/ {mode: timeline, difficulty}
    S->>S: enerji −1 (yoksa 409 no_energy) · aynı moddaki açık tur yarıda bırakılır
    S->>E: aday kartlar + tohum → deste (13 kart)
    S-->>M: çizgi (değerleriyle) + yeni kart (değersiz)
    loop her kart (süre sınırı yok)
        M->>S: POST moves/ {slot}
        S->>E: doğru boşluklar (eşitlikte iki taraf da doğru)
        S-->>M: doğru/yanlış + kartın değeri + yeni durum
    end
    Note over M,S: 10 kartlık çizgi = kazandın · 3 hata = kaybettin · deste biterse tur biter
```

## 5. Seri turu ve enerji

```mermaid
sequenceDiagram
    participant M as Mobil
    participant S as Sunucu (lineup_games)
    participant E as Motor (saf Python)
    M->>S: GET /lineup/games/home/
    S->>E: enerji = min(maks, kayıtlı + geçen süre / dolum)
    S-->>M: enerji (sonraki / dolu için saniye) · açık turlar · rekor
    M->>S: POST runs/ {mode: streak}
    alt Enerji yok
        S-->>M: 409 no_energy → "Enerjin bitti" (reklam / Pro: Faz 5)
    else Enerji var (ya da ilk 3 gün sınırsız)
        S->>E: tohum → deste (önce tanınmış kartlar, aralık seri uzadıkça daralır)
        S-->>M: açık kart (değeriyle) + sıradaki kart (değersiz)
        loop her tahmin
            M->>S: POST moves/ {guess: higher | lower}
            S->>E: karşılaştır (eşitse iki tahmin de doğru)
            S-->>M: doğru/yanlış + kartın değeri · açılan kart yeni açık kart olur
        end
        Note over M,S: ilk hatada tur biter (1 can) · rekor = en uzun seri · devam hakkı Faz 5'te
    end
```

## 6. Günlük bulmaca ve paylaşım

```mermaid
sequenceDiagram
    participant M as Mobil
    participant S as Sunucu (lineup_games)
    participant E as Motor (saf Python)
    M->>S: GET /lineup/games/daily/
    alt Bulmaca gününün ilk isteği (her sabah 07:30, İstanbul)
        S->>E: rastgele nitelik + tohum → 6 kart (tanınmış, değerler arası boşluk, sıralı gösterilmez)
        S->>S: DailyPuzzle (tarih tekil, no +1, deste donar)
    end
    S-->>M: herkese aynı 6 kart (değersiz) · denemeler · yeni bulmacaya kalan süre
    loop en fazla 3 deneme (enerji harcamaz)
        M->>M: kartları sürükleyerek sırala (🚩 = kart hata bildirimi)
        M->>S: POST daily/attempts/ {number, order}
        S->>E: her yer: 🟩 doğru · 🟨 bir yer yanında · 🟥 daha uzakta (eşitlikte iki yer de doğru)
        S-->>M: işaretler + yeni durum
    end
    S-->>M: bitince: değerler + doğru sıra + paylaşım metni
    M->>M: "Sonucu paylaş" → Line Up · Günlük #12 (Nüfus) / 🟥🟨🟩… / 🟩🟩🟩… – 2. deneme
    Note over M,S: 07:30 geçtiyse 409 daily_expired → yeni bulmaca yüklenir · kart adları paylaşılmaz (spoiler yok)
```

## 7. Ödüllü reklam ve Pro

```mermaid
sequenceDiagram
    participant M as Mobil
    participant S as Sunucu (billing + lineup_games)
    participant A as AdMob
    M->>S: POST /billing/rewards/ {kind: lineup.energy | lineup.continue, ref}
    S->>S: uygun mu? (enerji dolu değil / tur devam edebilir) · günlük sınır (10)
    S-->>M: ödül niyeti (id, kullanıcı id)
    M->>M: UMP izni (AB/UK, ilk reklamdan önce)
    M->>A: ödüllü reklam (SSV: user_id + custom_data = niyet id)
    A-->>M: reklam izlendi
    alt Yayında
        A->>S: GET /billing/admob/ssv/?...&signature&key_id (Google anahtarıyla ECDSA doğrulama)
        S->>S: niyeti tekrar kontrol et → ödülü ver (işlem id ile bir kez)
        M->>S: GET /billing/rewards/<id>/ (birkaç saniye bekler)
    else Geliştirme (DEBUG)
        M->>S: POST /billing/dev/rewards/<id>/grant/ (aynı ödül yolu, imzasız)
    end
    S-->>M: verildi → +1 enerji / tur 1 canla devam
    Note over M,S: Pro: sınırsız enerji · POST runs/<id>/continue/ reklamsız · geçmiş bulmacalar (seriye sayılmaz)
    Note over S: RevenueCat webhook → Pro hakkı (bitiş tarihi) · satın alma ekranı yayından önce (9.2)
```
