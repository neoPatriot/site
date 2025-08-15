from django.db import models
from django.contrib.auth.models import User

class Organization(models.Model):
    """Организация, которой принадлежат залы."""
    name = models.CharField(max_length=255, verbose_name="Название организации")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Организация"
        verbose_name_plural = "Организации"


class Room(models.Model):
    """Помещение для бронирования (зал, студия)."""
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='rooms', verbose_name="Организация")
    title = models.CharField(max_length=255, verbose_name="Название зала")
    description = models.TextField(blank=True, verbose_name="Описание")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "Зал"
        verbose_name_plural = "Залы"


class RoomSchedule(models.Model):
    """Расписание и цены для конкретного зала."""
    room = models.OneToOneField(Room, on_delete=models.CASCADE, related_name='schedule', verbose_name="Зал")
    # JSON-поле для хранения цен. Пример: {"1-09:00-10:00": 500, "1-10:00-11:00": 600, ...}
    # Где 1 - день недели (ПН), "09:00-10:00" - интервал, 500 - цена.
    schedule = models.JSONField(default=dict, verbose_name="Расписание (JSON)")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Расписание для {self.room.title}"

    class Meta:
        verbose_name = "Расписание зала"
        verbose_name_plural = "Расписания залов"


class Booking(models.Model):
    """Бронирование, созданное клиентом."""
    STATUS_CHOICES = [
        ('new', 'Новая'),
        ('confirmed', 'Подтверждена'),
        ('cancelled', 'Отменена'),
    ]

    room = models.ForeignKey(Room, on_delete=models.PROTECT, related_name='bookings', verbose_name="Зал")
    customer_name = models.CharField(max_length=100, verbose_name="Имя клиента")
    customer_phone = models.CharField(max_length=20, verbose_name="Телефон клиента")
    customer_comment = models.TextField(blank=True, verbose_name="Комментарий клиента")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='new', verbose_name="Статус")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Бронь #{self.id} на {self.room.title} от {self.customer_name}"

    class Meta:
        verbose_name = "Бронирование"
        verbose_name_plural = "Бронирования"
        ordering = ['-created_at']


class BookedTimeSlot(models.Model):
    """Конкретный забронированный временной слот."""
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='time_slots', verbose_name="Бронирование")
    booking_date = models.DateField(verbose_name="Дата бронирования")
    time_slot = models.CharField(max_length=50, verbose_name="Временной слот") # e.g., "09:00-10:00"
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Цена")
    is_active = models.BooleanField(default=True, verbose_name="Активен")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Слот {self.time_slot} на {self.booking_date} для брони #{self.booking.id}"

    class Meta:
        verbose_name = "Забронированный слот"
        verbose_name_plural = "Забронированные слоты"
        unique_together = ('booking_date', 'time_slot', 'booking')
