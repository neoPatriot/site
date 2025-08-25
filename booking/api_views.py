from rest_framework import generics, views, status
from rest_framework.response import Response
from .models import Room, BookedTimeSlot, ScheduleRule
from .serializers import RoomSerializer, BookingCreateSerializer
from .telegram_sender import send_telegram_message
import datetime
from decimal import Decimal
from .views import _generate_slots

class RoomListAPIView(generics.ListAPIView):
    queryset = Room.objects.select_related('organization').prefetch_related('schedule_rules').all()
    serializer_class = RoomSerializer

class RoomDetailAPIView(generics.RetrieveAPIView):
    queryset = Room.objects.select_related('organization').prefetch_related('schedule_rules').all()
    serializer_class = RoomSerializer

class RoomAvailabilityAPIView(views.APIView):
    def get(self, request, pk):
        try:
            date_str = request.query_params.get('date')
            if not date_str:
                return Response({"error": "Query parameter 'date' is required."}, status=status.HTTP_400_BAD_REQUEST)
            booking_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
            room = Room.objects.get(pk=pk)
        except (ValueError, Room.DoesNotExist):
            return Response({"error": "Invalid date format or room not found."}, status=status.HTTP_400_BAD_REQUEST)

        rules = ScheduleRule.objects.filter(room=room, day_of_week=booking_date.isoweekday())
        booked_slots = BookedTimeSlot.objects.filter(
            booking__room=room, booking_date=booking_date, is_active=True
        ).values_list('time_slot', flat=True)

        available_hours = {}
        for rule in rules:
            all_slots = _generate_slots(rule.start_time, rule.end_time, room.slot_duration_minutes)
            slot_price = (rule.price / Decimal(60.0)) * Decimal(room.slot_duration_minutes)

            for slot_key in all_slots:
                start_time_str = slot_key.split('-')[0]
                slot_start_time = datetime.datetime.strptime(start_time_str, '%H:%M').time()
                if booking_date == datetime.date.today() and slot_start_time < datetime.datetime.now().time():
                    continue
                if slot_key not in booked_slots:
                    available_hours[slot_key] = slot_price.quantize(Decimal("0.01"))

        return Response(available_hours)


class BookingCreateAPIView(generics.CreateAPIView):
    serializer_class = BookingCreateSerializer

    def perform_create(self, serializer):
        if self.request.user.is_authenticated:
            booking = serializer.save(user=self.request.user)
        else:
            booking = serializer.save()

        total_price = sum(slot.price for slot in booking.time_slots.all())
        slots_details = "\n".join([f"- {slot.time_slot} ({slot.price} руб.)" for slot in booking.time_slots.all()])

        message = (
            f"🛎 *Новая заявка (API) #{booking.id}*\n\n"
            f"*Зал:* {booking.room.title}\n"
            f"*Дата:* {booking.time_slots.first().booking_date.strftime('%d.%m.%Y')}\n"
            f"*Имя:* {booking.customer_name}\n"
            f"*Телефон:* {booking.customer_phone}\n\n"
            f"*Выбранные интервалы:*\n{slots_details}\n\n"
            f"*Итого:* {total_price} руб.\n"
            f"*Комментарий:* {booking.customer_comment or 'отсутствует'}"
        )
        send_telegram_message(message)
