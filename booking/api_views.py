from rest_framework import generics, views, status
from rest_framework.response import Response
from .models import Room, BookedTimeSlot, ScheduleRule
from .serializers import RoomSerializer, BookingCreateSerializer
from .telegram_sender import send_telegram_message
import datetime

class RoomListAPIView(generics.ListAPIView):
    """
    API endpoint to list all available rooms.
    """
    queryset = Room.objects.select_related('organization').prefetch_related('schedule_rules').all()
    serializer_class = RoomSerializer

class RoomDetailAPIView(generics.RetrieveAPIView):
    """
    API endpoint to get details of a specific room.
    """
    queryset = Room.objects.select_related('organization').prefetch_related('schedule_rules').all()
    serializer_class = RoomSerializer

class RoomAvailabilityAPIView(views.APIView):
    """
    API endpoint to check room availability for a specific date.
    e.g., /api/v1/rooms/1/availability/?date=2025-08-20
    """
    def get(self, request, pk):
        try:
            date_str = request.query_params.get('date')
            if not date_str:
                return Response({"error": "Query parameter 'date' is required."}, status=status.HTTP_400_BAD_REQUEST)

            booking_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
            room = Room.objects.get(pk=pk)

        except (ValueError, Room.DoesNotExist):
            return Response({"error": "Invalid date format or room not found."}, status=status.HTTP_400_BAD_REQUEST)

        day_of_week = booking_date.isoweekday()
        rules = ScheduleRule.objects.filter(room=room, day_of_week=day_of_week)

        booked_slots = BookedTimeSlot.objects.filter(
            booking__room=room,
            booking_date=booking_date,
            is_active=True
        ).values_list('time_slot', flat=True)

        available_hours = {}
        for i in range(24):
            current_time = datetime.time(i)
            time_key = f"{i:02d}:00-{(i + 1):02d}:00"

            if booking_date == datetime.date.today() and current_time < datetime.datetime.now().time():
                continue

            if time_key in booked_slots:
                continue

            for rule in rules:
                if rule.start_time <= current_time < rule.end_time:
                    available_hours[time_key] = rule.price
                    break

        return Response(available_hours)


class BookingCreateAPIView(generics.CreateAPIView):
    """
    API endpoint to create a new booking.
    """
    serializer_class = BookingCreateSerializer

    def perform_create(self, serializer):
        # The serializer's .create() method handles the transaction
        booking = serializer.save()

        # Send Telegram notification
        time_slots = serializer.validated_data['time_slots']
        booking_date = serializer.validated_data['booking_date']

        # Recalculate summary for notification from the created slots
        total_price = 0
        slots_details_list = []
        # The serializer has already created the time slots, so we can query them
        for slot in booking.time_slots.all():
            total_price += slot.price
            slots_details_list.append(f"- {slot.time_slot} ({slot.price} руб.)")

        slots_details = "\n".join(slots_details_list)

        message = (
            f"🛎 *Новая заявка (API) #{booking.id}*\n\n"
            f"*Зал:* {booking.room.title}\n"
            f"*Дата:* {booking_date.strftime('%d.%m.%Y')}\n"
            f"*Имя:* {booking.customer_name}\n"
            f"*Телефон:* {booking.customer_phone}\n\n"
            f"*Выбранные интервалы:*\n{slots_details}\n\n"
            f"*Итого:* {total_price} руб.\n"
            f"*Комментарий:* {booking.customer_comment or 'отсутствует'}"
        )
        send_telegram_message(message)
