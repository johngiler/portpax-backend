"""
Modelos del módulo Docking/Muellaje (Fase 1).
Navieras, puertos, muelles, barcos y escalas.
"""
from django.db import models


class ShippingLine(models.Model):
    """Naviera (cliente)."""
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Naviera"
        verbose_name_plural = "Navieras"

    def __str__(self):
        return self.name or self.code or str(self.pk)


class Port(models.Model):
    """Puerto."""
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Puerto"
        verbose_name_plural = "Puertos"

    def __str__(self):
        return self.name or self.code or str(self.pk)


class Berth(models.Model):
    """Muelle o posición de atraque en un puerto."""
    port = models.ForeignKey(Port, on_delete=models.CASCADE, related_name="berths")
    name = models.CharField(max_length=255)
    capacity_pax = models.PositiveIntegerField(null=True, blank=True)
    max_draft_m = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    max_length_m = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["port", "name"]
        verbose_name = "Muelle"
        verbose_name_plural = "Muelles"

    def __str__(self):
        return f"{self.port.name} — {self.name}"


class Ship(models.Model):
    """Barco (pertenece a una naviera)."""
    shipping_line = models.ForeignKey(
        ShippingLine, on_delete=models.CASCADE, related_name="ships"
    )
    name = models.CharField(max_length=255)
    imo = models.CharField(max_length=20, blank=True)
    capacity_pax = models.PositiveIntegerField(null=True, blank=True)
    length_m = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    draft_m = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Barco"
        verbose_name_plural = "Barcos"

    def __str__(self):
        return self.name or self.imo or str(self.pk)


class Scale(models.Model):
    """Escala: un barco en un puerto (y opcionalmente en un muelle) en una fecha."""
    ship = models.ForeignKey(Ship, on_delete=models.CASCADE, related_name="scales")
    port = models.ForeignKey(Port, on_delete=models.CASCADE, related_name="scales")
    berth = models.ForeignKey(
        Berth, on_delete=models.SET_NULL, null=True, blank=True, related_name="scales"
    )
    date = models.DateField()
    pax_count = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-date", "port", "ship"]
        verbose_name = "Escala"
        verbose_name_plural = "Escalas"

    def __str__(self):
        return f"{self.ship.name} @ {self.port.name} ({self.date})"
