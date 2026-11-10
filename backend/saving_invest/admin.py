from django.contrib import admin

from .models import Asset, AssetPrice, Deposit, Trade


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "asset_type", "unit", "provider", "source_code", "sort_order", "is_active"]
    list_filter = ["asset_type", "provider", "is_active"]


@admin.register(AssetPrice)
class AssetPriceAdmin(admin.ModelAdmin):
    list_display = ["asset", "date", "buy", "sell", "source_time"]
    list_filter = ["asset"]
    date_hierarchy = "date"


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display = ["date", "user", "asset", "side", "quantity", "unit_price", "proceeds", "account"]
    list_filter = ["side", "asset"]
    search_fields = ["user__username", "note"]


@admin.register(Deposit)
class DepositAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "principal", "annual_rate", "start_date", "maturity_date", "maturity_amount",
                    "status"]
    list_filter = ["status"]
    search_fields = ["name", "user__username"]
