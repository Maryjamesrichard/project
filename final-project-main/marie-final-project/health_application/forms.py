import os

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import HealthRecord, MedicalAdvice, MedicationReminder, Message, Patient, Profile


AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".webm", ".ogg"}
AUDIO_CONTENT_TYPES = {
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/mp4",
    "audio/x-m4a",
    "audio/webm",
    "audio/ogg",
    "application/ogg",
}
MAX_AUDIO_SIZE = 10 * 1024 * 1024


class BootstrapFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxSelectMultiple):
                widget.attrs.setdefault("class", "d-flex flex-wrap gap-3")
            elif isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", "form-select")
            elif isinstance(widget, forms.FileInput):
                widget.attrs.setdefault("class", "form-control")
                widget.attrs.setdefault("accept", "audio/mpeg,audio/wav,audio/mp4,audio/x-m4a,audio/webm,audio/ogg,.mp3,.wav,.m4a,.webm,.ogg")
            else:
                widget.attrs.setdefault("class", "form-control")


def validate_audio_file(file_obj):
    if not file_obj:
        return
    extension = os.path.splitext(file_obj.name.lower())[1]
    if extension not in AUDIO_EXTENSIONS:
        raise forms.ValidationError("Record audio in mp3, wav, m4a, webm, or ogg format.")
    if file_obj.size > MAX_AUDIO_SIZE:
        raise forms.ValidationError("Audio must be 10MB or smaller.")
    content_type = getattr(file_obj, "content_type", "")
    if content_type and content_type not in AUDIO_CONTENT_TYPES and not content_type.startswith("audio/"):
        raise forms.ValidationError("The recorded file must be an audio file.")


class RegisterForm(BootstrapFormMixin, UserCreationForm):
    ROLE_CHOICES = [
        (Profile.ROLE_PATIENT, "Normal User / Patient / Caregiver"),
        (Profile.ROLE_DOCTOR, "Doctor / Health Provider"),
    ]

    email = forms.EmailField(required=True)
    role = forms.ChoiceField(choices=ROLE_CHOICES)
    phone = forms.CharField(required=False)
    address = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
    language_preference = forms.ChoiceField(choices=Profile.LANGUAGE_CHOICES)

    class Meta:
        model = User
        fields = ["username", "email", "role", "phone", "address", "language_preference", "password1", "password2"]

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
            profile = user.profile
            profile.role = self.cleaned_data["role"]
            profile.phone = self.cleaned_data.get("phone", "")
            profile.address = self.cleaned_data.get("address", "")
            profile.language_preference = self.cleaned_data["language_preference"]
            profile.save()
        return user


