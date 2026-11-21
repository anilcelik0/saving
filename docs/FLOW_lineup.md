# Akış Şeması: Line Up

Line Up istemcisinin uçtan uca akışı. Her faz tamamlandığında bu dosya güncellenir.
Kesikli çizgili / gri kutular henüz yapılmamış (planlanan) kısımlardır.

**Son güncelleme:** Faz 0 (temel kurulum: misafir hesap, Flutter iskeleti, test reklamı + push) — 2026-11-21

---

## 1. Genel mimari

```mermaid
flowchart LR
    subgraph Mobil["Android (Flutter) · mobile_lineup"]
        UI[Ekranlar<br/>Başlangıç · Metin onayı · Ana ekran]
        DEV[Geliştirici araçları<br/>test reklamı · push]
        MODES[Oyun ekranları<br/>Zaman Çizgisi · Seri · Günlük]
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
        GAMES[lineup_games<br/>oturum, hamle, enerji, günlük]
        DB[(PostgreSQL)]
        ACC --> DB
        CARDS --> DB
        GAMES --> DB
    end

    API -->|/api/v1/ · app=lineup| ACC
    API -.-> GAMES
    NOTIF -->|firebase-admin| FCM[Firebase Cloud Messaging]
    FCM -->|bildirim| DEV
    DEV -->|test reklam birimi| ADMOB[AdMob]
    ADM[Django admin] -.-> CARDS

    classDef planned stroke-dasharray: 5 5,fill:#eee,color:#555
    class MODES,CARDS,GAMES,ADM planned
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
