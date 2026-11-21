# Akış Şeması: Line Up

Line Up istemcisinin uçtan uca akışı. Her faz tamamlandığında bu dosya güncellenir.
Kesikli çizgili kutular henüz yapılmamış (planlanan) kısımlardır.

**Son güncelleme:** Faz 0 planlandı (henüz kod yok) — 2026-11-21

---

## 1. Genel mimari (planlanan)

```mermaid
flowchart LR
    subgraph Mobil["Android (Flutter) · mobile_lineup"]
        UI[Ekranlar<br/>Zaman Çizgisi · Seri · Günlük]
        API[ApiClient<br/>JWT + otomatik yenileme]
        UI --> API
    end

    subgraph Sunucu["Docker Compose (Saving ile ortak sunucu)"]
        ACC[accounts<br/>misafir + giriş, app=lineup]
        CARDS[lineup_cards<br/>kart havuzu + içe aktarma]
        GAMES[lineup_games<br/>oturum, hamle, enerji, günlük]
        ENG[engine<br/>saf Python motor]
        DB[(PostgreSQL)]
        ACC --> DB
        CARDS --> DB
        GAMES --> ENG
        GAMES --> DB
    end

    API -->|/api/v1/ HTTPS| ACC
    API --> GAMES
    ADM[Django admin<br/>şablon → önizleme → onay] --> CARDS

    classDef planned stroke-dasharray: 5 5,fill:#eee,color:#555
    class UI,API,ACC,CARDS,GAMES,ENG,ADM planned
```
