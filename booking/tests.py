from django.test import TestCase
from django.urls import reverse
from .models import Organization, Room, ScheduleRule, Booking, BookedTimeSlot
import json
from rest_framework.test import APIClient
import datetime
from decimal import Decimal

class BookingAppTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(name="Test Org")
        cls.room = Room.objects.create(
            organization=cls.organization,
            title="Test Room",
            description="A room for testing."
        )
        # Create a schedule rule for Monday from 10:00 to 14:00 at 500/hr
        cls.rule = ScheduleRule.objects.create(
            room=cls.room,
            day_of_week=1,  # Monday
            start_time=datetime.time(10),
            end_time=datetime.time(14),
            price=Decimal("500.00")
        )
        # Determine the next Monday for testing
        today = datetime.date.today()
        cls.next_monday = today + datetime.timedelta(days=(7 - today.weekday()))
        cls.date_str = cls.next_monday.strftime('%Y-%m-%d')

    def test_home_page_status_code(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)

    def test_booking_step2_availability(self):
        # Test that the availability view shows correct slots
        url = reverse('booking:booking_view') + f'?room={self.room.id}&date={self.date_str}'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('available_hours', response.context)
        # Our rule is from 10:00 to 14:00
        self.assertIn('10:00-11:00', response.context['available_hours'])
        self.assertIn('13:00-14:00', response.context['available_hours'])
        self.assertNotIn('09:00-10:00', response.context['available_hours'])
        self.assertNotIn('14:00-15:00', response.context['available_hours'])
        self.assertEqual(response.context['available_hours']['10:00-11:00'], Decimal("500.00"))


    def test_model_str_representation(self):
        self.assertEqual(str(self.organization), "Test Org")
        self.assertEqual(str(self.room), "Test Room")
        expected_str = f"Правило для {self.room.title}: Понедельник 10:00:00-14:00:00"
        self.assertEqual(str(self.rule), expected_str)

    def test_booking_creation_full_process(self):
        time_slot = "11:00-12:00"
        booking_data = {
            'customer_name': 'Test User',
            'customer_phone': '+1234567890',
            'customer_comment': 'Test comment',
        }
        post_url = reverse('booking:booking_view') + f'?room={self.room.id}&date={self.date_str}&time={time_slot}'
        response = self.client.post(post_url, booking_data)

        self.assertRedirects(response, reverse('booking:booking_success'))

        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(BookedTimeSlot.objects.count(), 1)
        created_slot = BookedTimeSlot.objects.first()
        self.assertEqual(created_slot.time_slot, time_slot)
        # Check that the price was correctly applied from the rule
        self.assertEqual(created_slot.price, Decimal("500.00"))


class BookingAPITests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.client = APIClient()
        cls.organization = Organization.objects.create(name="Test API Org")
        cls.room = Room.objects.create(
            organization=cls.organization,
            title="Test API Room"
        )
        # Rule for Monday from 09:00 to 12:00 at 750/hr
        ScheduleRule.objects.create(
            room=cls.room, day_of_week=1,
            start_time=datetime.time(9), end_time=datetime.time(12),
            price=Decimal("750.00")
        )
        # Rule for Monday from 12:00 to 15:00 at 900/hr
        ScheduleRule.objects.create(
            room=cls.room, day_of_week=1,
            start_time=datetime.time(12), end_time=datetime.time(15),
            price=Decimal("900.00")
        )
        today = datetime.date.today()
        cls.next_monday = today + datetime.timedelta(days=(7 - today.weekday()))
        cls.date_str = cls.next_monday.strftime('%Y-%m-%d')

    def test_list_rooms_api(self):
        url = reverse('booking_api:room-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # Находим данные конкретного зала, созданного в этом тесте
        test_room_data = next((item for item in response.data if item['id'] == self.room.id), None)

        # Убедимся, что зал найден в ответе API
        self.assertIsNotNone(test_room_data, "Зал, созданный в тесте, не найден в ответе API")

        # Теперь проводим проверки для конкретного зала
        self.assertEqual(test_room_data['title'], self.room.title)
        self.assertIn('schedule_rules', test_room_data)
        self.assertEqual(len(test_room_data['schedule_rules']), 2)

    def test_room_availability_api(self):
        url = reverse('booking_api:room-availability', kwargs={'pk': self.room.id})
        response = self.client.get(url, {'date': self.date_str})
        self.assertEqual(response.status_code, 200)
        self.assertIn("09:00-10:00", response.data)
        # In the test client, the data might be a raw Decimal, not a string.
        # We compare it as a string to match the final JSON output.
        self.assertEqual(str(response.data["09:00-10:00"]), "750.00")
        self.assertIn("14:00-15:00", response.data)
        self.assertEqual(str(response.data["14:00-15:00"]), "900.00")
        self.assertNotIn("08:00-09:00", response.data)
        self.assertNotIn("15:00-16:00", response.data)

    def test_create_booking_api_success(self):
        url = reverse('booking_api:booking-create')
        payload = {
            "room": self.room.id,
            "booking_date": self.date_str,
            "time_slots": ["10:00-11:00", "12:00-13:00"], # One from each rule
            "customer_name": "API User",
            "customer_phone": "9876543210",
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(BookedTimeSlot.objects.count(), 2)

        booking = Booking.objects.first()
        slot1 = booking.time_slots.get(time_slot="10:00-11:00")
        slot2 = booking.time_slots.get(time_slot="12:00-13:00")
        self.assertEqual(slot1.price, Decimal("750.00"))
        self.assertEqual(slot2.price, Decimal("900.00"))

    def test_create_booking_api_slot_taken(self):
        # Pre-book a slot
        booking = Booking.objects.create(room=self.room, customer_name="First", customer_phone="1")
        BookedTimeSlot.objects.create(
            booking=booking, booking_date=self.next_monday,
            time_slot="11:00-12:00", price="750.00"
        )

        # Then, try to book the same slot
        url = reverse('booking_api:booking-create')
        payload = {
            "room": self.room.id, "booking_date": self.date_str,
            "time_slots": ["11:00-12:00"],
            "customer_name": "Second User", "customer_phone": "2",
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn("уже заняты", str(response.data))

    def test_create_booking_api_invalid_slot(self):
        # Try to book a slot that is not in any rule
        url = reverse('booking_api:booking-create')
        payload = {
            "room": self.room.id, "booking_date": self.date_str,
            "time_slots": ["08:00-09:00"], # This slot is not in the schedule
            "customer_name": "Invalid User", "customer_phone": "3",
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn("недоступен для бронирования", str(response.data))
