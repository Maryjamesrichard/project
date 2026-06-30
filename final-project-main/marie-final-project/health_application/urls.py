from django.urls import path

from . import views

urlpatterns = [
    path("sw.js", views.service_worker, name="service_worker"),
    path("", views.dashboard, name="dashboard"),
    path("login/", views.login_view, name="login"),
    path("register/", views.register_view, name="register"),
    path("logout/", views.logout_view, name="logout"),
    path("patients/", views.patients, name="patients"),
    path("patients/create/", views.patient_create, name="patient_create"),
    path("patients/<int:pk>/", views.patient_detail, name="patient_detail"),
    path("patients/<int:pk>/edit/", views.patient_edit, name="patient_edit"),
    path("patients/<int:pk>/delete/", views.patient_delete, name="patient_delete"),
    path("health-records/", views.health_records, name="health_records"),
    path("health-records/<int:pk>/edit/", views.health_record_edit, name="health_record_edit"),
    path("reminders/", views.reminders, name="reminders"),
    path("reminders/<int:pk>/edit/", views.reminder_edit, name="reminder_edit"),
    path("reminders/<int:pk>/delete/", views.reminder_delete, name="reminder_delete"),
    path("api/reminders/active/", views.active_reminders_api, name="active_reminders_api"),
    path("api/reminders/<int:pk>/mark-taken/", views.mark_reminder_taken_api, name="mark_reminder_taken_api"),
    path("messages/", views.inbox, name="messages"),
    path("messages/sent/", views.sent_messages, name="sent_messages"),
    path("messages/compose/", views.compose_message, name="compose_message"),
    path("messages/<int:pk>/", views.message_detail, name="message_detail"),
    path("advice/", views.advice, name="advice"),
    path("notifications/", views.notifications_list, name="notifications"),
    path("notifications/<int:pk>/read/", views.mark_notification_read, name="mark_notification_read"),
    path("profile/", views.profile, name="profile"),
    path("reports/", views.reports, name="reports"),
]
