from django import forms
from django.contrib.auth.models import User
from .models import UserProfile

class UserDetailForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'email']

class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['phone_number', 'api_key', 'wba_id','phone_number_id','app_id']
