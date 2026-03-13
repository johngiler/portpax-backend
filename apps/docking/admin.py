from django.contrib import admin
from .models import Berth, Port, PortFeeRule, Scale, Ship, ShippingLine


@admin.register(ShippingLine)
class ShippingLineAdmin(admin.ModelAdmin):
    list_display = ["name", "code"]


@admin.register(Port)
class PortAdmin(admin.ModelAdmin):
    list_display = ["name", "code"]


@admin.register(Berth)
class BerthAdmin(admin.ModelAdmin):
    list_display = ["name", "port", "capacity_pax"]
    list_filter = ["port"]


@admin.register(Ship)
class ShipAdmin(admin.ModelAdmin):
    list_display = ["name", "shipping_line", "imo", "capacity_pax"]
    list_filter = ["shipping_line"]


@admin.register(Scale)
class ScaleAdmin(admin.ModelAdmin):
    list_display = ["ship", "port", "berth", "date", "pax_count"]
    list_filter = ["port", "date"]


@admin.register(PortFeeRule)
class PortFeeRuleAdmin(admin.ModelAdmin):
    list_display = ["port", "fee_tier", "amount_per_pax_usd", "valid_from", "valid_to"]
    list_filter = ["port", "fee_tier"]
