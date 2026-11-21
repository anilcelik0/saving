import random
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from lineup_cards.models import Attribute, Card, CardType, CardTypeAttribute, CardTypeField, CardValue, Tag

DEMO_TAG = "demo"

# Fictional names on purpose: demo values are random, so they must never look like facts about real places/works.
PROVINCE_NAMES = [
    "Yıldızkent", "Mavikıyı", "Gümüşova", "Altınyaka", "Serinköy", "Kızılsu", "Ayışığı", "Bulutdağ", "Çınarlı",
    "Rüzgarbey", "Akpınar Yaylası", "Demirkapı", "Sarıçam", "Karlıtepe", "Yeşilvadi", "Taşköprü Ovası",
    "Gökçeada Kıyısı", "Kartalyuva", "Ilgınlı", "Mercanbük",
]
EVENT_NAMES = [
    "Büyük Fener Bayramı", "Kayıp Kervanın Dönüşü", "Gümüş Köprü Açılışı", "Üç Dağ Antlaşması", "İlk Balon Uçuşu",
    "Saat Kulesi Yangını", "Kuzey Yıldızı Seferi", "Mavi Liman Kuruluşu", "Bakır Madeni Keşfi", "Yedi Göl Barışı",
    "Kum Fırtınası Yılı", "Telgraf Hattı Açılışı", "Altın Hasat Şenliği", "Demiryolu Birleşimi", "Kayalık Kalesi Kuşatması",
    "Büyük Kütüphane Açılışı", "Rüzgar Değirmeni Yarışı", "Dokuz Ada Fuarı", "Fırtına Gecesi", "Son Kervansaray",
]
FILM_NAMES = [
    "Kayıp Vadi", "Sisli Sokaklar", "Gece Yolcusu", "Kırmızı Balon", "Son Tren", "Rüzgarın Kızı", "Taş Bebek",
    "Uzak Fener", "Gölgedeki Adam", "Sonbahar Mektubu", "Kuşların Dili", "Mavi Kapı", "Beyaz Atlı", "Eski Plak",
    "Yaz Yağmuru", "Saklı Bahçe", "Kar Altında", "Dördüncü Kat", "Gizli Harita", "Ay Tutulması",
]


class Command(BaseCommand):
    help = (
        "Line Up demo card pool for development: 60 approved cards over 3 types (İl, Olay, Film) with FICTIONAL names "
        "and random values, all flagged is_demo and tagged 'demo'. Idempotent (same seed = same cards). "
        "--purge deletes every demo card instead."
    )

    def add_arguments(self, parser):
        parser.add_argument("--purge", action="store_true", help="Delete all demo cards (is_demo=True)")

    @transaction.atomic
    def handle(self, *args, purge=False, **options):
        if purge:
            count, _ = Card.objects.filter(is_demo=True).delete()
            Tag.objects.filter(slug=DEMO_TAG, cards__isnull=True, children__isnull=True).delete()
            self.stdout.write(self.style.SUCCESS(f"Demo cards deleted ({count} rows incl. values)."))
            return

        rng = random.Random(20261121)
        date = self._attribute("date", "Tarih", "date", "", "daha eski", "daha yeni")
        population = self._attribute("population", "Nüfus", "number", "kişi", "daha az nüfuslu", "daha kalabalık")
        area = self._attribute("area", "Yüzölçümü", "number", "km²", "daha küçük", "daha büyük")
        tag, _ = Tag.objects.get_or_create(slug=DEMO_TAG, defaults={"name": "Demo"})

        province = self._type("province", "İl", "🏙️", [(population, True), (area, True)], [("region", "Bölge")])
        event = self._type("event", "Olay", "📜", [(date, True)], [])
        film = self._type("film", "Film", "🎬", [(date, True)], [("director", "Yönetmen")])

        regions = ["Ege", "Marmara", "Akdeniz", "Karadeniz", "İç Anadolu", "Doğu Anadolu", "Güneydoğu Anadolu"]
        directors = ["A. Demo", "B. Örnek", "C. Deneme", "D. Taslak"]
        counts = {"created": 0, "updated": 0}

        for i, name in enumerate(PROVINCE_NAMES, 1):
            card = self._card(province, f"demo:province:{i}", name, rng, tag, counts,
                              extra={"region": rng.choice(regions)})
            self._value(card, population, number=Decimal(rng.randrange(80_000, 5_500_000, 1_000)))
            self._value(card, area, number=Decimal(rng.randrange(1_500, 40_000)))

        for i, name in enumerate(EVENT_NAMES, 1):
            card = self._card(event, f"demo:event:{i}", name, rng, tag, counts)
            year = rng.randint(1050, 2020)
            precision = rng.choice(["year", "year", "month", "day"])
            month = rng.randint(1, 12) if precision != "year" else None
            day = rng.randint(1, 28) if precision == "day" else None
            self._value(card, date, year=year, month=month, day=day)

        for i, name in enumerate(FILM_NAMES, 1):
            card = self._card(film, f"demo:film:{i}", name, rng, tag, counts, extra={"director": rng.choice(directors)})
            self._value(card, date, year=rng.randint(1950, 2024))

        # ties for the engine's equal-value rule: a film and an event in the same year, two films in the same year
        Card.objects.get(card_type=film, external_key="demo:film:1").values.filter(attribute=date).update(
            year=1999, month=None, day=None)
        Card.objects.get(card_type=film, external_key="demo:film:2").values.filter(attribute=date).update(
            year=1999, month=None, day=None)
        Card.objects.get(card_type=event, external_key="demo:event:1").values.filter(attribute=date).update(
            year=1999, month=8, day=17)

        self.stdout.write(self.style.SUCCESS(
            f"Demo pool ready: {counts['created']} created, {counts['updated']} updated "
            f"(İl {len(PROVINCE_NAMES)}, Olay {len(EVENT_NAMES)}, Film {len(FILM_NAMES)}; all approved, is_demo)."))

    @staticmethod
    def _attribute(key, name, value_type, unit, lower, higher):
        attribute, _ = Attribute.objects.get_or_create(key=key, defaults={
            "name": name, "value_type": value_type, "unit": unit, "lower_label": lower, "higher_label": higher})
        return attribute

    @staticmethod
    def _type(key, name, emoji, attributes, fields):
        card_type, _ = CardType.objects.get_or_create(key=key, defaults={"name": name, "emoji": emoji})
        for order, (attribute, required) in enumerate(attributes):
            CardTypeAttribute.objects.get_or_create(card_type=card_type, attribute=attribute,
                                                    defaults={"is_required": required, "order": order})
        for order, (field_key, label) in enumerate(fields):
            CardTypeField.objects.get_or_create(card_type=card_type, key=field_key,
                                                defaults={"label": label, "order": order})
        return card_type

    @staticmethod
    def _card(card_type, key, title, rng, tag, counts, extra=None):
        card, created = Card.objects.update_or_create(
            card_type=card_type, external_key=key,
            defaults={"title": title, "title_lang": "tr", "popularity": rng.randint(25, 100),
                      "status": Card.Status.APPROVED, "is_demo": True, "extra": extra or {}},
        )
        card.tags.add(tag)
        counts["created" if created else "updated"] += 1
        return card

    @staticmethod
    def _value(card, attribute, number=None, year=None, month=None, day=None):
        CardValue.objects.update_or_create(card=card, attribute=attribute,
                                           defaults={"number": number, "year": year, "month": month, "day": day})
