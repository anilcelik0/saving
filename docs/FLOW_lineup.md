# Akış Şeması: Line Up

Line Up istemcisinin uçtan uca akışı. Her faz tamamlandığında bu dosya güncellenir.
Kesikli çizgili / gri kutular henüz yapılmamış (planlanan) kısımlardır.

**Son güncelleme:** Faz 1 (kart havuzu, içe aktarma, oyun motoru, Zaman Çizgisi) — 2026-11-22

---

## 1. Genel mimari

```mermaid
flowchart LR
    subgraph Mobil["Android (Flutter) · mobile_lineup"]
        UI[Ekranlar<br/>Başlangıç · Metin onayı · Ana ekran]
        DEV[Geliştirici araçları<br/>test reklamı · push]
        MODES[Zaman Çizgisi<br/>sürükle-bırak · dokun · geri sayım]
        LATER[Seri · Günlük bulmaca]
        API[ApiClient<br/>JWT + yenileme + misafir girişi]
        STORE[(Şifreli depo<br/>token + misafir şifresi)]
        UI --> API
        MODES --> API
        API --- STORE
    end

    subgraph Sunucu["Docker Compose (Saving ile ortak sunucu)"]
        ACC[accounts<br/>misafir hesap, giriş, metin onayı]
        NOTIF[notifications<br/>FCM gönderimi]
        CARDS[lineup_cards<br/>kart havuzu + içe aktarma]
        GAMES[lineup_games<br/>tur, hamle, süre kontrolü]
        ENGINE[engine<br/>saf Python: deste, eşitlik, kurallar]
        SUP[support<br/>kart hata bildirimi]
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
    DEV -->|test reklam birimi| ADMOB[AdMob]
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
        S-->>M: kullanıcı + onaylanmamış metinler
        Note over M: Yeni metin sürümü varsa → onay ekranı → POST /auth/consents/
    else İlk açılış
        M->>S: GET /legal/lineup/
        S-->>M: gizlilik + KVKK (güncel sürümler)
        M->>M: Onay ekranı (oku, işaretle, devam)
        M->>S: POST /auth/guest/ {app, accepted_documents}
        S-->>M: kullanıcı + misafir şifresi (bir kez) + JWT
        M->>M: Şifre ve token'ları şifreli depoya yaz
    end
    Note over M,S: 401 → refresh token ile yenile; o da geçersizse misafir şifresiyle yeniden giriş
    M->>M: Ana ekran
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
    M->>S: POST /lineup/games/runs/ {difficulty}
    S->>E: aday kartlar + tohum → deste (13 kart)
    S-->>M: çizgi (değerleriyle) + yeni kart (değersiz) + kalan süre
    loop her kart (10 sn + 2 sn ağ payı)
        M->>S: POST moves/ {slot} (süre bitince slot=null)
        S->>E: süre kontrolü + doğru boşluklar (eşitlikte iki taraf da doğru)
        S-->>M: doğru/yanlış + kartın değeri + yeni durum
    end
    Note over M,S: 10 kartlık çizgi = kazandın · 3 hata = kaybettin · deste biterse tur biter
```
