from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.db import transaction
from .models import Room, Booking, BookedTimeSlot, RoomSchedule
from .forms import BookingForm
from .telegram_sender import send_telegram_message
import datetime

def booking_view(request):
    step = 0
    context = {
        'step': step,
        'site_title': "«Продюсерский центр Big \"Z\"» | Бронирование",
    }

    room_id = request.GET.get('room')
    booking_date_str = request.GET.get('date')
    time_slots_str = request.GET.get('time')

    # Step 0: Show all rooms
    if not room_id:
        context['rooms'] = Room.objects.all()
        return render(request, 'booking/booking.html', context)

    # From here on, a room is selected
    step = 1
    room = get_object_or_404(Room, id=room_id)
    context.update({'step': step, 'room': room})

    # Step 1: A room is selected, show calendar
    if room_id and not booking_date_str:
        today = datetime.date.today()
        # You can implement a more complex calendar generation if needed
        context.update({
            'page_title': f"{room.title} - Выберите дату",
            'today': today,
            'max_date': today + datetime.timedelta(days=30),
        })
        return render(request, 'booking/booking.html', context)

    # Step 2: Date is selected, show available time slots
    if room_id and booking_date_str and not time_slots_str:
        step = 2
        booking_date = datetime.datetime.strptime(booking_date_str, '%Y-%m-%d').date()

        # Get schedule for the room
        try:
            schedule = room.schedule.schedule
        except Room.schedule.RelatedObjectDoesNotExist:
            # Handle case where room has no schedule
            schedule = {}

        # Get booked slots for the date
        booked_slots = BookedTimeSlot.objects.filter(
            booking__room=room,
            booking_date=booking_date,
            is_active=True
        ).values_list('time_slot', flat=True)

        # Determine available slots
        day_of_week = booking_date.isoweekday() # Monday is 1 and Sunday is 7
        available_hours = {}

        # Assuming schedule keys are like "1-09:00-10:00"
        for i in range(24):
            time_key = f"{i:02d}:00-{(i+1):02d}:00"
            if time_key == "23:00-24:00": time_key = "23:00-00:00"

            schedule_key = f"{day_of_week}-{time_key}"

            # Check if today and time has passed
            if booking_date == datetime.date.today() and i < datetime.datetime.now().hour:
                continue

            price = schedule.get(schedule_key)
            if price and float(price) > 0 and time_key not in booked_slots:
                available_hours[time_key] = price

        context.update({
            'step': step,
            'booking_date': booking_date,
            'available_hours': available_hours,
            'page_title': f"{room.title} - Выберите время",
        })
        return render(request, 'booking/booking.html', context)

    # Step 3 & 4: Time is selected, show contact form (GET) or process booking (POST)
    if room_id and booking_date_str and time_slots_str:
        step = 3
        booking_date = datetime.datetime.strptime(booking_date_str, '%Y-%m-%d').date()
        selected_slots = time_slots_str.split(',')

        try:
            schedule = room.schedule.schedule
        except Room.schedule.RelatedObjectDoesNotExist:
            schedule = {}

        # Calculate total price and prepare summary
        total_price = 0
        booking_summary = {}
        day_of_week = booking_date.isoweekday()
        for slot in selected_slots:
            schedule_key = f"{day_of_week}-{slot}"
            price = schedule.get(schedule_key, 0)
            booking_summary[slot] = price
            total_price += float(price)

        if request.method == 'POST':
            form = BookingForm(request.POST)
            if form.is_valid():
                try:
                    with transaction.atomic():
                        # Final availability check
                        already_booked = BookedTimeSlot.objects.filter(
                            booking__room=room,
                            booking_date=booking_date,
                            time_slot__in=selected_slots,
                            is_active=True
                        ).exists()

                        if already_booked:
                            # Handle error - slots taken
                            # You should add a message to the user
                            return redirect(request.path_info + f"?room={room_id}&date={booking_date_str}")

                        booking = form.save(commit=False)
                        booking.room = room
                        booking.save()

                        slots_to_create = []
                        for slot, price in booking_summary.items():
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

                        # Send Telegram notification
                        slots_details = "\n".join([f"- {slot} ({price} руб.)" for slot, price in booking_summary.items()])
                        message = (
                            f"🛎 *Новая заявка #{booking.id}*\n\n"
                            f"*Зал:* {booking.room.title}\n"
                            f"*Дата:* {booking_date.strftime('%d.%m.%Y')}\n"
                            f"*Имя:* {booking.customer_name}\n"
                            f"*Телефон:* {booking.customer_phone}\n\n"
                            f"*Выбранные интервалы:*\n{slots_details}\n\n"
                            f"*Итого:* {total_price} руб.\n"
                            f"*Комментарий:* {booking.customer_comment or 'отсутствует'}"
                        )
                        send_telegram_message(message)

                        return redirect(reverse('booking:booking_success'))
                except Exception as e:
                    # Handle transaction error
                    # Log the error e
                    pass # Fall through to render form with errors
        else:
            form = BookingForm()

        context.update({
            'step': step,
            'booking_date': booking_date,
            'selected_slots': booking_summary,
            'total_price': total_price,
            'form': form,
            'page_title': f"{room.title} - Контактные данные",
        })
        return render(request, 'booking/booking.html', context)

    # Fallback redirect to the start
    return redirect(reverse('booking:booking_view'))


def booking_success_view(request):
    context = {
        'site_title': "«Продюсерский центр Big \"Z\"» | Бронирование",
        'page_title': "Бронирование успешно завершено",
    }
    return render(request, 'booking/booking_success.html', context)

def home_view(request):
    # I need to add image to room model to make this dynamic
    rooms = Room.objects.all()
    context = {
        'site_title': "«Продюсерский центр Big \"Z\"»",
        'page_title': "Главная",
        'rooms': rooms,
    }
    return render(request, 'booking/home.html', context)

def about_view(request):
    context = {
        'site_title': "«Продюсерский центр Big \"Z\"»",
        'page_title': "О нас",
    }
    return render(request, 'booking/about.html', context)
