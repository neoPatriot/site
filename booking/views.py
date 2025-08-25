from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.db import transaction, models
from .models import Room, Booking, BookedTimeSlot, ScheduleRule
from .forms import BookingForm
from .telegram_sender import send_telegram_message
import datetime
import calendar
from decimal import Decimal

RUSSIAN_MONTH_NAMES = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель", 5: "Май", 6: "Июнь",
    7: "Июль", 8: "Август", 9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
}

def _generate_slots(start_time, end_time, duration_minutes):
    """Генерирует список временных слотов (строк) на основе времени начала, окончания и длительности."""
    slots = []
    current_time = datetime.datetime.combine(datetime.date.today(), start_time)
    end_dt = datetime.datetime.combine(datetime.date.today(), end_time)
    duration = datetime.timedelta(minutes=duration_minutes)

    while current_time < end_dt:
        slot_end_time = current_time + duration
        if slot_end_time > end_dt:
            break
        slots.append(f"{current_time.strftime('%H:%M')}-{slot_end_time.strftime('%H:%M')}")
        current_time += duration
    return slots

def get_calendar_data(room, year, month):
    cal = calendar.Calendar()
    month_days = cal.monthdatescalendar(year, month)

    rules_for_room = ScheduleRule.objects.filter(room=room)
    rules_by_day = {rule.day_of_week: rule for rule in rules_for_room}

    booked_slots_for_month = BookedTimeSlot.objects.filter(
        booking__room=room,
        booking_date__year=year,
        booking_date__month=month,
        is_active=True
    ).values('booking_date').annotate(count=models.Count('id'))

    booked_counts = {item['booking_date']: item['count'] for item in booked_slots_for_month}

    calendar_data = []
    for week in month_days:
        week_data = []
        for day_date in week:
            rule = rules_by_day.get(day_date.isoweekday())

            if rule:
                all_possible_slots = _generate_slots(rule.start_time, rule.end_time, room.slot_duration_minutes)
                total_slots = len(all_possible_slots)
            else:
                total_slots = 0

            booked_count = booked_counts.get(day_date, 0)

            color = 'grey'
            if total_slots > 0:
                if booked_count == 0:
                    color = 'green'
                elif booked_count >= total_slots:
                    color = 'red'
                elif booked_count > total_slots / 2:
                    color = 'yellow'
                else:
                    color = 'green'

            if day_date.month != month or day_date < datetime.date.today():
                color = 'disabled'

            week_data.append({
                'date': day_date, 'day_number': day_date.day, 'color': color
            })
        calendar_data.append(week_data)

    return calendar_data

