from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import MedicalAdvice, Message, Notification, Patient, Profile


class DashboardContextTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="patient", password="secret123")
        self.profile, _ = Profile.objects.get_or_create(user=self.user, defaults={"role": Profile.ROLE_PATIENT})
        self.patient = Patient.objects.create(user=self.user, full_name="Jane Doe", gender="Female", age=30)

    def test_dashboard_shows_total_advice_and_notification_counts(self):
        MedicalAdvice.objects.create(doctor=self.user, patient=self.patient, title="Take rest")
        MedicalAdvice.objects.create(doctor=self.user, patient=self.patient, title="Hydrate")
        Notification.objects.create(user=self.user, title="Reminder", message="Take medicine")
        Notification.objects.create(user=self.user, title="Advice", message="Drink water", is_read=True)

        self.client.login(username="patient", password="secret123")
        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_advice"], 2)
        self.assertEqual(response.context["total_notifications"], 2)

    def test_doctor_dashboard_shows_sent_advice_count(self):
        doctor = get_user_model().objects.create_user(username="doctor", password="secret123")
        doctor_profile, created = Profile.objects.get_or_create(user=doctor, defaults={"role": Profile.ROLE_DOCTOR})
        if not created and doctor_profile.role != Profile.ROLE_DOCTOR:
            doctor_profile.role = Profile.ROLE_DOCTOR
            doctor_profile.save(update_fields=["role"])
        patient = Patient.objects.create(user=self.user, full_name="Jane Doe", gender="Female", age=30, assigned_doctor=doctor)
        MedicalAdvice.objects.create(doctor=doctor, patient=patient, title="Rest well")
        MedicalAdvice.objects.create(doctor=doctor, patient=patient, title="Drink water")

        self.client.login(username="doctor", password="secret123")
        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["role"], Profile.ROLE_DOCTOR)
        self.assertEqual(response.context["total_sent_advice"], 2)


class MessageReplyTests(TestCase):
    def setUp(self):
        self.caregiver = get_user_model().objects.create_user(username="caregiver", password="secret123")
        self.caregiver_profile, _ = Profile.objects.get_or_create(user=self.caregiver, defaults={"role": Profile.ROLE_PATIENT})
        self.doctor = get_user_model().objects.create_user(username="doctor", password="secret123")
        self.doctor_profile, _ = Profile.objects.get_or_create(user=self.doctor, defaults={"role": Profile.ROLE_DOCTOR})
        self.patient = Patient.objects.create(user=self.caregiver, full_name="Jane Doe", gender="Female", age=30, assigned_doctor=self.doctor)
        self.message = Message.objects.create(
            sender=self.caregiver,
            recipient=self.doctor,
            patient=self.patient,
            subject="Need help",
            body="Please advise",
            message_type=Message.TYPE_TEXT,
        )

    def test_reply_message_visible_to_sender_and_recipient(self):
        self.client.login(username="doctor", password="secret123")
        response = self.client.post(
            reverse("message_detail", args=[self.message.pk]),
            {
                "action": "reply",
                "patient": self.patient.pk,
                "subject": "Re: Need help",
                "message_type": Message.TYPE_TEXT,
                "body": "Please schedule an appointment.",
            },
        )
        self.assertEqual(response.status_code, 302)
        reply = Message.objects.filter(reply_to=self.message).first()
        self.assertIsNotNone(reply)
        self.assertEqual(reply.sender, self.doctor)
        self.assertEqual(reply.recipient, self.caregiver)

        self.client.logout()
        self.client.login(username="caregiver", password="secret123")
        response = self.client.get(reverse("message_detail", args=[self.message.pk]))
        self.assertContains(response, "Re: Need help")
