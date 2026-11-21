from django import forms
from django.contrib import admin, messages
from django.contrib.admin.utils import flatten_fieldsets
from django.db.models import Count, Q
from django.utils.html import format_html_join

from . import services
from .models import Attribute, Card, CardType, CardTypeAttribute, CardTypeField, CardValue, Tag

EXTRA_PREFIX = "extra__"


# ---------------------------------------------------------------- schema
@admin.register(Attribute)
class AttributeAdmin(admin.ModelAdmin):
    list_display = ["name", "key", "value_type", "unit", "decimal_places", "lower_label", "higher_label", "is_active"]
    list_filter = ["value_type", "is_active"]
    search_fields = ["name", "key"]


class CardTypeAttributeInline(admin.TabularInline):
    model = CardTypeAttribute
    extra = 1
    autocomplete_fields = ["attribute"]


class CardTypeFieldInline(admin.TabularInline):
    model = CardTypeField
    extra = 1


@admin.register(CardType)
class CardTypeAdmin(admin.ModelAdmin):
    list_display = ["__str__", "key", "attribute_names", "approved_count", "staging_count"]
    search_fields = ["name", "key"]
    inlines = [CardTypeAttributeInline, CardTypeFieldInline]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("attributes").annotate(
            approved=Count("cards", filter=Q(cards__status=Card.Status.APPROVED)),
            staging=Count("cards", filter=Q(cards__status=Card.Status.STAGING)),
        )

    @admin.display(description="nitelikler")
    def attribute_names(self, obj):
        return ", ".join(a.name for a in obj.attributes.all())

    @admin.display(description="onaylı", ordering="approved")
    def approved_count(self, obj):
        return obj.approved

    @admin.display(description="onay bekleyen", ordering="staging")
    def staging_count(self, obj):
        return obj.staging


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ["__str__", "slug", "card_count"]
    search_fields = ["name", "slug"]
    autocomplete_fields = ["parent"]
    prepopulated_fields = {"slug": ["name"]}
    list_select_related = ["parent__parent"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(card_total=Count("cards"))

    @admin.display(description="kart", ordering="card_total")
    def card_count(self, obj):
        return obj.card_total


# ---------------------------------------------------------------- cards
class PopularityFilter(admin.SimpleListFilter):
    title = "tanınırlık"
    parameter_name = "popularity"
    BANDS = {"low": (0, 29, "Düşük (0-29)"), "mid": (30, 59, "Orta (30-59)"), "high": (60, 100, "Yüksek (60-100)")}

    def lookups(self, request, model_admin):
        return [(key, label) for key, (_, _, label) in self.BANDS.items()]

    def queryset(self, request, queryset):
        if self.value() in self.BANDS:
            low, high, _ = self.BANDS[self.value()]
            return queryset.filter(popularity__gte=low, popularity__lte=high)
        return queryset


class CardValueInline(admin.TabularInline):
    model = CardValue
    extra = 1
    fields = ["attribute", "number", "year", "month", "day", "source_url"]
    verbose_name_plural = "değerler (türde olmayan bir nitelik seçilirse türe isteğe bağlı olarak eklenir)"

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "attribute":
            kwargs["queryset"] = Attribute.objects.filter(is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class CardAdminForm(forms.ModelForm):
    """The card type's display fields appear as plain text inputs (stored in Card.extra)."""

    class Meta:
        model = Card
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extra_fields = []
        if self.instance.card_type_id:
            stored = self.instance.extra or {}
            for field in self.instance.card_type.fields.all():
                name = f"{EXTRA_PREFIX}{field.key}"
                self.fields[name] = forms.CharField(label=field.label, required=False,
                                                    initial=stored.get(field.key, ""))
                self.extra_fields.append((name, field.key))

    def clean(self):
        cleaned = super().clean()
        if self.extra_fields:
            extra = {}
            for name, key in self.extra_fields:
                value = (cleaned.get(name) or "").strip()
                if value:
                    extra[key] = value
            self.instance.extra = extra
        return cleaned


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    form = CardAdminForm
    list_display = ["__str__", "card_type", "values_summary", "popularity", "status", "is_demo", "review_flags"]
    list_filter = ["status", "card_type", "is_demo", PopularityFilter, "title_lang", "tags"]
    search_fields = ["title", "subtitle", "external_key"]
    list_select_related = ["card_type"]
    autocomplete_fields = ["tags"]
    readonly_fields = ["review", "created_at", "updated_at"]
    inlines = [CardValueInline]
    actions = ["approve", "reject", "back_to_staging"]
    list_per_page = 50

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(*services.REVIEW_PREFETCH)

    def get_fieldsets(self, request, obj=None):
        fieldsets = [
            (None, {"fields": ["card_type", "title", "subtitle", "title_lang", "popularity", "status", "tags"]}),
        ]
        if obj is not None:
            names = [f"{EXTRA_PREFIX}{f.key}" for f in obj.card_type.fields.all()]
            if names:
                fieldsets.append(("Ek bilgiler (kart türüne göre)", {"fields": names}))
            fieldsets.append(("İnceleme", {"fields": ["review", "notes"]}))
        else:
            fieldsets.append(("Ek bilgiler", {"fields": [], "description":
                              "Türü seçip kaydedin; türün ek alanları ve nitelik seçenekleri sonra gelir."}))
        fieldsets.append(("Kaynak", {"fields": ["source_url", "external_key", "fetched_at", "is_demo"]}))
        if obj is not None:
            fieldsets.append(("Kayıt", {"classes": ["collapse"], "fields": ["created_at", "updated_at"]}))
        return fieldsets

    def get_form(self, request, obj=None, change=False, **kwargs):
        # extra__* fields are added by CardAdminForm itself; the model form factory must not see them
        fields = flatten_fieldsets(self.get_fieldsets(request, obj))
        kwargs["fields"] = [f for f in fields if not f.startswith(EXTRA_PREFIX) and f not in self.readonly_fields]
        return super().get_form(request, obj, change, **kwargs)

    def get_readonly_fields(self, request, obj=None):
        # the type decides the schema: changing it later would orphan values and extra fields
        return [*self.readonly_fields, "card_type"] if obj is not None else self.readonly_fields

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        added = services.extend_schema(form.instance)
        if added:
            self.message_user(request, f"'{form.instance.card_type}' türüne isteğe bağlı nitelik eklendi: "
                              + ", ".join(a.name for a in added), messages.INFO)
        # fresh copy: the edited object may carry prefetched values from before the inline save
        card = self.get_queryset(request).get(pk=form.instance.pk)
        if card.status == Card.Status.APPROVED:
            problems = services.approval_problems(card)
            if problems:
                card.status = Card.Status.STAGING
                card.save(update_fields=["status", "updated_at"])
                self.message_user(request, f"'{card}' onaylanamadı, onay bekliyor durumunda kaldı: "
                                  + " ".join(problems), messages.WARNING)

    @admin.display(description="değerler")
    def values_summary(self, obj):
        return " · ".join(v.display() for v in obj.values.all()) or "-"

    @admin.display(description="uyarı")
    def review_flags(self, obj):
        problems = services.approval_problems(obj) if obj.status != Card.Status.REJECTED else []
        return "⛔" if problems else ("⚠" if services.review_warnings(obj) else "")

    @admin.display(description="onay kontrolü")
    def review(self, obj):
        problems = [("⛔", p) for p in services.approval_problems(obj)]
        warnings = [("⚠", w) for w in services.review_warnings(obj)]
        if not problems and not warnings:
            return "✔ Onaya hazır"
        return format_html_join("\n", "<div>{} {}</div>", problems + warnings)

    @admin.action(description="Onayla (eksiği olanlar atlanır)")
    def approve(self, request, queryset):
        cards = queryset.prefetch_related(*services.REVIEW_PREFETCH)
        changed, skipped = services.set_status(cards, Card.Status.APPROVED)
        self.message_user(request, f"{changed} kart onaylandı.", messages.SUCCESS)
        for card, problems in skipped[:10]:
            self.message_user(request, f"Atlandı: {card}: {' '.join(problems)}", messages.WARNING)
        if len(skipped) > 10:
            self.message_user(request, f"... ve {len(skipped) - 10} kart daha atlandı.", messages.WARNING)

    @admin.action(description="Reddet")
    def reject(self, request, queryset):
        changed, _ = services.set_status(queryset, Card.Status.REJECTED)
        self.message_user(request, f"{changed} kart reddedildi.", messages.SUCCESS)

    @admin.action(description="Onay bekliyor durumuna al")
    def back_to_staging(self, request, queryset):
        changed, _ = services.set_status(queryset, Card.Status.STAGING)
        self.message_user(request, f"{changed} kart onay bekliyor durumuna alındı.", messages.SUCCESS)