def booking_view(request):
    context = {'site_title': "«Продюсерский центр Big \"Z\"» | Бронирование"}
    room_id = request.GET.get('room')
    booking_date_str = request.GET.get('date')
    time_slots_str = request.GET.get('time')

    if not room_id:
        step = 0
        today = datetime.date.today()
        try:
            year = int(request.GET.get('year', today.year))
            month = int(request.GET.get('month', today.month))
            if datetime.date(year, month, 1) < datetime.date(today.year, today.month, 1):
                year, month = today.year, today.month
        except (ValueError, TypeError):
            year, month = today.year, today.month

        next_month_date = (datetime.date(year, month, 1) + datetime.timedelta(days=32)).replace(day=1)
        prev_month_date = (datetime.date(year, month, 1) - datetime.timedelta(days=1)).replace(day=1)
        show_prev_button = datetime.date(year, month, 1) > datetime.date(today.year, today.month, 1)

        rooms_with_calendars = []
        for room in Room.objects.all():
            rooms_with_calendars.append({
                'room': room, 'calendar': get_calendar_data(room, year, month)
            })

        context.update({
            'step': step, 'page_title': "Выберите зал и дату",
            'rooms_data': rooms_with_calendars,
            'calendar_month_name': RUSSIAN_MONTH_NAMES.get(month, ""), 'calendar_year': year,
            'next_month': next_month_date.month, 'next_year': next_month_date.year,
            'prev_month': prev_month_date.month, 'prev_year': prev_month_date.year,
            'show_prev_button': show_prev_button,
        })
        return render(request, 'booking/booking.html', context)

    room = get_object_or_404(Room, id=room_id)
    context.update({'room': room})

    if room_id and booking_date_str and not time_slots_str:
        step = 2
        booking_date = datetime.datetime.strptime(booking_date_str, '%Y-%m-%d').date()
        rule = ScheduleRule.objects.filter(room=room, day_of_week=booking_date.isoweekday()).first()
        booked_slots = BookedTimeSlot.objects.filter(
            booking__room=room, booking_date=booking_date, is_active=True
        ).values_list('time_slot', flat=True)

        available_hours = {}
        if rule:
            all_slots = _generate_slots(rule.start_time, rule.end_time, room.slot_duration_minutes)
            slot_price = (rule.price / Decimal(60.0)) * Decimal(room.slot_duration_minutes)

            for slot_key in all_slots:
                start_time_str = slot_key.split('-')[0]
                slot_start_time = datetime.datetime.strptime(start_time_str, '%H:%M').time()
                if booking_date == datetime.date.today() and slot_start_time < datetime.datetime.now().time():
                    continue
                if slot_key not in booked_slots:
                    available_hours[slot_key] = slot_price.quantize(Decimal("0.01"))

        context.update({
            'step': step, 'booking_date': booking_date,
            'available_hours': available_hours, 'page_title': f"{room.title} - Выберите время",
        })
        return render(request, 'booking/booking.html', context)

    if room_id and booking_date_str and time_slots_str:
        step = 3
        booking_date = datetime.datetime.strptime(booking_date_str, '%Y-%m-%d').date()
        selected_slots = time_slots_str.split(',')
        rule = ScheduleRule.objects.filter(room=room, day_of_week=booking_date.isoweekday()).first()

        booking_summary = {}
        total_price = Decimal(0)
        if rule:
            slot_price = (rule.price / Decimal(60.0)) * Decimal(room.slot_duration_minutes)
            for slot in selected_slots:
                booking_summary[slot] = slot_price.quantize(Decimal("0.01"))
                total_price += slot_price

        if request.method == 'POST':
            form = BookingForm(request.POST)
            if form.is_valid():
                try:
                    with transaction.atomic():
                        already_booked = BookedTimeSlot.objects.filter(
                            booking__room=room,
                            booking_date=booking_date,
                            time_slot__in=selected_slots,
                            is_active=True
                        ).exists()
                        if already_booked:
                            return redirect(request.path_info + f"?room={room_id}&date={booking_date_str}")

                        booking = form.save(commit=False)
                        booking.room = room
                        if request.user.is_authenticated:
                            booking.user = request.user
                        booking.save()

                        slots_to_create = []
                        for slot, price in booking_summary.items():
                            slots_to_create.append(
                                BookedTimeSlot(booking=booking, booking_date=booking_date, time_slot=slot, price=price, is_active=True)
                            )
                        BookedTimeSlot.objects.bulk_create(slots_to_create)

                        slots_details = "\n".join([f"- {s} ({p} руб.)" for s, p in booking_summary.items()])
                        message = (
                            f"🛎 *Новая заявка #{booking.id}*\n\n"
                            f"*Зал:* {booking.room.title}\n"
                            f"*Дата:* {booking_date.strftime('%d.%m.%Y')}\n"
                            f"*Имя:* {booking.customer_name}\n"
                            f"*Телефон:* {booking.customer_phone}\n\n"
                            f"*Выбранные интервалы:*\n{slots_details}\n\n"
                            f"*Итого:* {total_price:.2f} руб.\n"
                            f"*Комментарий:* {booking.customer_comment or 'отсутствует'}"
                        )
                        send_telegram_message(message)

                        return redirect(reverse('booking:booking_success'))
                except Exception:
                    pass
        else:
            initial_data = {}
            if request.user.is_authenticated:
                initial_data['customer_name'] = request.user.get_full_name() or request.user.username
            form = BookingForm(initial=initial_data)

        context.update({
            'step': step, 'booking_date': booking_date,
            'selected_slots': booking_summary, 'total_price': total_price.quantize(Decimal("0.01")),
            'form': form, 'page_title': f"{room.title} - Контактные данные",
        })
        return render(request, 'booking/booking.html', context)

    return redirect(reverse('booking:booking_view'))

def booking_success_view(request):
    context = {
        'site_title': "«Продюсерский центр Big \"Z\"» | Бронирование",
        'page_title': "Бронирование успешно завершено",
    }
    return render(request, 'booking/booking_success.html', context)

from django.contrib.auth import login, authenticate, logout
from django.conf import settings
from django.views.decorators.http import require_GET
import hmac
import hashlib

def home_view(request):
    rooms = Room.objects.all()
    context = {
        'site_title': "«Продюсерский центр Big \"Z\"»",
        'page_title': "Главная",
        'rooms': rooms,
    }
    return render(request, 'booking/home.html', context)


def login_page_view(request):
    """
    Страница для отображения виджета входа через Telegram.
    """
    if request.user.is_authenticated:
        return redirect('home')
    return render(request, 'booking/login.html')


@require_GET
def telegram_login_callback(request):
    auth_data = request.GET.dict()
    received_hash = auth_data.pop('hash', None)

    if not received_hash:
        return redirect('home')

    sorted_keys = sorted(auth_data.keys())
    data_check_string = "\n".join([f"{key}={auth_data[key]}" for key in sorted_keys])

    secret_key = hashlib.sha256(settings.TELEGRAM_BOT_TOKEN.encode()).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if calculated_hash == received_hash:
        user = authenticate(request, telegram_data=auth_data)
        if user is not None:
            login(request, user)

    return redirect('home')


def logout_view(request):
    logout(request)
    return redirect('home')
