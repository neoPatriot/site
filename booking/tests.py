from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from unittest.mock import patch
from .models import Organization, Room, ScheduleRule, Booking, BookedTimeSlot
import json
from rest_framework.test import APIClient
import datetime
from decimal import Decimal

class BookingAppTests(TestCase):

    def setUp(self):
        self.organization = Organization.objects.create(name="Test Org")
        self.room = Room.objects.create(
            organization=self.organization,
            title="Test Room",
            description="A room for testing."
        )
        self.rule = ScheduleRule.objects.create(
            room=self.room,
            day_of_week=1,
            start_time=datetime.time(10),
            end_time=datetime.time(14),
            price=Decimal("500.00")
        )
        today = datetime.date.today()
        self.next_monday = today + datetime.timedelta(days=(7 - today.weekday()))
        self.date_str = self.next_monday.strftime('%Y-%m-%d')

    def test_home_page_status_code(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)

    def test_booking_step2_availability_default_duration(self):
        url = reverse('booking:booking_view') + f'?room={self.room.id}&date={self.date_str}'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('available_hours', response.context)
        self.assertIn('10:00-11:00', response.context['available_hours'])
        self.assertEqual(response.context['available_hours']['10:00-11:00'], Decimal("500.00"))

    def test_booking_step2_availability_30_min_duration(self):
        self.room.slot_duration_minutes = 30
        self.room.save()
        url = reverse('booking:booking_view') + f'?room={self.room.id}&date={self.date_str}'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('10:00-10:30', response.context['available_hours'])
        self.assertEqual(response.context['available_hours']['10:00-10:30'], Decimal("250.00"))

    def test_booking_creation_full_process(self):
        time_slot = "11:00-12:00"
        booking_data = {'customer_name': 'Test User', 'customer_phone': '+1234567890'}
        post_url = reverse('booking:booking_view') + f'?room={self.room.id}&date={self.date_str}&time={time_slot}'
        response = self.client.post(post_url, booking_data)
        self.assertRedirects(response, reverse('booking:booking_success'))
        self.assertEqual(Booking.objects.count(), 1)
        created_slot = BookedTimeSlot.objects.first()
        self.assertEqual(created_slot.price, Decimal("500.00"))

    @patch('booking.views.send_telegram_message')
    def test_booking_creation_sends_correct_telegram_message(self, mock_send_telegram):
        time_slot = "11:00-12:00"
        booking_data = {'customer_name': 'Test User', 'customer_phone': '+1234567890'}
        post_url = reverse('booking:booking_view') + f'?room={self.room.id}&date={self.date_str}&time={time_slot}'

        self.client.post(post_url, booking_data)

        # Проверяем, что функция отправки была вызвана один раз
        self.assertEqual(mock_send_telegram.call_count, 1)

        # Получаем аргументы, с которыми была вызвана функция
        message = mock_send_telegram.call_args[0][0]

        # Проверяем, что в сообщении нет экранированных \n и цена отформатирована
        self.assertNotIn('\\n', message)
        self.assertIn('*Итого:* 500.00 руб.', message)


class BookingAPITests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.organization = Organization.objects.create(name="Test API Org")
        self.room = Room.objects.create(organization=self.organization, title="Test API Room")
        ScheduleRule.objects.create(
            room=self.room, day_of_week=1, start_time=datetime.time(9),
            end_time=datetime.time(12), price=Decimal("750.00")
        )
        ScheduleRule.objects.create(
            room=self.room, day_of_week=1, start_time=datetime.time(12),
            end_time=datetime.time(15), price=Decimal("900.00")
        )
        today = datetime.date.today()
        self.next_monday = today + datetime.timedelta(days=(7 - today.weekday()))
        self.date_str = self.next_monday.strftime('%Y-%m-%d')

    def test_room_availability_api_default_duration(self):
        url = reverse('booking_api:room-availability', kwargs={'pk': self.room.id})
        response = self.client.get(url, {'date': self.date_str})
        self.assertEqual(response.status_code, 200)
        self.assertIn("09:00-10:00", response.data)
        self.assertEqual(str(response.data["09:00-10:00"]), "750.00")
        self.assertIn("14:00-15:00", response.data)
        self.assertEqual(str(response.data["14:00-15:00"]), "900.00")

    def test_room_availability_api_30_min_duration(self):
        self.room.slot_duration_minutes = 30
        self.room.save()
        url = reverse('booking_api:room-availability', kwargs={'pk': self.room.id})
        response = self.client.get(url, {'date': self.date_str})
        self.assertEqual(response.status_code, 200)
        self.assertIn("09:00-09:30", response.data)
        self.assertEqual(str(response.data["09:00-09:30"]), "375.00")
        self.assertIn("12:00-12:30", response.data)
        self.assertEqual(str(response.data["12:00-12:30"]), "450.00")

    def test_create_booking_api_30_min_slots(self):
        self.room.slot_duration_minutes = 30
        self.room.save()
        url = reverse('booking_api:booking-create')
        payload = {
            "room": self.room.id, "booking_date": self.date_str,
            "time_slots": ["10:00-10:30", "14:30-15:00"],
            "customer_name": "API User 30min", "customer_phone": "123",
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, 201)
        booking = Booking.objects.first()
        slot1 = booking.time_slots.get(time_slot="10:00-10:30")
        slot2 = booking.time_slots.get(time_slot="14:30-15:00")
        self.assertEqual(slot1.price, Decimal("375.00"))
        self.assertEqual(slot2.price, Decimal("450.00"))

    def test_create_booking_api_authenticated_user(self):
        test_user = User.objects.create_user(username='testuser', password='password')
        self.client.force_authenticate(user=test_user)
        url = reverse('booking_api:booking-create')
        payload = {
            "room": self.room.id, "booking_date": self.date_str,
            "time_slots": ["10:00-11:00"],
            "customer_name": "This should be ignored", "customer_phone": "111222333",
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, 201)
        booking = Booking.objects.first()
        self.assertEqual(booking.user, test_user)
        self.assertEqual(booking.customer_name, test_user.username)
