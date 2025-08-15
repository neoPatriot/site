from django.urls import path
from . import api_views

app_name = 'booking_api'

urlpatterns = [
    path('rooms/', api_views.RoomListAPIView.as_view(), name='room-list'),
    path('rooms/<int:pk>/', api_views.RoomDetailAPIView.as_view(), name='room-detail'),
    path('rooms/<int:pk>/availability/', api_views.RoomAvailabilityAPIView.as_view(), name='room-availability'),
    path('bookings/', api_views.BookingCreateAPIView.as_view(), name='booking-create'),
]
