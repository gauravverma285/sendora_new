from django.urls import path
from services import views, chat_views
urlpatterns = [
    path('', views.services, name='services'),
    path('template_list/', views.template_list, name='template_list'),
    path('rejected_templates/', views.rejected_templates, name='rejected_templates'),
    path('edit_templates_rules/', views.edit_templates_rules, name='edit_templates_rules'),
    path('delete_template/', views.delete_template, name='delete_template'),
    path('template/<int:template_id>/', views.view_template, name='view_template'),
    # urls.py
    path('create_template/', views.create_or_edit_template, name="create_template"),
    path('edit/<str:template_id>/', views.create_or_edit_template, name="edit_template"),
    
    path('upload-media/', views.upload_media, name='upload_media'),  # ✅ Keep it on the same page

    path('contacts_list/', views.contacts_list, name='contacts_list'),
    path('add_contact/', views.add_contact, name='add_contact'),
    path('update_contact/<int:contact_id>/', views.update_contact, name='update_contact'),


    path('campaign/', views.create_campaign, name='create_campaign'),
    path('check-campaign-name/', views.check_campaign_name, name='check_campaign_name'),
    path('campaign/search_contacts/', views.campaign_search_contacts, name='campaign_search_contacts'),
    path('campaign_list/', views.campaign_list, name='campaign_list'),
    path('campaign_analytics/', views.campaign_analytics, name='campaign_analytics'),
    path('campaign_analytics/export/', views.export_campaign_analytics, name='export_campaign_analytics'),
    path('campaign_analytics/recipients/', views.campaign_recipients, name='campaign_recipients'),
    path('campaign_analytics/retarget/', views.campaign_retarget, name='campaign_retarget'),
    path('fetch_analytics/', views.fetch_analytics, name='fetch_analytics'),
    path("stop_campaign/", views.stop_campaign, name="stop_campaign"),
    path("start_campaign/", views.start_campaign, name="start_campaign"),
    path('campaign/delete/<int:campaign_id>/', views.delete_campaign, name='delete_campaign'),


    path("webhook/", views.whatsapp_webhook, name="whatsapp_webhook"),

    path('tags/', views.tag_list, name='tag_list'),
    path('tags/create/', views.create_tag, name='create_tag'),
    path('tags/<int:tag_id>/update/', views.update_tag, name='update_tag'),
    path('tags/<int:tag_id>/delete/', views.delete_tag, name='delete_tag'),
    # path('campaign/', views.create_campaign, name='send_message_to_test_user'),

    path('toggle_opt_out/', views.toggle_opt_out, name='toggle_opt_out'),

    # Messages inbox (WhatsApp chat) — everything scoped to the signed-in account
    path('messages/', chat_views.chat_page, name='chat'),
    path('messages/api/conversations/', chat_views.chat_conversations, name='chat_conversations'),
    path('messages/api/thread/', chat_views.chat_thread, name='chat_thread'),
    path('messages/api/send/', chat_views.chat_send, name='chat_send'),
    path('messages/api/save-contact/', chat_views.chat_save_contact, name='chat_save_contact'),
    path('messages/api/add-tag/', chat_views.chat_add_tag, name='chat_add_tag'),
    path('messages/media/<int:message_id>/', chat_views.chat_media, name='chat_media'),

    path('flows/', views.flow_list, name='flow_list'),
    path('flows/create/', views.flow_create, name='flow_create'),
    path('flows/<int:flow_id>/', views.flow_builder, name='flow_builder'),
    path('flows/<int:flow_id>/save/', views.flow_save, name='flow_save'),
    path('flows/<int:flow_id>/delete/', views.flow_delete, name='flow_delete'),
    path('flows/<int:flow_id>/toggle/', views.flow_toggle_active, name='flow_toggle_active'),

]
