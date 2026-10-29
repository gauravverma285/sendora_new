import re

from rest_framework import serializers

PHONE_RE = re.compile(r'^\+?[1-9]\d{6,14}$')


def validate_phone_number(value):
    cleaned = value.strip()
    if not PHONE_RE.match(cleaned):
        raise serializers.ValidationError(
            f"'{value}' is not a valid phone number. Use international format, e.g. +919876543210."
        )
    return cleaned


class HeaderParamSerializer(serializers.Serializer):
    type = serializers.ChoiceField(
        choices=["image", "video", "document"],
        help_text="Must match the header format the template was created with.",
    )
    id = serializers.CharField(help_text="Meta media ID (from uploading the file to Meta beforehand).")
    filename = serializers.CharField(
        required=False, allow_blank=True,
        help_text="Required when type is 'document'.",
    )


class ButtonParamSerializer(serializers.Serializer):
    index = serializers.IntegerField(min_value=0, help_text="0-based position of this button in the template.")
    sub_type = serializers.ChoiceField(choices=["url", "copy_code"])
    value = serializers.CharField(help_text="The URL's variable value, or the coupon/copy code.")


class BaseSendMessageSerializer(serializers.Serializer):
    template_name = serializers.CharField(help_text="Name of an APPROVED template on your WhatsApp Business Account.")
    language = serializers.CharField(default="en_US", help_text="Template language code, e.g. en_US.")
    header = HeaderParamSerializer(required=False, help_text="Only needed if the template has a media header.")
    body_params = serializers.ListField(
        child=serializers.CharField(allow_blank=True),
        required=False,
        default=list,
        help_text="Values for the template body's {{1}}, {{2}}, ... variables, in order.",
    )
    button_params = ButtonParamSerializer(
        many=True, required=False, default=list,
        help_text="Only needed for buttons with a variable (dynamic URL suffix or copy code).",
    )


class SendMessageSerializer(BaseSendMessageSerializer):
    to = serializers.CharField(help_text="Recipient phone number in international format, e.g. +919876543210.")

    def validate_to(self, value):
        return validate_phone_number(value)


class SendBulkMessageSerializer(BaseSendMessageSerializer):
    to = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=False,
        help_text='List of recipient phone numbers, e.g. ["+919876543210", "+917877383709"].',
    )

    def validate_to(self, value):
        return [validate_phone_number(number) for number in value]


class LeadQuerySerializer(serializers.Serializer):
    reengage_after_days = serializers.IntegerField(
        required=False, min_value=1,
        help_text="Optional. Omit this and every inbound message is delivered as its own "
                   "one-time lead (useful for testing). Set it to collapse leads to one per "
                   "contact instead: a contact already delivered is suppressed until at least "
                   "this many days have passed AND they've messaged again since their last "
                   "delivery, at which point they're delivered again as a new lead.",
    )


class LeadSerializer(serializers.Serializer):
    contact_number = serializers.CharField(help_text="The lead's WhatsApp number with a leading +, e.g. +15556748313.")
    wa_id = serializers.CharField(help_text="The same number in WhatsApp's wa_id format (digits only, no +).")
    name = serializers.CharField(
        help_text="The lead's saved name if you have them tagged in Contacts, otherwise their "
                   "WhatsApp profile name, otherwise their number."
    )
    message = serializers.CharField(help_text="Their latest message at the time this lead was delivered.")
    message_type = serializers.CharField(help_text="text, image, video, document, audio, etc.")
    timestamp = serializers.DateTimeField(help_text="When that message was sent.")
    wamid = serializers.CharField(help_text="Meta's unique id for that message.")
