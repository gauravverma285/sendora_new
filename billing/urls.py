from django.urls import path

from . import views

app_name = "billing"

urlpatterns = [
    path("plans/", views.plan_list, name="plan_list"),
    path("plans/<slug:slug>/checkout/", views.checkout, name="checkout"),
]
