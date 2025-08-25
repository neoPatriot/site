from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.db import transaction
from .models import Room, Booking, BookedTimeSlot, ScheduleRule
from .forms import BookingForm
from .telegram_sender import send_telegram_message
import datetime
import calendar
from django.db.models import Count

RUSSIAN_MONTH_NAMES = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель", 5: "Май", 6: "Июнь",
    7: "Июль", 8: "Август", 9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
}

def get_calendar_data(room, year, month):
    """
    Подготавливает данные для рендеринга календаря на месяц для конкретного зала.
    """
    cal = calendar.Calendar()
    month_days = cal.monthdatescalendar(year, month)

    rules_for_room = ScheduleRule.objects.filter(room=room)
    rules_by_day = {rule.day_of_week: rule for rule in rules_for_room}

    booked_slots_for_month = BookedTimeSlot.objects.filter(
        booking__room=room,
        booking_date__year=year,
        booking_date__month=month,
        is_active=True
    ).values('booking_date').annotate(count=Count('id'))

    booked_counts = {item['booking_date']: item['count'] for item in booked_slots_for_month}

    calendar_data = []
    for week in month_days:
        week_data = []
        for day_date in week:
            rule = rules_by_day.get(day_date.isoweekday())
            total_slots = int(rule.end_time.hour - rule.start_time.hour) if rule else 0
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
                'date': day_date,
                'day_number': day_date.day,
                'color': color
            })
        calendar_data.append(week_data)

    return calendar_data


def booking_view(request):
    context = {
        'site_title': "«Продюсерский центр Big \"Z\"» | Бронирование",
    }

    room_id = request.GET.get('room')
    booking_date_str = request.GET.get('date')
    time_slots_str = request.GET.get('time')

    # Шаг 0: Показываем все залы с их календарями
    if not room_id:
        step = 0
        today = datetime.date.today()

        try:
            year = int(request.GET.get('year', today.year))
            month = int(request.GET.get('month', today.month))
            # Не даем уйти в прошлое дальше текущего месяца
            if datetime.date(year, month, 1) < datetime.date(today.year, today.month, 1):
                year, month = today.year, today.month
        except (ValueError, TypeError):
            year, month = today.year, today.month

        # Расчет следующего месяца
        next_month_date = (datetime.date(year, month, 1) + datetime.timedelta(days=32)).replace(day=1)
        next_month = next_month_date.month
        next_year = next_month_date.year

        # Расчет предыдущего месяца
        prev_month_date = (datetime.date(year, month, 1) - datetime.timedelta(days=1)).replace(day=1)
        prev_month = prev_month_date.month
        prev_year = prev_month_date.year

        show_prev_button = datetime.date(year, month, 1) > datetime.date(today.year, today.month, 1)

        rooms = Room.objects.all()
        rooms_with_calendars = []
        for room in rooms:
            calendar_data = get_calendar_data(room, year, month)
            rooms_with_calendars.append({
                'room': room,
                'calendar': calendar_data
            })

        month_name = RUSSIAN_MONTH_NAMES.get(month, "")

        context.update({
            'step': step,
            'page_title': "Выберите зал и дату",
            'rooms_data': rooms_with_calendars,
            'calendar_month_name': month_name,
            'calendar_year': year,
            'next_month': next_month,
            'next_year': next_year,
            'prev_month': prev_month,
            'prev_year': prev_year,
            'show_prev_button': show_prev_button,
        })
        return render(request, 'booking/booking.html', context)

    # Если выбран зал, переходим к следующим шагам
    room = get_object_or_404(Room, id=room_id)
    context.update({'room': room})

    # Шаг 2: Выбрана дата, показываем доступные временные слоты
    if room_id and booking_date_str and not time_slots_str:
        step = 2
        booking_date = datetime.datetime.strptime(booking_date_str, '%Y-%m-%d').date()
        day_of_week = booking_date.isoweekday()
        rules = ScheduleRule.objects.filter(room=room, day_of_week=day_of_week)
        booked_slots = BookedTimeSlot.objects.filter(
            booking__room=room, booking_date=booking_date, is_active=True
        ).values_list('time_slot', flat=True)

        available_hours = {}
        for i in range(24):
            current_time = datetime.time(i)
            time_key = f"{i:02d}:00-{(i + 1):02d}:00"

            if booking_date == datetime.date.today() and current_time < datetime.datetime.now().time():
                continue
            if time_key in booked_slots:
                continue

            for rule in rules:
                if rule.start_time <= current_time < rule.end_time:
                    available_hours[time_key] = rule.price
                    break

        context.update({
            'step': step,
            'booking_date': booking_date,
            'available_hours': available_hours,
            'page_title': f"{room.title} - Выберите время",
        })
        return render(request, 'booking/booking.html', context)

    # Шаги 3 и 4: Выбрано время, показываем форму или обрабатываем бронь
    if room_id and booking_date_str and time_slots_str:
        step = 3
        booking_date = datetime.datetime.strptime(booking_date_str, '%Y-%m-%d').date()
        selected_slots = time_slots_str.split(',')
        day_of_week = booking_date.isoweekday()
        rules = ScheduleRule.objects.filter(room=room, day_of_week=day_of_week)

        booking_summary = {}
        total_price = 0
        for slot in selected_slots:
            price = 0
            try:
                start_hour = int(slot.split(':')[0])
                slot_time = datetime.time(start_hour)
                for rule in rules:
                    if rule.start_time <= slot_time < rule.end_time:
                        price = rule.price
                        break
            except (ValueError, IndexError):
                pass
            booking_summary[slot] = price
            total_price += price

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
                        booking.save()

                        BookedTimeSlot.objects.bulk_create([
                            BookedTimeSlot(
                                booking=booking, booking_date=booking_date,
                                time_slot=slot, price=price, is_active=True
                            ) for slot, price in booking_summary.items()
                        ])

                        slots_details = "\\n".join([f"- {s} ({p} руб.)" for s, p in booking_summary.items()])
                        message = (
                            f"🛎 *Новая заявка #{booking.id}*\\n\\n"
                            f"*Зал:* {booking.room.title}\\n"
                            f"*Дата:* {booking_date.strftime('%d.%m.%Y')}\\n"
                            f"*Имя:* {booking.customer_name}\\n"
                            f"*Телефон:* {booking.customer_phone}\\n\\n"
                            f"*Выбранные интервалы:*\\n{slots_details}\\n\\n"
                            f"*Итого:* {total_price} руб.\\n"
                            f"*Комментарий:* {booking.customer_comment or 'отсутствует'}"
                        )
                        send_telegram_message(message)

                        return redirect(reverse('booking:booking_success'))
                except Exception:
                    pass
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

    return redirect(reverse('booking:booking_view'))


def booking_success_view(request):
    context = {
        'site_title': "«Продюсерский центр Big \"Z\"» | Бронирование",
        'page_title': "Бронирование успешно завершено",
    }
    return render(request, 'booking/booking_success.html', context)


def home_view(request):
    rooms = Room.objects.all()
    context = {
        'site_title': "«Продюсерский центр Big \"Z\"»",
        'page_title': "Главная",
        'rooms': rooms,
    }
    return render(request, 'booking/home.html', context)
