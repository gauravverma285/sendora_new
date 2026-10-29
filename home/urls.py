from django.urls import path
from home import views
urlpatterns = [
    path('',views.index,name='home' ),
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),
    path('pricing/', views.pricing, name='pricing'),
    path('how_it_works/', views.how_it_works, name='how_it_works'),

    # steps to follow
    path('step1/', views.step1, name='step1'),
    path('faqs/', views.faqs, name='faqs'),
    path('privacy-policy/', views.privacy_policy, name='privacy_policy'),
    path('terms-of-service/', views.terms_of_service, name='terms_of_service'),

]
