from django.db import models

# Create your models here.

from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    api_key = models.TextField(blank=True, null=True)
    wba_id = models.CharField(max_length=50, blank=True, null=True)
    phone_number_id = models.CharField(max_length=50, blank=True, null=True)
    app_id = models.CharField(max_length=50, blank=True, null=True)
    business_id = models.CharField(max_length=50, blank=True, null=True)
    meta_connected_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.user.username


class EndUserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='enduser_profile')
    phone_number = models.CharField(max_length=15, blank=True, null=True)

    def __str__(self):
        return self.user.username

# Signal to create or update UserProfile when a User is created/updated
@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)
    else:
        instance.profile.save()
