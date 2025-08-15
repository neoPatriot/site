from django.test import TestCase
from django.urls import reverse
from .models import Organization, Room, RoomSchedule, Booking, BookedTimeSlot
import json
from rest_framework.test import APIClient
import datetime

class BookingAppTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        # Создаем данные один раз для всех тестов в классе
        cls.organization = Organization.objects.create(name="Test Org")
        cls.room = Room.objects.create(
            organization=cls.organization,
            title="Test Room",
            description="A room for testing."
        )
        # Создаем расписание для комнаты
        # 1-ПН, 2-ВТ, ..., 7-ВС
        schedule_data = {
            "1-10:00-11:00": "500.00",
            "1-11:00-12:00": "600.00",
        }
        cls.schedule = RoomSchedule.objects.create(room=cls.room, schedule=schedule_data)

    def test_home_page_status_code(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)

    def test_about_page_status_code(self):
        response = self.client.get(reverse('about'))
        self.assertEqual(response.status_code, 200)

    def test_booking_step0_room_list_status_code(self):
        response = self.client.get(reverse('booking:booking_view'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.room.title)

    def test_model_str_representation(self):
        self.assertEqual(str(self.organization), "Test Org")
        self.assertEqual(str(self.room), "Test Room")
        self.assertEqual(str(self.schedule), f"Расписание для {self.room.title}")

    def test_booking_creation_full_process(self):
        # Шаг 0: Заходим на страницу бронирования
        response = self.client.get(reverse('booking:booking_view'))
        self.assertEqual(response.status_code, 200)

        # Шаг 1: Выбираем комнату (в нашем случае она одна)
        # Шаг 2: Выбираем дату
        import datetime
        # Выбираем следующий понедельник, чтобы расписание точно работало
        today = datetime.date.today()
        next_monday = today + datetime.timedelta(days=(7 - today.weekday()))
        date_str = next_monday.strftime('%Y-%m-%d')

        # Шаг 3: Выбираем время
        time_slot = "10:00-11:00"

        # Шаг 4: Отправляем форму с контактными данными
        booking_data = {
            'customer_name': 'Test User',
            'customer_phone': '+1234567890',
            'customer_comment': 'Test comment',
        }

        # Полный URL для POST-запроса
        post_url = reverse('booking:booking_view') + f'?room={self.room.id}&date={date_str}&time={time_slot}'

        response = self.client.post(post_url, booking_data)

        # Проверяем, что нас перенаправило на страницу успеха
        self.assertRedirects(response, reverse('booking:booking_success'))

        # Проверяем, что бронирование создано в базе данных
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(BookedTimeSlot.objects.count(), 1)

        created_booking = Booking.objects.first()
        self.assertEqual(created_booking.customer_name, 'Test User')
        self.assertEqual(created_booking.room, self.room)

        created_slot = BookedTimeSlot.objects.first()
        self.assertEqual(created_slot.booking, created_booking)
        self.assertEqual(created_slot.time_slot, time_slot)
        self.assertEqual(created_slot.booking_date, next_monday)


class BookingAPITests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.client = APIClient()
        cls.organization = Organization.objects.create(name="Test API Org")
        cls.room = Room.objects.create(
            organization=cls.organization,
            title="Test API Room",
            description="A room for API testing."
        )
        cls.schedule_data = {
            "1-10:00-11:00": "700.00",
            "1-11:00-12:00": "800.00",
        }
        cls.schedule = RoomSchedule.objects.create(room=cls.room, schedule=cls.schedule_data)

        # Determine next Monday for testing
        today = datetime.date.today()
        cls.next_monday = today + datetime.timedelta(days=(7 - today.weekday()))
        cls.date_str = cls.next_monday.strftime('%Y-%m-%d')

    def test_list_rooms_api(self):
        url = reverse('booking_api:room-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['title'], self.room.title)

    def test_room_availability_api(self):
        url = reverse('booking_api:room-availability', kwargs={'pk': self.room.id})
        response = self.client.get(url, {'date': self.date_str})
        self.assertEqual(response.status_code, 200)
        self.assertIn("10:00-11:00", response.data)
        self.assertEqual(response.data["10:00-11:00"], "700.00")

    def test_create_booking_api_success(self):
        url = reverse('booking_api:booking-create')
        payload = {
            "room": self.room.id,
            "booking_date": self.date_str,
            "time_slots": ["10:00-11:00"],
            "customer_name": "API User",
            "customer_phone": "9876543210",
            "customer_comment": "Via API"
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(BookedTimeSlot.objects.count(), 1)
        self.assertEqual(Booking.objects.first().customer_name, "API User")

    def test_create_booking_api_slot_taken(self):
        # First, create a booking to occupy a slot
        BookedTimeSlot.objects.create(
            booking=Booking.objects.create(room=self.room, customer_name="First", customer_phone="1"),
            booking_date=self.next_monday,
            time_slot="11:00-12:00",
            price="800.00"
        )

        # Then, try to book the same slot
        url = reverse('booking_api:booking-create')
        payload = {
            "room": self.room.id,
            "booking_date": self.date_str,
            "time_slots": ["11:00-12:00"], # This slot is now taken
            "customer_name": "Second User",
            "customer_phone": "2",
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn("уже заняты", str(response.data))
