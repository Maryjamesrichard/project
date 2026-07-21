import os
from datetime import datetime, time, timedelta

from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone


class Profile(models.Model):
    ROLE_PATIENT = "PATIENT"
    ROLE_DOCTOR = "DOCTOR"
    ROLE_ADMIN = "ADMIN"
    ROLE_CHOICES = [
        (ROLE_PATIENT, "Normal User / Patient / Caregiver"),
        (ROLE_DOCTOR, "Doctor / Health Provider"),
        (ROLE_ADMIN, "Admin"),
    ]
    LANGUAGE_CHOICES = [
        ("en", "English"),
        ("sw", "Kiswahili"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_PATIENT)
    phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    language_preference = models.CharField(max_length=20, choices=LANGUAGE_CHOICES, default="en")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self):
        return f"{self.user.get_username()} ({self.get_role_display()})"


class Patient(models.Model):
    GENDER_CHOICES = [
        ("Female", "Female"),
        ("Male", "Male"),
        ("Other", "Other"),
    ]
    STATUS_CHOICES = [
        ("Stable", "Stable"),
        ("Needs Attention", "Needs Attention"),
        ("Critical", "Critical"),
        ("Recovering", "Recovering"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="owned_patients")
    full_name = models.CharField(max_length=150)
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES)
    age = models.PositiveIntegerField()
    phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    medical_condition = models.CharField(max_length=200, blank=True)
    emergency_contact = models.CharField(max_length=150, blank=True)
    assigned_doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_patients",
    )
    status = models.CharField(max_length=40, choices=STATUS_CHOICES, default="Stable")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name


class HealthRecord(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="health_records")
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="health_records",
    )
    temperature = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    blood_pressure = models.CharField(max_length=30, blank=True)
    heart_rate = models.PositiveIntegerField(null=True, blank=True)
    symptoms = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at"]

    def __str__(self):
        return f"Health record for {self.patient} on {self.recorded_at:%Y-%m-%d}"


class MedicationReminder(models.Model):
    REPEAT_ONCE = "once"
    REPEAT_DAILY = "daily"
    REPEAT_WEEKLY = "weekly"
    REPEAT_CUSTOM = "custom"
    REPEAT_CHOICES = [
        (REPEAT_ONCE, "Once"),
        (REPEAT_DAILY, "Daily"),
        (REPEAT_WEEKLY, "Weekly"),
        (REPEAT_CUSTOM, "Custom days"),
    ]

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="reminders")
    medicine_name = models.CharField(max_length=150)
    dosage = models.CharField(max_length=100)
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(null=True, blank=True)
    number_of_days = models.PositiveIntegerField(null=True, blank=True)
    reminder_time = models.TimeField()
    repeat_type = models.CharField(max_length=20, choices=REPEAT_CHOICES, default=REPEAT_DAILY)
    days_of_week = models.JSONField(default=list, blank=True)
    instructions = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    next_trigger_at = models.DateTimeField(null=True, blank=True)
    last_triggered_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_medication_reminders",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["next_trigger_at", "reminder_time", "medicine_name"]

    def __str__(self):
        return f"{self.medicine_name} for {self.patient}"

    def get_effective_end_date(self):
        if self.end_date:
            return self.end_date
        if self.number_of_days:
            return self.start_date + timedelta(days=self.number_of_days - 1)
        return None

    def calculate_next_trigger_at(self, after=None):
        if not self.is_active:
            return None
        after = after or timezone.now()
        current_date = max(self.start_date, timezone.localdate(after))
        end_date = self.get_effective_end_date()
        allowed_days = {int(day) for day in (self.days_of_week or []) if str(day).isdigit()}

        for offset in range(0, 370):
            candidate_date = current_date + timedelta(days=offset)
            if end_date and candidate_date > end_date:
                return None
            if self.repeat_type == self.REPEAT_ONCE and candidate_date != self.start_date:
                return None
            if self.repeat_type == self.REPEAT_WEEKLY and candidate_date.weekday() != self.start_date.weekday():
                continue
            if self.repeat_type == self.REPEAT_CUSTOM and allowed_days and candidate_date.weekday() not in allowed_days:
                continue
            candidate = timezone.make_aware(datetime.combine(candidate_date, self.reminder_time))
            if candidate > after:
                return candidate
        return None

    def refresh_next_trigger(self, after=None, save=True):
        self.next_trigger_at = self.calculate_next_trigger_at(after=after)
        if save:
            self.save(update_fields=["next_trigger_at"])
        return self.next_trigger_at


