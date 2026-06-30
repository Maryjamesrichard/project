from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.conf import settings
from django.db.models import Q
from django.http import FileResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .forms import (
    HealthRecordForm,
    MedicalAdviceForm,
    MedicationReminderForm,
    MessageForm,
    PatientForm,
    ProfileForm,
    RegisterForm,
)
from .models import HealthRecord, MedicalAdvice, MedicationIntakeLog, MedicationReminder, Message, Notification, Patient, Profile


def role_for(user):
    if user.is_superuser or user.is_staff:
        return Profile.ROLE_ADMIN
    profile, _ = Profile.objects.get_or_create(user=user)
    return profile.role


def is_admin(user):
    return role_for(user) == Profile.ROLE_ADMIN


def is_doctor(user):
    return role_for(user) == Profile.ROLE_DOCTOR


def is_caregiver(user):
    return role_for(user) == Profile.ROLE_PATIENT


def require_roles(user, *roles):
    if is_admin(user):
        return True
    return role_for(user) in roles


def visible_patients(user):
    if is_admin(user):
        return Patient.objects.all()
    if is_doctor(user):
        return Patient.objects.filter(assigned_doctor=user)
    return Patient.objects.filter(user=user)


def can_edit_patient(user, patient):
    return is_admin(user) or patient.user_id == user.id


def can_view_message(user, message_obj):
    if is_admin(user):
        return True
    if message_obj.sender_id == user.id or message_obj.recipient_id == user.id:
        return True
    return bool(message_obj.patient_id and is_doctor(user) and message_obj.patient.assigned_doctor_id == user.id)


def create_notification(user, title, message, notification_type="", related_message=None):
    return Notification.objects.create(
        user=user,
        title=title,
        message=message,
        notification_type=notification_type,
        related_message=related_message,
    )


def can_manage_reminders(user):
    return is_admin(user) or is_doctor(user)


def sync_reminder_state(reminder):
    now = timezone.now()
    if not reminder.next_trigger_at:
        reminder.refresh_next_trigger(after=now, save=True)
        return
    missed_cutoff = now - timedelta(hours=1)
    changed = False
    while reminder.next_trigger_at and reminder.next_trigger_at < missed_cutoff:
        MedicationIntakeLog.objects.get_or_create(
            reminder=reminder,
            patient=reminder.patient,
            scheduled_for=reminder.next_trigger_at,
            defaults={"status": MedicationIntakeLog.STATUS_MISSED},
        )
        reminder.last_triggered_at = reminder.next_trigger_at
        reminder.next_trigger_at = reminder.calculate_next_trigger_at(after=reminder.next_trigger_at)
        changed = True
    if changed:
        reminder.save(update_fields=["last_triggered_at", "next_trigger_at"])
    if reminder.next_trigger_at and reminder.next_trigger_at <= now:
        MedicationIntakeLog.objects.get_or_create(
            reminder=reminder,
            patient=reminder.patient,
            scheduled_for=reminder.next_trigger_at,
            defaults={"status": MedicationIntakeLog.STATUS_PENDING},
        )


def reminder_payload(reminder):
    return {
        "id": reminder.id,
        "patient": reminder.patient.full_name,
        "medicine_name": reminder.medicine_name,
        "dosage": reminder.dosage,
        "instructions": reminder.instructions,
        "next_trigger_at": reminder.next_trigger_at.isoformat() if reminder.next_trigger_at else None,
        "reminder_time": reminder.reminder_time.strftime("%H:%M"),
        "repeat_type": reminder.repeat_type,
    }


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, "Welcome back.")
            return redirect("dashboard")
        messages.error(request, "Invalid username or password.")
    return render(request, "health_application/login.html")


def register_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Account created successfully.")
        return redirect("dashboard")
    return render(request, "health_application/register.html", {"form": form})


def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect("login")


