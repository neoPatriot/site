from django import forms
from .models import Booking

class BookingForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ['customer_name', 'customer_phone', 'customer_comment']
        widgets = {
            'customer_name': forms.TextInput(attrs={'placeholder': 'Ваше имя'}),
            'customer_phone': forms.TextInput(attrs={'placeholder': 'Ваш телефон'}),
            'customer_comment': forms.Textarea(attrs={'placeholder': 'Комментарий', 'rows': 4}),
        }
        labels = {
            'customer_name': 'Имя',
            'customer_phone': 'Телефон',
            'customer_comment': 'Комментарий',
        }
