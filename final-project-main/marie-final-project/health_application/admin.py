from django.contrib import admin

from .models import HealthRecord, MedicalAdvice, MedicationIntakeLog, MedicationReminder, Message, Notification, Patient, Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "phone", "language_preference", "created_at")
    list_filter = ("role", "language_preference", "created_at")
    search_fields = ("user__username", "user__email", "phone")


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("full_name", "gender", "age", "status", "assigned_doctor", "user", "updated_at")
    list_filter = ("gender", "status", "created_at")
    search_fields = ("full_name", "phone", "medical_condition", "emergency_contact")


@admin.register(HealthRecord)
class HealthRecordAdmin(admin.ModelAdmin):
    list_display = ("patient", "doctor", "temperature", "blood_pressure", "heart_rate", "recorded_at")
    list_filter = ("recorded_at",)
    search_fields = ("patient__full_name", "blood_pressure", "symptoms", "notes")


@admin.register(MedicationReminder)
class MedicationReminderAdmin(admin.ModelAdmin):
    list_display = ("medicine_name", "patient", "dosage", "reminder_time", "repeat_type", "next_trigger_at", "is_active")
    list_filter = ("is_active", "repeat_type", "reminder_time")
    search_fields = ("medicine_name", "patient__full_name", "dosage")


@admin.register(MedicationIntakeLog)
class MedicationIntakeLogAdmin(admin.ModelAdmin):
    list_display = ("reminder", "patient", "scheduled_for", "status", "taken_at")
    list_filter = ("status", "scheduled_for")
    search_fields = ("reminder__medicine_name", "patient__full_name")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("subject", "sender", "recipient", "patient", "message_type", "is_read", "created_at")
    list_filter = ("message_type", "is_read", "created_at")
    search_fields = ("subject", "body", "patient__full_name")


@admin.register(MedicalAdvice)
class MedicalAdviceAdmin(admin.ModelAdmin):
    list_display = ("title", "doctor", "patient", "created_at")
    list_filter = ("created_at",)
    search_fields = ("title", "advice_text", "patient__full_name", "doctor__username")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "notification_type", "is_read", "created_at")
    list_filter = ("notification_type", "is_read", "created_at")
    search_fields = ("title", "message", "user__username")