@login_required
def dashboard(request):
    role = role_for(request.user)
    patients_qs = visible_patients(request.user)
    context = {
        "role": role,
        "total_patients": patients_qs.count(),
        "total_reminders": MedicationReminder.objects.filter(patient__in=patients_qs).count(),
        "total_health_records": HealthRecord.objects.filter(patient__in=patients_qs).count(),
        "total_messages": Message.objects.filter(Q(recipient=request.user) | Q(sender=request.user)).count(),
        "recent_patients": patients_qs.order_by("-created_at")[:5],
        "active_reminders": MedicationReminder.objects.filter(patient__in=patients_qs, is_active=True).select_related("patient")[:5],
        "latest_advice": MedicalAdvice.objects.filter(patient__in=patients_qs).select_related("patient", "doctor")[:5],
        "recent_messages": Message.objects.filter(Q(recipient=request.user) | Q(sender=request.user)).select_related("sender", "recipient", "patient")[:5],
        "recent_health_records": HealthRecord.objects.filter(patient__in=patients_qs).select_related("patient", "doctor")[:5],
        "unread_messages": Message.objects.filter(recipient=request.user, is_read=False).count(),
        "pending_reviews": Message.objects.filter(recipient=request.user, reviewed_at__isnull=True).count(),
        "unread_notifications": request.user.notifications.filter(is_read=False).count(),
    }
    if role == Profile.ROLE_ADMIN:
        context.update(
            total_users=User.objects.count(),
            total_doctors=Profile.objects.filter(role=Profile.ROLE_DOCTOR).count(),
            total_all_patients=Patient.objects.count(),
            total_all_messages=Message.objects.count(),
            total_all_reminders=MedicationReminder.objects.count(),
        )
    return render(request, "health_application/dashboard.html", context)


@login_required
def patients(request):
    return render(request, "health_application/patients.html", {"patients": visible_patients(request.user)})


@login_required
def patient_detail(request, pk):
    patient = get_object_or_404(visible_patients(request.user), pk=pk)
    return render(request, "health_application/patient_detail.html", {"patient": patient})


@login_required
def patient_create(request):
    if is_doctor(request.user):
        return HttpResponseForbidden("Doctors can review assigned patients but cannot create patient records.")
    form = PatientForm(request.POST or None)
    if not is_admin(request.user) and not is_doctor(request.user):
        form.fields["assigned_doctor"].initial = None
    if request.method == "POST" and form.is_valid():
        patient = form.save(commit=False)
        patient.user = request.user
        if is_doctor(request.user) and not patient.assigned_doctor:
            patient.assigned_doctor = request.user
        patient.save()
        messages.success(request, "Patient added successfully.")
        return redirect("patients")
    return render(request, "health_application/patient_form.html", {"form": form, "page_title": "Add Patient", "button_label": "Add Patient"})


@login_required
def patient_edit(request, pk):
    patient = get_object_or_404(visible_patients(request.user), pk=pk)
    if not can_edit_patient(request.user, patient):
        return HttpResponseForbidden("You are not allowed to update this patient.")
    form = PatientForm(request.POST or None, instance=patient)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Patient updated successfully.")
        return redirect("patient_detail", pk=patient.pk)
    return render(request, "health_application/patient_form.html", {"form": form, "page_title": "Edit Patient", "button_label": "Save Changes"})


@login_required
def patient_delete(request, pk):
    patient = get_object_or_404(visible_patients(request.user), pk=pk)
    if not is_admin(request.user) and patient.user_id != request.user.id:
        return HttpResponseForbidden("You are not allowed to delete this patient.")
    if request.method == "POST":
        patient.delete()
        messages.success(request, "Patient deleted successfully.")
        return redirect("patients")
    return render(request, "health_application/404.html", status=405)


@login_required
def health_records(request):
    if not require_roles(request.user, Profile.ROLE_DOCTOR):
        return HttpResponseForbidden("Only doctors and admins can access health records.")
    patients_qs = visible_patients(request.user)
    records = HealthRecord.objects.filter(patient__in=patients_qs).select_related("patient", "doctor")
    form = HealthRecordForm(request.POST or None)
    form.fields["patient"].queryset = patients_qs
    if request.method == "POST" and form.is_valid():
        record = form.save(commit=False)
        record.doctor = request.user if is_doctor(request.user) or is_admin(request.user) else record.patient.assigned_doctor
        record.save()
        messages.success(request, "Health record saved successfully.")
        return redirect("health_records")
    return render(request, "health_application/health_records.html", {"records": records, "form": form})