class MedicationIntakeLog(models.Model):
    STATUS_TAKEN = "taken"
    STATUS_MISSED = "missed"
    STATUS_PENDING = "pending"
    STATUS_CHOICES = [
        (STATUS_TAKEN, "Taken"),
        (STATUS_MISSED, "Missed"),
        (STATUS_PENDING, "Pending"),
    ]

    reminder = models.ForeignKey(MedicationReminder, on_delete=models.CASCADE, related_name="intake_logs")
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="medication_intake_logs")
    scheduled_for = models.DateTimeField()
    taken_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-scheduled_for"]
        constraints = [
            models.UniqueConstraint(fields=["reminder", "scheduled_for"], name="unique_reminder_scheduled_intake")
        ]

    def __str__(self):
        return f"{self.reminder.medicine_name} {self.status} at {self.scheduled_for:%Y-%m-%d %H:%M}"


def voice_upload_path(instance, filename):
    name = os.path.basename(filename)
    return f"voice_messages/user_{instance.sender_id or 'new'}/{name}"


def advice_voice_upload_path(instance, filename):
    name = os.path.basename(filename)
    return f"medical_advice/doctor_{instance.doctor_id or 'new'}/{name}"


class Message(models.Model):
    TYPE_TEXT = "TEXT"
    TYPE_VOICE = "VOICE"
    TYPE_BOTH = "BOTH"
    MESSAGE_TYPE_CHOICES = [
        (TYPE_TEXT, "Text"),
        (TYPE_VOICE, "Voice"),
        (TYPE_BOTH, "Text and Voice"),
    ]

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_health_messages",
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_health_messages",
    )
    reply_to = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replies",
    )
    patient = models.ForeignKey(Patient, on_delete=models.SET_NULL, null=True, blank=True, related_name="messages")
    subject = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    voice_file = models.FileField(upload_to=voice_upload_path, blank=True, null=True)
    message_type = models.CharField(max_length=10, choices=MESSAGE_TYPE_CHOICES, default=TYPE_TEXT)
    is_read = models.BooleanField(default=False)
    appointment_needed = models.BooleanField(default=False)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.subject


class MedicalAdvice(models.Model):
    TYPE_TEXT = "TEXT"
    TYPE_VOICE = "VOICE"
    TYPE_BOTH = "BOTH"
    MESSAGE_TYPE_CHOICES = Message.MESSAGE_TYPE_CHOICES

    doctor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="medical_advice_sent")
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="medical_advice")
    source_message = models.ForeignKey(Message, on_delete=models.SET_NULL, null=True, blank=True, related_name="medical_advice")
    title = models.CharField(max_length=200)
    advice_text = models.TextField(blank=True)
    voice_file = models.FileField(upload_to=advice_voice_upload_path, blank=True, null=True)
    message_type = models.CharField(max_length=10, choices=MESSAGE_TYPE_CHOICES, default=TYPE_TEXT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=150)
    message = models.TextField()
    notification_type = models.CharField(max_length=50, blank=True)
    related_message = models.ForeignKey(Message, on_delete=models.SET_NULL, null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_profile(sender, instance, created, **kwargs):
    if created:
        role = Profile.ROLE_ADMIN if instance.is_superuser or instance.is_staff else Profile.ROLE_PATIENT
        Profile.objects.create(user=instance, role=role)
    elif hasattr(instance, "profile") and (instance.is_superuser or instance.is_staff):
        if instance.profile.role != Profile.ROLE_ADMIN:
            instance.profile.role = Profile.ROLE_ADMIN
            instance.profile.save(update_fields=["role"])
