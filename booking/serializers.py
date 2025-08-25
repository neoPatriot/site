from rest_framework import serializers
from .models import Room, ScheduleRule, Booking, BookedTimeSlot
from django.db import transaction
import datetime
from decimal import Decimal
from .views import _generate_slots

class ScheduleRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScheduleRule
        fields = ['day_of_week', 'start_time', 'end_time', 'price']


class RoomSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    schedule_rules = ScheduleRuleSerializer(many=True, read_only=True)
    slot_duration_minutes = serializers.IntegerField(read_only=True)

    class Meta:
        model = Room
        fields = ['id', 'title', 'description', 'image', 'slot_duration_minutes', 'organization_name', 'schedule_rules']


class BookingCreateSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)
    room = serializers.PrimaryKeyRelatedField(queryset=Room.objects.all())
    booking_date = serializers.DateField(write_only=True)
    time_slots = serializers.ListField(child=serializers.CharField(max_length=50), write_only=True)
    customer_name = serializers.CharField(max_length=100)
    customer_phone = serializers.CharField(max_length=20)
    customer_comment = serializers.CharField(required=False, allow_blank=True)

    def validate_booking_date(self, value):
        if value < datetime.date.today():
            raise serializers.ValidationError("Нельзя забронировать на прошедшую дату.")
        return value

    def validate(self, data):
        room = data['room']
        booking_date = data['booking_date']
        time_slots = data['time_slots']

        rules = ScheduleRule.objects.filter(room=room, day_of_week=booking_date.isoweekday())
        if not rules.exists():
            raise serializers.ValidationError("На выбранную дату нет расписания.")

        all_possible_slots = []
        for rule in rules:
            all_possible_slots.extend(_generate_slots(rule.start_time, rule.end_time, room.slot_duration_minutes))

        for slot in time_slots:
            if slot not in all_possible_slots:
                raise serializers.ValidationError(f"Слот {slot} недоступен для бронирования по текущему расписанию.")

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
        room = validated_data['room']
        booking_date = validated_data['booking_date']
        time_slots = validated_data['time_slots']

        rules = ScheduleRule.objects.filter(room=room, day_of_week=booking_date.isoweekday())

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
                    slot_start_time = datetime.datetime.strptime(slot.split('-')[0], '%H:%M').time()

                    correct_rule = None
                    for rule in rules:
                        if rule.start_time <= slot_start_time < rule.end_time:
                            correct_rule = rule
                            break

                    if not correct_rule:
                        raise serializers.ValidationError(f"Не найдено правило для слота {slot}.")

                    slot_price = (correct_rule.price / Decimal(60.0)) * Decimal(room.slot_duration_minutes)

                    slots_to_create.append(
                        BookedTimeSlot(
                            booking=booking,
                            booking_date=booking_date,
                            time_slot=slot,
                            price=slot_price.quantize(Decimal("0.01")),
                            is_active=True
                        )
                    )
                BookedTimeSlot.objects.bulk_create(slots_to_create)

                return booking
        except Exception as e:
            raise serializers.ValidationError(f"Не удалось создать бронирование: {e}")