class ProfileForm(BootstrapFormMixin, forms.ModelForm):
    email = forms.EmailField(required=False)
    first_name = forms.CharField(required=False)
    last_name = forms.CharField(required=False)

    class Meta:
        model = Profile
        fields = ["first_name", "last_name", "email", "phone", "address", "language_preference"]
        widgets = {"address": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        super().__init__(*args, **kwargs)
        self.fields["email"].initial = self.user.email
        self.fields["first_name"].initial = self.user.first_name
        self.fields["last_name"].initial = self.user.last_name

    def save(self, commit=True):
        profile = super().save(commit=False)
        self.user.email = self.cleaned_data.get("email", "")
        self.user.first_name = self.cleaned_data.get("first_name", "")
        self.user.last_name = self.cleaned_data.get("last_name", "")
        if commit:
            self.user.save()
            profile.save()
        return profile


class PatientForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Patient
        fields = [
            "full_name",
            "gender",
            "age",
            "phone",
            "address",
            "medical_condition",
            "emergency_contact",
            "assigned_doctor",
            "status",
        ]
        widgets = {"address": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        doctor_ids = Profile.objects.filter(role=Profile.ROLE_DOCTOR).values_list("user_id", flat=True)
        self.fields["assigned_doctor"].queryset = User.objects.filter(id__in=doctor_ids)
        self.fields["assigned_doctor"].required = False


class HealthRecordForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = HealthRecord
        fields = ["patient", "temperature", "blood_pressure", "heart_rate", "symptoms", "notes"]
        widgets = {
            "symptoms": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


class MedicationReminderForm(BootstrapFormMixin, forms.ModelForm):
    DAY_CHOICES = [
        (0, "Monday"),
        (1, "Tuesday"),
        (2, "Wednesday"),
        (3, "Thursday"),
        (4, "Friday"),
        (5, "Saturday"),
        (6, "Sunday"),
    ]

    days_of_week = forms.MultipleChoiceField(
        choices=DAY_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Use when repeat type is custom days.",
    )

    class Meta:
        model = MedicationReminder
        fields = [
            "patient",
            "medicine_name",
            "dosage",
            "instructions",
            "start_date",
            "reminder_time",
            "repeat_type",
            "days_of_week",
            "end_date",
            "number_of_days",
            "is_active",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "reminder_time": forms.TimeInput(attrs={"type": "time"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "instructions": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["days_of_week"].initial = [str(day) for day in (self.instance.days_of_week or [])]

    def clean_days_of_week(self):
        return [int(day) for day in self.cleaned_data.get("days_of_week", [])]

    def clean(self):
        cleaned = super().clean()
        repeat_type = cleaned.get("repeat_type")
        days = cleaned.get("days_of_week") or []
        end_date = cleaned.get("end_date")
        number_of_days = cleaned.get("number_of_days")
        start_date = cleaned.get("start_date")
        if repeat_type == MedicationReminder.REPEAT_CUSTOM and not days:
            self.add_error("days_of_week", "Choose at least one day for custom reminders.")
        if end_date and start_date and end_date < start_date:
            self.add_error("end_date", "End date cannot be before start date.")
        if end_date and number_of_days:
            self.add_error("number_of_days", "Use either end date or number of days, not both.")
        return cleaned


class MessageForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Message
        fields = ["patient", "subject", "message_type", "body", "voice_file"]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 4}),
            "voice_file": forms.FileInput(attrs={"class": "d-none", "accept": "audio/webm,audio/ogg,audio/wav,audio/mpeg,.webm,.ogg,.wav,.mp3"}),
        }

    def clean_voice_file(self):
        file_obj = self.cleaned_data.get("voice_file")
        validate_audio_file(file_obj)
        return file_obj

    def clean(self):
        cleaned = super().clean()
        message_type = cleaned.get("message_type")
        body = (cleaned.get("body") or "").strip()
        voice_file = cleaned.get("voice_file")
        if message_type == Message.TYPE_TEXT and not body:
            self.add_error("body", "Enter a text message.")
        if message_type == Message.TYPE_VOICE and not voice_file:
            self.add_error("voice_file", "Record a voice note before sending.")
        if message_type == Message.TYPE_BOTH:
            if not body:
                self.add_error("body", "Enter the text part of this message.")
            if not voice_file:
                self.add_error("voice_file", "Record the voice part of this message.")
        return cleaned


class MedicalAdviceForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = MedicalAdvice
        fields = ["patient", "title", "message_type", "advice_text", "voice_file"]
        widgets = {
            "advice_text": forms.Textarea(attrs={"rows": 4}),
            "voice_file": forms.FileInput(attrs={"class": "d-none", "accept": "audio/webm,audio/ogg,audio/wav,audio/mpeg,.webm,.ogg,.wav,.mp3"}),
        }

    def clean_voice_file(self):
        file_obj = self.cleaned_data.get("voice_file")
        validate_audio_file(file_obj)
        return file_obj

    def clean(self):
        cleaned = super().clean()
        message_type = cleaned.get("message_type")
        advice_text = (cleaned.get("advice_text") or "").strip()
        voice_file = cleaned.get("voice_file")
        if message_type == MedicalAdvice.TYPE_TEXT and not advice_text:
            self.add_error("advice_text", "Enter medical advice text.")
        if message_type == MedicalAdvice.TYPE_VOICE and not voice_file:
            self.add_error("voice_file", "Record voice feedback before sending.")
        if message_type == MedicalAdvice.TYPE_BOTH:
            if not advice_text:
                self.add_error("advice_text", "Enter the text part of this advice.")
            if not voice_file:
                self.add_error("voice_file", "Record the voice part of this advice.")
        return cleaned
