from rest_framework import serializers
from .models import Room, ScheduleRule, Booking, BookedTimeSlot
from django.db import transaction
import datetime

class ScheduleRuleSerializer(serializers.ModelSerializer):
    """
    Serializer for individual schedule rules.
    """
    class Meta:
        model = ScheduleRule
        fields = ['day_of_week', 'start_time', 'end_time', 'price']


class RoomSerializer(serializers.ModelSerializer):
    """
    Serializer for reading room information.
    """
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    schedule_rules = ScheduleRuleSerializer(many=True, read_only=True)

    class Meta:
        model = Room
        fields = ['id', 'title', 'description', 'image', 'organization_name', 'schedule_rules']


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

        # Check that the requested time slots are valid according to the room's schedule
        rules = ScheduleRule.objects.filter(room=room, day_of_week=booking_date.isoweekday())
        for slot in time_slots:
            is_valid_slot = False
            try:
                start_hour = int(slot.split(':')[0])
                slot_time = datetime.time(start_hour)
                for rule in rules:
                    if rule.start_time <= slot_time < rule.end_time:
                        is_valid_slot = True
                        break
            except (ValueError, IndexError):
                # This will be caught by is_valid_slot being False
                pass

            if not is_valid_slot:
                raise serializers.ValidationError(f"Слот {slot} недоступен для бронирования по текущему расписанию.")

        # Check for existing bookings for the same slots
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
        day_of_week = booking_date.isoweekday()
        rules = ScheduleRule.objects.filter(room=room, day_of_week=day_of_week)

        try:
            with transaction.atomic():
                booking = Booking.objects.create(
                    room=room,
                    customer_name=validated_data['customer_name'],
                    customer_phone=validated_data['customer_phone'],
                    customer_comment=validated_data.get('customer_comment', ''),
                )

                slots_to_create = []
                for slot in time_slots:
                    price = 0  # Default price
                    try:
                        start_hour = int(slot.split(':')[0])
                        slot_time = datetime.time(start_hour)
                        for rule in rules:
                            if rule.start_time <= slot_time < rule.end_time:
                                price = rule.price
                                break
                    except (ValueError, IndexError):
                        pass

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

                # The view will be responsible for calculating the total price
                # for the notification message based on the created slots.
                return booking
        except Exception as e:
            raise serializers.ValidationError(f"Не удалось создать бронирование: {e}")
