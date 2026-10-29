from django.urls import path

from . import api_views

urlpatterns = [
    path('messages/send/', api_views.SendMessageView.as_view(), name='api_send_message'),
    path('messages/send-bulk/', api_views.SendBulkMessageView.as_view(), name='api_send_bulk_message'),
    path('leads/', api_views.NewLeadsView.as_view(), name='api_new_leads'),
]
