from rest_framework import serializers
from .models import Room, RoomSchedule, Booking, BookedTimeSlot
from django.db import transaction
import datetime

class RoomScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoomSchedule
        fields = ['schedule']

class RoomSerializer(serializers.ModelSerializer):
    """
    Serializer for reading room information.
    """
    schedule = RoomScheduleSerializer(read_only=True)
    organization_name = serializers.CharField(source='organization.name', read_only=True)

    class Meta:
        model = Room
        fields = ['id', 'title', 'description', 'image', 'organization_name', 'schedule']


class BookingCreateSerializer(serializers.Serializer):
    """
    Serializer for creating a new booking.
    """
    id = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)

    room = serializers.PrimaryKeyRelatedField(queryset=Room.objects.all())
    booking_date = serializers.DateField(write_only=True)
    time_slots = serializers.ListField(
        child=serializers.CharField(max_length=50),
        write_only=True
    )
    customer_name = serializers.CharField(max_length=100)
    customer_phone = serializers.CharField(max_length=20)
    customer_comment = serializers.CharField(required=False, allow_blank=True)

    def validate_booking_date(self, value):
        """
        Check that the booking date is not in the past.
        """
        if value < datetime.date.today():
            raise serializers.ValidationError("Нельзя забронировать на прошедшую дату.")
        return value

    def validate(self, data):
        """
        Validate that the requested time slots are available.
        """
        room = data['room']
        booking_date = data['booking_date']
        time_slots = data['time_slots']

        # Check for schedule availability and price
        try:
            schedule = room.schedule.schedule
        except Room.schedule.RelatedObjectDoesNotExist:
            raise serializers.ValidationError(f"Для зала '{room.title}' не настроено расписание.")

        day_of_week = booking_date.isoweekday()
        for slot in time_slots:
            schedule_key = f"{day_of_week}-{slot}"
            if schedule.get(schedule_key) is None or float(schedule.get(schedule_key, 0)) <= 0:
                raise serializers.ValidationError(f"Слот {slot} недоступен для бронирования в этот день.")

        # Check for existing bookings
        already_booked = BookedTimeSlot.objects.filter(
            booking__room=room,
            booking_date=booking_date,
            time_slot__in=time_slots,
            is_active=True
        ).exists()

        if already_booked:
            raise serializers.ValidationError("Один или несколько выбранных слотов уже заняты.")

        return data

    def create(self, validated_data):
        """
        Create the Booking and related BookedTimeSlot objects.
        """
        room = validated_data['room']
        booking_date = validated_data['booking_date']
        time_slots = validated_data['time_slots']
        schedule = room.schedule.schedule
        day_of_week = booking_date.isoweekday()

        try:
            with transaction.atomic():
                booking = Booking.objects.create(
                    room=room,
                    customer_name=validated_data['customer_name'],
                    customer_phone=validated_data['customer_phone'],
                    customer_comment=validated_data.get('customer_comment', ''),
                )

                slots_to_create = []
                total_price = 0
                booking_summary = {}

                for slot in time_slots:
                    schedule_key = f"{day_of_week}-{slot}"
                    price = float(schedule.get(schedule_key, 0))
                    total_price += price
                    booking_summary[slot] = price
                    slots_to_create.append(
                        BookedTimeSlot(
                            booking=booking,
                            booking_date=booking_date,
                            time_slot=slot,
                            price=price,
                            is_active=True
                        )
                    )
                BookedTimeSlot.objects.bulk_create(slots_to_create)

                # Note: Sending Telegram message should ideally be here or in a signal
                # For simplicity, we can call it from the view after serializer.save()

                return booking
        except Exception as e:
            raise serializers.ValidationError(f"Не удалось создать бронирование: {e}")
