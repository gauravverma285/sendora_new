from django.contrib import admin

# Register your models here.
from .models import Contact, Tag, OptOutUser, GlobalOptOut, Campaign, CampaignMessage

# Register your models here.

admin.site.register([Contact, Tag, OptOutUser, GlobalOptOut, Campaign])


@admin.register(CampaignMessage)
class CampaignMessageAdmin(admin.ModelAdmin):
    list_display = ("mobile_number", "campaign", "status", "wamid", "sent_at", "delivered_at", "read_at", "failed_at")
    list_filter = ("status", "campaign")
    search_fields = ("mobile_number", "wamid")

from .models import Conversation, ChatMessage


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("user", "contact_number", "profile_name", "last_message_at", "unread_count")
    list_filter = ("user",)
    search_fields = ("contact_number", "profile_name")


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("user", "conversation", "direction", "message_type", "status", "timestamp")
    list_filter = ("user", "direction", "status")
    search_fields = ("body", "wamid")
