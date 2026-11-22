"""
Line Up card pool. New categories need no migration: an admin defines an Attribute (what is compared), a CardType
(which attributes and display fields its cards have) and then adds cards (by hand or by import, Phase 1.3).

Cards are shared content, not user data. Values come from sources (CardValue.source_url), never invented; demo cards
(`is_demo`) are the only exception and are purged before release.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, RegexValidator
from django.db import models
from django.db.models import Q

from core.base_models import BaseModel

from . import values

key_validator = RegexValidator(r"^[a-z0-9_]+$", "Yalnızca küçük harf, rakam ve '_' kullanın.")


class Attribute(BaseModel):
    """A comparable quantity, e.g. date, population. Cards of different types meet on the same attribute."""

    class ValueType(models.TextChoices):
        NUMBER = "number", "Sayı"
        DATE = "date", "Tarih"

    key = models.CharField(max_length=50, unique=True, validators=[key_validator],
                           help_text="Makine adı, ör. date, population, area, transfer_fee")
    name = models.CharField("ad", max_length=100, help_text="Görünen ad, ör. Tarih, Nüfus")
    value_type = models.CharField("değer tipi", max_length=10, choices=ValueType.choices)
    unit = models.CharField("birim", max_length=20, blank=True, help_text="ör. kişi, km², €, TL (tarihte boş)")
    decimal_places = models.PositiveSmallIntegerField("ondalık basamak", default=0, validators=[MaxValueValidator(4)])
    lower_label = models.CharField("küçük olan", max_length=50, help_text='ör. "daha eski", "daha az nüfuslu"')
    higher_label = models.CharField("büyük olan", max_length=50, help_text='ör. "daha yeni", "daha kalabalık"')
    is_active = models.BooleanField("aktif", default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "nitelik"
        verbose_name_plural = "nitelikler"

    def __str__(self):
        return f"{self.name} ({self.unit})" if self.unit else self.name

    def clean(self):
        if self.value_type == self.ValueType.DATE and (self.unit or self.decimal_places):
            raise ValidationError("Tarih niteliğinde birim ve ondalık basamak olmaz.")


class CardType(BaseModel):
    """Schema of a kind of card (İl, Film, Futbolcu...): its attributes and display-only fields."""

    key = models.CharField(max_length=50, unique=True, validators=[key_validator], help_text="ör. province, film")
    name = models.CharField("ad", max_length=100)
    emoji = models.CharField(max_length=8, blank=True, help_text="Kartta görsel yerine gösterilir")
    description = models.TextField("açıklama", blank=True)
    attributes = models.ManyToManyField(Attribute, through="CardTypeAttribute", related_name="card_types")
    target_count = models.PositiveIntegerField("hedef kart sayısı", default=0,
                                               help_text="Onaylı kart hedefi (dağılım raporu); 0 = hedef yok")

    class Meta:
        ordering = ["name"]
        verbose_name = "kart türü"
        verbose_name_plural = "kart türleri"

    def __str__(self):
        return f"{self.emoji} {self.name}".strip()


class CardTypeAttribute(BaseModel):
    card_type = models.ForeignKey(CardType, on_delete=models.CASCADE, related_name="schema_attributes")
    attribute = models.ForeignKey(Attribute, on_delete=models.PROTECT, related_name="schema_entries",
                                  verbose_name="nitelik")
    is_required = models.BooleanField("zorunlu", default=True, help_text="Onay için bu değer gerekli")
    order = models.PositiveSmallIntegerField("sıra", default=0)

    class Meta:
        ordering = ["order", "attribute__name"]
        verbose_name = "kart türü niteliği"
        verbose_name_plural = "kart türü nitelikleri"
        constraints = [models.UniqueConstraint(fields=["card_type", "attribute"], name="uniq_lineup_type_attribute")]

    def __str__(self):
        return f"{self.card_type}: {self.attribute}"


class CardTypeField(BaseModel):
    """Display-only text field of a card type (e.g. Bölge, Takım, Yönetmen); stored in Card.extra[key]."""

    card_type = models.ForeignKey(CardType, on_delete=models.CASCADE, related_name="fields")
    key = models.CharField(max_length=50, validators=[key_validator])
    label = models.CharField("etiket", max_length=100)
    is_required = models.BooleanField("zorunlu", default=False)
    order = models.PositiveSmallIntegerField("sıra", default=0)

    class Meta:
        ordering = ["order", "label"]
        verbose_name = "ek alan"
        verbose_name_plural = "ek alanlar"
        constraints = [models.UniqueConstraint(fields=["card_type", "key"], name="uniq_lineup_type_field")]

    def __str__(self):
        return self.label


class Tag(BaseModel):
    """Hierarchical tag (Futbol > Galatasaray) for category mixes and difficulty."""

    name = models.CharField("ad", max_length=100)
    slug = models.SlugField(max_length=100, unique=True, allow_unicode=False)
    parent = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="children",
                               verbose_name="üst etiket")

    class Meta:
        ordering = ["name"]
        verbose_name = "etiket"
        verbose_name_plural = "etiketler"

    def __str__(self):
        names, tag, seen = [], self, set()
        while tag is not None and tag.pk not in seen:
            seen.add(tag.pk)
            names.append(tag.name)
            tag = tag.parent
        return " › ".join(reversed(names))

    def clean(self):
        tag, seen = self.parent, set()
        while tag is not None:
            if tag.pk == self.pk or tag.pk in seen:
                raise ValidationError({"parent": "Etiket kendi alt etiketinin altına konamaz."})
            seen.add(tag.pk)
            tag = tag.parent


class Card(BaseModel):
    class Status(models.TextChoices):
        STAGING = "staging", "Onay bekliyor"
        APPROVED = "approved", "Onaylı"
        REJECTED = "rejected", "Reddedildi"

    card_type = models.ForeignKey(CardType, on_delete=models.PROTECT, related_name="cards", verbose_name="tür")
    title = models.CharField("başlık", max_length=200)
    title_lang = models.CharField("başlık dili", max_length=8, default="tr",
                                  help_text="Kaynakta Türkçe ad yoksa ör. en; onay için Türkçe başlık (tr) gerekir")
    subtitle = models.CharField("alt başlık", max_length=200, blank=True, help_text="ör. şarkı için sanatçı")
    popularity = models.PositiveSmallIntegerField("tanınırlık", default=50, validators=[MaxValueValidator(100)],
                                                  help_text="0-100; kolay modlar yüksek tanınırlıklı kartları seçer")
    status = models.CharField("durum", max_length=10, choices=Status.choices, default=Status.STAGING, db_index=True)
    tags = models.ManyToManyField(Tag, blank=True, related_name="cards", verbose_name="etiketler")
    extra = models.JSONField("ek bilgiler", default=dict, blank=True,
                             help_text="Kart türünün ek alanları (yalnızca gösterilir, karşılaştırılmaz)")
    external_key = models.CharField("dış anahtar", max_length=200, blank=True,
                                    help_text="Kaynaktaki kimlik (ör. wikidata:Q406); içe aktarma bununla günceller")
    source_url = models.URLField("kaynak", max_length=500, blank=True)
    fetched_at = models.DateTimeField("kaynaktan alındı", null=True, blank=True)
    is_demo = models.BooleanField("demo", default=False, help_text="Uydurma test verisi; yayından önce silinir")
    notes = models.TextField("notlar", blank=True, help_text="İnceleme / ret notu (yalnızca admin)")

    class Meta:
        ordering = ["title"]
        verbose_name = "kart"
        verbose_name_plural = "kartlar"
        constraints = [
            models.UniqueConstraint(fields=["card_type", "external_key"], condition=~Q(external_key=""),
                                    name="uniq_lineup_card_external_key"),
        ]
        indexes = [models.Index(fields=["status", "popularity"], name="lineup_card_status_pop")]

    def __str__(self):
        return f"{self.title} ({self.subtitle})" if self.subtitle else self.title

    def clean(self):
        if not isinstance(self.extra, dict):
            raise ValidationError({"extra": "Ek bilgiler bir sözlük (JSON nesnesi) olmalı."})
        if self.card_type_id and self.extra:
            known = set(self.card_type.fields.values_list("key", flat=True))
            unknown = sorted(set(self.extra) - known)
            if unknown:
                raise ValidationError({"extra": f"Kart türünde tanımlı olmayan alan: {', '.join(unknown)}"})


class CardValue(BaseModel):
    """One attribute value of a card: a number, or a (partial) date that keeps its precision."""

    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="values")
    attribute = models.ForeignKey(Attribute, on_delete=models.PROTECT, related_name="card_values",
                                  verbose_name="nitelik")
    number = models.DecimalField("sayı", max_digits=20, decimal_places=4, null=True, blank=True)
    year = models.IntegerField("yıl", null=True, blank=True, help_text="MÖ için eksi (MÖ 1200 = -1200)")
    month = models.PositiveSmallIntegerField("ay", null=True, blank=True)
    day = models.PositiveSmallIntegerField("gün", null=True, blank=True)
    source_url = models.URLField("kaynak", max_length=500, blank=True, help_text="Boşsa kartın kaynağı geçerli")

    class Meta:
        ordering = ["attribute__name"]
        verbose_name = "değer"
        verbose_name_plural = "değerler"
        constraints = [models.UniqueConstraint(fields=["card", "attribute"], name="uniq_lineup_card_attribute")]
        indexes = [
            models.Index(fields=["attribute", "number"], name="lineup_value_number"),
            models.Index(fields=["attribute", "year", "month", "day"], name="lineup_value_date"),
        ]

    def __str__(self):
        return f"{self.attribute.name}: {self.display()}"

    @property
    def precision(self) -> values.Precision | None:
        if self.attribute.value_type != Attribute.ValueType.DATE or self.year is None:
            return None
        return values.date_precision(self.month, self.day)

    def display(self) -> str:
        if self.attribute.value_type == Attribute.ValueType.DATE:
            return values.format_date(self.year, self.month, self.day) if self.year is not None else "-"
        if self.number is None:
            return "-"
        return values.format_number(self.number, self.attribute.decimal_places, self.attribute.unit)

    def clean(self):
        if not self.attribute_id:
            return
        attribute = self.attribute
        date_set = any(v is not None for v in (self.year, self.month, self.day))
        errors = {}
        if attribute.value_type == Attribute.ValueType.NUMBER:
            if self.number is None:
                errors["number"] = "Bu nitelik için sayı girin."
            elif values.decimal_places_of(self.number) > attribute.decimal_places:
                errors["number"] = f"En fazla {attribute.decimal_places} ondalık basamak girilebilir."
            if date_set:
                errors["year"] = "Sayı niteliğinde yıl/ay/gün boş kalmalı."
        else:
            if self.number is not None:
                errors["number"] = "Tarih niteliğinde sayı boş kalmalı."
            problems = values.date_problems(self.year, self.month, self.day)
            if problems:
                errors["year"] = problems
        if errors:
            raise ValidationError(errors)


class CardImport(BaseModel):
    """One upload through the import pipeline (importer.py): validated rows wait in preview until applied."""

    class Status(models.TextChoices):
        PREVIEW = "preview", "Önizleme"
        APPLIED = "applied", "İçe aktarıldı"
        CANCELLED = "cancelled", "Vazgeçildi"

    card_type = models.ForeignKey(CardType, on_delete=models.PROTECT, related_name="imports", verbose_name="tür")
    file_name = models.CharField("dosya", max_length=255)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="+", verbose_name="yükleyen")
    status = models.CharField("durum", max_length=10, choices=Status.choices, default=Status.PREVIEW)
    rows = models.JSONField(default=list, blank=True)
    file_warnings = models.JSONField(default=list, blank=True)
    summary = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)
    applied_at = models.DateTimeField("içe aktarıldı", null=True, blank=True)
    source = models.ForeignKey("CardSource", on_delete=models.SET_NULL, null=True, blank=True, related_name="imports",
                               verbose_name="kaynak", help_text="Boşsa dosya yüklemesi")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "içe aktarma"
        verbose_name_plural = "içe aktarmalar"

    def __str__(self):
        return f"{self.card_type} · {self.file_name}"


class CardSource(BaseModel):
    """
    An external source feeding a card type through the import pipeline (lineup_cards.sources). Wikidata today: a
    SPARQL query whose variables follow sources/wikidata.py. "Çek" makes a preview; the monthly refresh applies new and
    changed cards to staging (approved cards whose values changed are reviewed again).
    """

    class Kind(models.TextChoices):
        WIKIDATA = "wikidata", "Wikidata (SPARQL)"

    card_type = models.ForeignKey(CardType, on_delete=models.PROTECT, related_name="sources", verbose_name="tür")
    kind = models.CharField("kaynak", max_length=20, choices=Kind.choices, default=Kind.WIKIDATA)
    name = models.CharField("ad", max_length=100)
    query = models.TextField("sorgu", help_text="SPARQL; değişkenler: ?item ?title_tr ?title_en ?sitelinks ?trwiki, "
                                                "nitelik anahtarları (?population, ?date …), ?<anahtar>_precision / "
                                                "_date / _rank, ek alan anahtarları (?region …)")
    tags = models.CharField("etiketler", max_length=200, blank=True, help_text="Her karta eklenir, virgülle")
    limit = models.PositiveIntegerField("en fazla kart", default=500,
                                        help_text="En çok Vikipedi'si olanlardan bu kadarı (içe aktarma sınırı 5000)")
    use_pageviews = models.BooleanField("Türkçe Vikipedi görüntülenmesi", default=True,
                                        help_text="Tanınırlığa katılır (madde başına bir istek; büyük kaynakta yavaş)")
    auto_refresh = models.BooleanField("aylık yenile", default=True)
    last_run_at = models.DateTimeField("son çekim", null=True, blank=True)
    last_error = models.TextField("son hata", blank=True)

    class Meta:
        ordering = ["card_type__name", "name"]
        verbose_name = "kart kaynağı"
        verbose_name_plural = "kart kaynakları"

    def __str__(self):
        return self.name

