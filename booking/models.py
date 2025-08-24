from django.db import models
from django.contrib.auth.models import User

class Organization(models.Model):
    """Организация, которой принадлежат залы."""
    name = models.CharField(max_length=255, verbose_name="Название организации")
    description = models.TextField(blank=True, verbose_name="Описание")
    phone = models.CharField(max_length=30, blank=True, verbose_name="Телефон")
    email = models.EmailField(blank=True, verbose_name="Email")
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
    image = models.ImageField(upload_to='room_images/', blank=True, null=True, verbose_name="Изображение")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "Зал"
        verbose_name_plural = "Залы"


class ScheduleRule(models.Model):
    """Правило для генерации слотов в расписании зала."""
    DAY_CHOICES = [
        (1, "Понедельник"),
        (2, "Вторник"),
        (3, "Среда"),
        (4, "Четверг"),
        (5, "Пятница"),
        (6, "Суббота"),
        (7, "Воскресенье"),
    ]

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='schedule_rules', verbose_name="Зал")
    day_of_week = models.IntegerField(choices=DAY_CHOICES, verbose_name="День недели")
    start_time = models.TimeField(verbose_name="Время начала")
    end_time = models.TimeField(verbose_name="Время окончания")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Цена за час")

    def __str__(self):
        return f"Правило для {self.room.title}: {self.get_day_of_week_display()} {self.start_time}-{self.end_time}"

    class Meta:
        verbose_name = "Правило расписания"
        verbose_name_plural = "Правила расписания"
        ordering = ['day_of_week', 'start_time']


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
