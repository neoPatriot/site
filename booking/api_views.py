from rest_framework import generics, views, status
from rest_framework.response import Response
from .models import Room, BookedTimeSlot
from .serializers import RoomSerializer, BookingCreateSerializer
from .telegram_sender import send_telegram_message
import datetime

class RoomListAPIView(generics.ListAPIView):
    """
    API endpoint to list all available rooms.
    """
    queryset = Room.objects.select_related('organization', 'schedule').all()
    serializer_class = RoomSerializer

class RoomDetailAPIView(generics.RetrieveAPIView):
    """
    API endpoint to get details of a specific room.
    """
    queryset = Room.objects.select_related('organization', 'schedule').all()
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

        # Logic to determine available slots (similar to web view)
        try:
            schedule = room.schedule.schedule
        except Room.schedule.RelatedObjectDoesNotExist:
            return Response({"error": "Schedule not configured for this room."}, status=status.HTTP_404_NOT_FOUND)

        booked_slots = BookedTimeSlot.objects.filter(
            booking__room=room,
            booking_date=booking_date,
            is_active=True
        ).values_list('time_slot', flat=True)

        day_of_week = booking_date.isoweekday()
        available_hours = {}

        for i in range(24):
            time_key = f"{i:02d}:00-{(i+1):02d}:00"
            if time_key == "23:00-24:00": time_key = "23:00-00:00"
            schedule_key = f"{day_of_week}-{time_key}"

            if booking_date == datetime.date.today() and i < datetime.datetime.now().hour:
                continue

            price = schedule.get(schedule_key)
            if price and float(price) > 0 and time_key not in booked_slots:
                available_hours[time_key] = price

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

        # Recalculate summary for notification
        total_price = 0
        slots_details_list = []
        schedule = booking.room.schedule.schedule
        day_of_week = booking_date.isoweekday()
        for slot in time_slots:
            schedule_key = f"{day_of_week}-{slot}"
            price = float(schedule.get(schedule_key, 0))
            total_price += price
            slots_details_list.append(f"- {slot} ({price} руб.)")

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
