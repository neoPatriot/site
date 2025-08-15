from django.urls import path
from . import views

app_name = 'booking'

urlpatterns = [
    path('', views.booking_view, name='booking_view'),
    path('success/', views.booking_success_view, name='booking_success'),
]
