from django.contrib import admin

from apps.catalogs.models import (
    Berth,
    MooringScenario,
    MooringScenarioSlot,
    Port,
    Position,
    ShippingLine,
    ShippingLineGroup,
    Vessel,
)


class BerthInline(admin.TabularInline):
    model = Berth
    extra = 0
    fields = ("code", "name", "length_m", "width_m", "min_draft_m", "sort_order", "is_active")


class PositionInline(admin.TabularInline):
    model = Position
    extra = 0
    fields = (
        "code",
        "position_type",
        "berth",
        "max_loa_m",
        "out_of_service",
        "is_projection",
        "sort_order",
        "is_active",
    )


class MooringScenarioSlotInline(admin.TabularInline):
    model = MooringScenarioSlot
    extra = 0
    fields = ("slot_label", "position", "max_loa_m", "sort_order")


@admin.register(Port)
class PortAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "commercial_name",
        "country",
        "status",
        "is_active",
    )
    list_filter = ("status", "is_active", "country")
    search_fields = ("code", "name", "commercial_name")
    inlines = (BerthInline, PositionInline)


@admin.register(Berth)
class BerthAdmin(admin.ModelAdmin):
    list_display = ("code", "port", "length_m", "width_m", "min_draft_m", "is_active")
    list_filter = ("port", "is_active")
    search_fields = ("code", "name", "port__code")


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "port",
        "position_type",
        "berth",
        "max_loa_m",
        "out_of_service",
        "is_projection",
        "is_active",
    )
    list_filter = ("port", "position_type", "out_of_service", "is_projection", "is_active")
    search_fields = ("code", "port__code")


@admin.register(MooringScenario)
class MooringScenarioAdmin(admin.ModelAdmin):
    list_display = ("name", "port", "vessel_count", "is_projection", "effective_from")
    list_filter = ("port", "is_projection")
    inlines = (MooringScenarioSlotInline,)


@admin.register(MooringScenarioSlot)
class MooringScenarioSlotAdmin(admin.ModelAdmin):
    list_display = ("scenario", "slot_label", "position", "max_loa_m", "sort_order")
    list_filter = ("scenario__port",)


class ShippingLineInline(admin.TabularInline):
    model = ShippingLine
    extra = 0
    fields = ("code", "name", "is_active")


class VesselInline(admin.TabularInline):
    model = Vessel
    extra = 0
    fields = ("name", "vessel_class", "loa_m", "draft_m", "pax_capacity", "is_active")
    show_change_link = True


@admin.register(ShippingLineGroup)
class ShippingLineGroupAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    search_fields = ("code", "name")
    list_filter = ("is_active",)
    inlines = (ShippingLineInline,)


@admin.register(ShippingLine)
class ShippingLineAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "group", "is_active")
    search_fields = ("code", "name", "group__name")
    list_filter = ("group", "is_active")
    inlines = (VesselInline,)


@admin.register(Vessel)
class VesselAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "shipping_line",
        "loa_m",
        "draft_m",
        "pax_capacity",
        "segment",
        "is_active",
    )
    search_fields = ("name", "shipping_line__name", "shipping_line__group__name")
    list_filter = ("shipping_line__group", "shipping_line", "segment", "is_active")
