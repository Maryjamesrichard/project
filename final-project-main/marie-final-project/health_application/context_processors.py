def notifications(request):
    if not request.user.is_authenticated:
        return {}
    unread = request.user.notifications.filter(is_read=False)
    return {
        "unread_notification_count": unread.count(),
        "latest_unread_notifications": unread[:5],
    }
