from django.contrib import admin
from .models import Organization, Room, ScheduleRule, Booking, BookedTimeSlot

@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'email', 'created_at')
    search_fields = ('name', 'email')
    fieldsets = (
        (None, {
            'fields': ('name', 'description', 'phone', 'email')
        }),
    )

class ScheduleRuleInline(admin.TabularInline):
    model = ScheduleRule
    extra = 1
    verbose_name_plural = 'Правила расписания'
    fields = ('day_of_week', 'start_time', 'end_time', 'price')


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('title', 'organization', 'slot_duration_minutes', 'image', 'created_at')
    list_filter = ('organization',)
    search_fields = ('title',)
    inlines = (ScheduleRuleInline,)
    fieldsets = (
        (None, {
            'fields': ('organization', 'title', 'description', 'image', 'slot_duration_minutes')
        }),
    )


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
