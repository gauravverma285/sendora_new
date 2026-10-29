from django.urls import path, include
from accounts import views

urlpatterns = [
    path('', include('allauth.urls')),  # Routes from `django-allauth`
    path('user-detail/',views.user_detail_view, name='user_detail'),  # Custom user detail page
    path('api-token/regenerate/', views.regenerate_api_token, name='regenerate_api_token'),
    path('update-avatar/', views.update_avatar, name='update_avatar'),

    path('whatsapp/send-otp/', views.send_otp_view, name='send_otp'),
    path('whatsapp/verify-otp/', views.verify_otp_view, name='verify_otp'),

    path('whatsapp/embedded-signup/callback/', views.whatsapp_embedded_signup_callback, name='whatsapp_embedded_signup_callback'),



]
