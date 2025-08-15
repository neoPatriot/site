from django.contrib import admin
from .models import Organization, Room, RoomSchedule, Booking, BookedTimeSlot

@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')

class RoomScheduleInline(admin.StackedInline):
    model = RoomSchedule
    can_delete = False
    verbose_name_plural = 'Расписание'

    fieldsets = (
        (None, {
            'fields': ('schedule',),
            'description': 'JSON-объект. Ключ: "день-часы", значение: цена. Например: {"1-09:00-10:00": 500}'
        }),
    )


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('title', 'organization', 'created_at')
    list_filter = ('organization',)
    search_fields = ('title',)
    inlines = (RoomScheduleInline,)


class BookedTimeSlotInline(admin.TabularInline):
    model = BookedTimeSlot
    extra = 0 # Не показывать пустые формы для добавления
    fields = ('booking_date', 'time_slot', 'price', 'is_active')
    readonly_fields = ('booking_date', 'time_slot', 'price')
    can_delete = False


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'room', 'customer_name', 'customer_phone', 'status', 'created_at')
    list_filter = ('status', 'room')
    search_fields = ('customer_name', 'customer_phone', 'id')
    inlines = (BookedTimeSlotInline,)
    list_display_links = ('id', 'room')

    actions = ['make_confirmed', 'make_cancelled']

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('time_slots')

    @admin.action(description='Изменить статус на "Подтверждена"')
    def make_confirmed(self, request, queryset):
        queryset.update(status='confirmed')
        for booking in queryset:
            booking.time_slots.update(is_active=True)

    @admin.action(description='Изменить статус на "Отменена"')
    def make_cancelled(self, request, queryset):
        queryset.update(status='cancelled')
        for booking in queryset:
            booking.time_slots.update(is_active=False)