@login_required
def health_record_edit(request, pk):
    record = get_object_or_404(HealthRecord, pk=pk, patient__in=visible_patients(request.user))
    if not (is_admin(request.user) or is_doctor(request.user)):
        return HttpResponseForbidden("Only doctors and admins can update health records.")
    form = HealthRecordForm(request.POST or None, instance=record)
    form.fields["patient"].queryset = visible_patients(request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Health record updated successfully.")
        return redirect("health_records")
    return render(request, "health_application/health_record_form.html", {"form": form, "page_title": "Edit Health Record"})


@login_required
def reminders(request):
    patients_qs = visible_patients(request.user)
    reminder_list = MedicationReminder.objects.filter(patient__in=patients_qs).select_related("patient", "created_by")
    for reminder in reminder_list:
        sync_reminder_state(reminder)
    form = None
    if can_manage_reminders(request.user):
        form = MedicationReminderForm(request.POST or None)
        form.fields["patient"].queryset = patients_qs
        if request.method == "POST" and form.is_valid():
            reminder = form.save(commit=False)
            reminder.created_by = request.user
            reminder.next_trigger_at = reminder.calculate_next_trigger_at()
            reminder.save()
            create_notification(reminder.patient.user, "Medication reminder", f"{reminder.medicine_name} at {reminder.reminder_time:%H:%M}", "REMINDER")
            messages.success(request, "Medication reminder created successfully.")
            return redirect("reminders")
    elif request.method == "POST":
        return HttpResponseForbidden("Patients and caregivers can view reminders but cannot manage them.")
    history = MedicationIntakeLog.objects.filter(patient__in=patients_qs).select_related("patient", "reminder")[:50]
    return render(
        request,
        "health_application/reminders.html",
        {"reminders": reminder_list, "form": form, "can_manage_reminders": can_manage_reminders(request.user), "history": history},
    )


@login_required
def reminder_edit(request, pk):
    if not can_manage_reminders(request.user):
        return HttpResponseForbidden("Only doctors and admins can manage reminders.")
    reminder = get_object_or_404(MedicationReminder, pk=pk, patient__in=visible_patients(request.user))
    form = MedicationReminderForm(request.POST or None, instance=reminder)
    form.fields["patient"].queryset = visible_patients(request.user)
    if request.method == "POST" and form.is_valid():
        reminder = form.save(commit=False)
        reminder.next_trigger_at = reminder.calculate_next_trigger_at()
        reminder.save()
        messages.success(request, "Reminder updated successfully.")
        return redirect("reminders")
    return render(request, "health_application/reminder_form.html", {"form": form, "page_title": "Edit Reminder"})


@login_required
def reminder_delete(request, pk):
    if not can_manage_reminders(request.user):
        return HttpResponseForbidden("Only doctors and admins can manage reminders.")
    reminder = get_object_or_404(MedicationReminder, pk=pk, patient__in=visible_patients(request.user))
    if request.method == "POST":
        reminder.delete()
        messages.success(request, "Reminder deleted successfully.")
    return redirect("reminders")


@login_required
@require_GET
def active_reminders_api(request):
    patients_qs = visible_patients(request.user)
    reminders_qs = MedicationReminder.objects.filter(patient__in=patients_qs, is_active=True).select_related("patient")
    data = []
    for reminder in reminders_qs:
        sync_reminder_state(reminder)
        if reminder.next_trigger_at:
            data.append(reminder_payload(reminder))
    return JsonResponse({"reminders": data, "server_time": timezone.now().isoformat()})


@login_required
@require_POST
def mark_reminder_taken_api(request, pk):
    reminder = get_object_or_404(MedicationReminder.objects.select_related("patient"), pk=pk, patient__in=visible_patients(request.user))
    if can_manage_reminders(request.user) and reminder.patient.user_id != request.user.id:
        return HttpResponseForbidden("Only the patient or caregiver can mark this reminder as taken.")
    sync_reminder_state(reminder)
    scheduled_for = reminder.next_trigger_at or timezone.now()
    log = (
        MedicationIntakeLog.objects.filter(reminder=reminder, status=MedicationIntakeLog.STATUS_PENDING)
        .order_by("-scheduled_for")
        .first()
    )
    if not log:
        log, _ = MedicationIntakeLog.objects.get_or_create(
            reminder=reminder,
            patient=reminder.patient,
            scheduled_for=scheduled_for,
            defaults={"status": MedicationIntakeLog.STATUS_PENDING},
        )
    log.status = MedicationIntakeLog.STATUS_TAKEN
    log.taken_at = timezone.now()
    log.save(update_fields=["status", "taken_at"])
    reminder.last_triggered_at = log.scheduled_for
    reminder.next_trigger_at = reminder.calculate_next_trigger_at(after=log.scheduled_for)
    reminder.save(update_fields=["last_triggered_at", "next_trigger_at"])
    return JsonResponse({"ok": True, "reminder": reminder_payload(reminder) if reminder.next_trigger_at else None})


@login_required
def inbox(request):
    messages_qs = Message.objects.filter(recipient=request.user).select_related("sender", "recipient", "patient")
    return render(request, "health_application/messages.html", {"messages_list": messages_qs, "box": "Inbox"})


@login_required
def sent_messages(request):
    messages_qs = Message.objects.filter(sender=request.user).select_related("recipient", "patient")
    return render(request, "health_application/messages.html", {"messages_list": messages_qs, "box": "Sent"})


@login_required
def compose_message(request):
    if is_doctor(request.user):
        return HttpResponseForbidden("Doctors send feedback from the message detail or medical advice screens.")
    form = MessageForm(request.POST or None, request.FILES or None)
    patients_qs = visible_patients(request.user)
    form.fields["patient"].queryset = patients_qs
    if request.method == "POST" and form.is_valid():
        message_obj = form.save(commit=False)
        message_obj.sender = request.user
        if not message_obj.patient or not patients_qs.filter(pk=message_obj.patient_id).exists():
            return HttpResponseForbidden("You are not allowed to message about this patient.")
        if is_admin(request.user):
            message_obj.recipient = message_obj.patient.assigned_doctor or message_obj.patient.user
        else:
            if not message_obj.patient.assigned_doctor_id:
                form.add_error("patient", "Assign a doctor to this patient before sending a message.")
                return render(request, "health_application/compose_message.html", {"form": form})
            message_obj.recipient = message_obj.patient.assigned_doctor
        message_obj.save()
        create_notification(message_obj.recipient, "New caregiver message", message_obj.subject, "MESSAGE", message_obj)
        messages.success(request, "Message sent successfully.")
        return redirect("sent_messages")
    return render(request, "health_application/compose_message.html", {"form": form})


@login_required
def message_detail(request, pk):
    message_obj = get_object_or_404(Message.objects.select_related("sender", "recipient", "patient"), pk=pk)
    if not can_view_message(request.user, message_obj):
        return HttpResponseForbidden("You are not allowed to view this message.")
    can_doctor_review = (
        (is_doctor(request.user) or is_admin(request.user))
        and message_obj.patient_id
        and (is_admin(request.user) or message_obj.patient.assigned_doctor_id == request.user.id)
    )
    advice_form = None
    if message_obj.recipient_id == request.user.id and not message_obj.is_read:
        message_obj.is_read = True
        message_obj.reviewed_at = timezone.now()
        message_obj.save(update_fields=["is_read", "reviewed_at"])
    if can_doctor_review:
        advice_form = MedicalAdviceForm(
            request.POST or None,
            request.FILES or None,
            initial={"patient": message_obj.patient, "title": f"Feedback: {message_obj.subject}"},
        )
        advice_form.fields["patient"].queryset = Patient.objects.filter(pk=message_obj.patient_id)
        advice_form.fields["patient"].widget = advice_form.fields["patient"].hidden_widget()
        if request.method == "POST":
            action = request.POST.get("action")
            if action == "appointment":
                message_obj.appointment_needed = request.POST.get("appointment_needed") == "1"
                message_obj.is_read = True
                message_obj.reviewed_at = message_obj.reviewed_at or timezone.now()
                message_obj.save(update_fields=["appointment_needed", "is_read", "reviewed_at"])
                status = "needed" if message_obj.appointment_needed else "not needed"
                create_notification(message_obj.sender, "Appointment decision", f"Appointment {status} for {message_obj.patient.full_name}.", "APPOINTMENT", message_obj)
                messages.success(request, "Appointment decision saved.")
                return redirect("message_detail", pk=message_obj.pk)
            if action == "advice" and advice_form.is_valid():
                advice_obj = advice_form.save(commit=False)
                advice_obj.doctor = request.user
                advice_obj.patient = message_obj.patient
                advice_obj.source_message = message_obj
                advice_obj.save()
                create_notification(message_obj.sender, "Doctor feedback", advice_obj.title, "ADVICE", message_obj)
                messages.success(request, "Doctor feedback sent successfully.")
                return redirect("message_detail", pk=message_obj.pk)
    return render(
        request,
        "health_application/message_detail.html",
        {"message_obj": message_obj, "advice_form": advice_form, "can_doctor_review": can_doctor_review},
    )


@login_required
def advice(request):
    patients_qs = visible_patients(request.user)
    advice_qs = MedicalAdvice.objects.filter(patient__in=patients_qs).select_related("doctor", "patient")
    form = None
    if is_doctor(request.user) or is_admin(request.user):
        form = MedicalAdviceForm(request.POST or None, request.FILES or None)
        form.fields["patient"].queryset = patients_qs
        if request.method == "POST" and form.is_valid():
            advice_obj = form.save(commit=False)
            advice_obj.doctor = request.user
            advice_obj.save()
            create_notification(advice_obj.patient.user, "Doctor feedback", advice_obj.title, "ADVICE")
            messages.success(request, "Medical advice sent successfully.")
            return redirect("advice")
    return render(request, "health_application/advice.html", {"advice_list": advice_qs, "form": form})


@login_required
def notifications_list(request):
    return render(request, "health_application/notifications.html", {"notifications": request.user.notifications.all()})


@login_required
def mark_notification_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.is_read = True
    notification.save(update_fields=["is_read"])
    next_url = request.POST.get("next") or request.GET.get("next") or "notifications"
    return redirect(next_url)


@login_required
def profile(request):
    profile_obj, _ = Profile.objects.get_or_create(user=request.user)
    form = ProfileForm(request.POST or None, instance=profile_obj, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profile updated successfully.")
        return redirect("profile")
    return render(request, "health_application/profile.html", {"form": form, "profile": profile_obj})


@login_required
def reports(request):
    if not is_admin(request.user):
        return HttpResponseForbidden("Only admins can access reports.")
    patients_qs = visible_patients(request.user)
    context = {
        "total_patients": patients_qs.count(),
        "total_reminders": MedicationReminder.objects.filter(patient__in=patients_qs).count(),
        "active_reminders": MedicationReminder.objects.filter(patient__in=patients_qs, is_active=True).count(),
        "total_health_records": HealthRecord.objects.filter(patient__in=patients_qs).count(),
        "total_messages": Message.objects.filter(Q(recipient=request.user) | Q(sender=request.user)).count(),
        "recent_patients": patients_qs.order_by("-created_at")[:5],
    }
    if is_admin(request.user):
        context.update(total_users=User.objects.count(), total_doctors=Profile.objects.filter(role=Profile.ROLE_DOCTOR).count())
    return render(request, "health_application/reports.html", context)


def not_found(request, exception=None):
    return render(request, "health_application/404.html", status=404)


def service_worker(request):
    response = FileResponse(open(settings.BASE_DIR / "health_application/static/health_application/sw.js", "rb"), content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    return response
