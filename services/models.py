from django.db import models
from django.contrib.auth.models import User
from django.contrib.postgres.fields import ArrayField  # For storing list of numbers
import json

# Create your models here.
class Tag(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tags")
    name = models.CharField(max_length=50)
    is_prebuilt = models.BooleanField(default=False)  # New field for system tags

    class Meta:
        unique_together = ('name', 'user')  # Each user can have unique tag names

    def __str__(self):
        return self.name
    
class Contact(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="contacts")
    name = models.CharField(blank=True, max_length=255)
    mobile_number = models.CharField(max_length=15)
    email = models.EmailField(blank=True, null=True)
    age = models.PositiveIntegerField(blank=True, null=True)
    tags = models.ManyToManyField(Tag, blank=True)  # Store tags as comma-separated values

    class Meta:
        # Unique *per account*, not globally — two different businesses can
        # each have the same customer's number in their own contact list.
        unique_together = ("user", "mobile_number")

    def __str__(self):
        return self.mobile_number

class OptOutUser(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="opt_out_users")
    contact = models.ForeignKey("Contact", on_delete=models.CASCADE, related_name="opt_outs")
    opted_out_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.contact.mobile_number} opted out"

class GlobalOptOut(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="global_opt_out")
    is_enabled = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username} - Opt-Out: {self.is_enabled}"


class Campaign(models.Model):
    MESSAGE_TYPE_CHOICES = [
        ("template", "Template"),
        ("text", "Text"),
        ("image", "Image"),
        ("document", "Document"),
    ]
    CAMPAIGN_TYPE_CHOICES = [
        ("broadcast", "Broadcast"),
        ("personalized", "Personalized"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    campaign_name = models.CharField(max_length=255)
    template_name = models.CharField(max_length=255, blank=True)
    template_id = models.CharField(max_length=255, blank=True, null=True)
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPE_CHOICES, default="template")
    campaign_type = models.CharField(max_length=20, choices=CAMPAIGN_TYPE_CHOICES, default="broadcast")
    add_unsubscribe_button = models.BooleanField(default=False)
    track_status = models.BooleanField(default=False)
    is_draft = models.BooleanField(default=False)
    start_time = models.DateTimeField()  # Store when the campaign is created
    end_time = models.DateTimeField(blank=True, null=True)  # Set this when the campaign is completed
    contact_numbers = models.JSONField(default=list)  # Store numbers in JSON format
    is_scheduled = models.BooleanField(default=False)
    scheduled_time = models.DateTimeField(null=True, blank=True)

    sending_payload = models.JSONField(null=True, blank=True)
    customer_list = models.JSONField(null=True, blank=True)
    final_data = models.JSONField(null=True, blank=True)

    # Raw, always-resumable inputs — stored independently of sending_payload
    # so an incomplete draft (missing an upload, no template chosen yet, ...)
    # can still be reopened and finished later without retyping anything.
    audience_mode = models.CharField(max_length=20, default="all")
    audience_tags = models.JSONField(default=list, blank=True)
    audience_contact_ids = models.JSONField(default=list, blank=True)
    message_text = models.TextField(blank=True, default="")
    media_id = models.CharField(max_length=255, blank=True, default="")
    media_caption = models.TextField(blank=True, default="")
    media_filename = models.CharField(max_length=255, blank=True, default="")

    # Set when this campaign was created via "Retarget" from another
    # campaign's recipient list (see services.views.campaign_retarget) —
    # lets the UI show "Retry of: <original>" and compute a recovery rate
    # (how many of the retargeted contacts delivered/read/replied this
    # time, vs. the original send).
    retargeted_from = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="retargets"
    )

    def __str__(self):
        return f"{self.campaign_name} - {self.template_name or self.message_type}"


class CampaignMessage(models.Model):
    """One outbound WhatsApp message sent as part of a campaign, tracked by
    its Meta message id (wamid) so the webhook's per-message status updates
    (sent/delivered/read/failed) can be attributed to the exact campaign
    that sent it.

    This is what campaign_analytics is built from instead of Meta's
    `template_analytics` endpoint — that endpoint reports totals per
    *template* across the whole WABA, so two campaigns sharing one template
    (or the same template reused later) show mixed-together numbers there.
    Counting our own rows per-campaign avoids that entirely.
    """
    STATUS_CHOICES = [
        ("queued", "Queued"),
        ("sent", "Sent"),
        ("delivered", "Delivered"),
        ("read", "Read"),
        ("failed", "Failed"),
    ]
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="messages")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="campaign_messages")
    contact_name = models.CharField(max_length=255, blank=True)
    mobile_number = models.CharField(max_length=20)

    # The "messages"[0]["id"] Meta returns from the send call. Null when the
    # send itself failed before Meta ever assigned an id (e.g. a network
    # error) — status webhooks then have nothing to match against, so this
    # row just stays "failed" from the send response alone.
    wamid = models.CharField(max_length=150, unique=True, null=True, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="queued")

    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    # Set when an inbound message's `context.id` points back at this wamid —
    # i.e. the contact replied to (or tapped a button on) this exact message.
    replied_at = models.DateTimeField(null=True, blank=True)
    # Subset of the above: specifically a template quick-reply / interactive
    # button tap, not a plain text reply. Meta does not report per-message
    # clicks for URL buttons over the webhook (only aggregated, per-template,
    # via template_analytics) so a URL button tap can't be attributed here.
    clicked_at = models.DateTimeField(null=True, blank=True)

    error_code = models.CharField(max_length=20, blank=True)
    error_title = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)
    # Meta's short `error.message` ("Re-engagement message") explains what
    # went wrong in a couple of words; the actual human-readable explanation
    # ("...more than 24 hours have passed since the customer last replied")
    # lives one level deeper in `error.error_data.details` — worth keeping
    # separately since it's what actually tells the sender what to do next.
    error_details = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["campaign", "status"])]

    def __str__(self):
        return f"{self.mobile_number} - {self.status} (campaign {self.campaign_id})"


class Flow(models.Model):
    """A chatbot conversation flow: a named graph of messages, triggered by
    a keyword (or any inbound message) and driven forward by the webhook as
    the contact taps buttons."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="flows")
    name = models.CharField(max_length=255)
    trigger_keywords = models.JSONField(default=list, blank=True)  # lowercase strings
    trigger_any_message = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    start_node = models.ForeignKey(
        "FlowNode", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class FlowNode(models.Model):
    MESSAGE_TYPE_CHOICES = [
        ("text", "Text"),
        ("image", "Image"),
        ("video", "Video"),
        ("document", "Document"),
        ("capture", "Ask & Save Answer"),
        ("api_call", "Call External API"),
    ]
    flow = models.ForeignKey(Flow, on_delete=models.CASCADE, related_name="nodes")
    # A stable id assigned client-side when a node is first drawn, so saving
    # the flow again can update/reposition existing nodes (and follow their
    # button connections) instead of recreating everything with new ids —
    # which would silently orphan anyone mid-conversation on that node.
    client_key = models.CharField(max_length=40)
    title = models.CharField(max_length=255, blank=True)
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPE_CHOICES, default="text")
    body_text = models.TextField(blank=True)
    media_id = models.CharField(max_length=255, blank=True)
    media_filename = models.CharField(max_length=255, blank=True)
    pos_x = models.FloatField(default=40)
    pos_y = models.FloatField(default=40)
    is_end = models.BooleanField(default=False)

    # -- "capture" nodes: send body_text as the question, then store the
    # contact's next text reply under this variable name (e.g. "email"). --
    capture_variable = models.CharField(max_length=100, blank=True)
    # If set, the captured value is wiped from ContactFlowState.variables
    # right after the next API Call node runs — so a password, say, never
    # sits in the database longer than it takes to log in with it.
    capture_sensitive = models.BooleanField(default=False)

    # -- "api_call" nodes: call an external API using previously-captured
    # variables, save fields from the response as new variables, then
    # branch to a "success" or "failure" node automatically (no user input
    # needed to advance past this node type). --
    api_url = models.CharField(max_length=500, blank=True)
    api_method = models.CharField(max_length=10, default="POST")
    # {"Authorization": "Bearer {{access_token}}", ...} - values may contain
    # {{variable}} placeholders filled in from ContactFlowState.variables.
    api_headers = models.JSONField(default=dict, blank=True)
    api_body = models.JSONField(default=dict, blank=True)
    # How to encode api_body on the wire — a plain JSON API needs "json",
    # while a classic server-rendered form (e.g. Django's request.POST,
    # which never sees a raw JSON body) needs "form". Client-configurable,
    # not assumed — different client APIs expect different things here.
    API_BODY_TYPE_CHOICES = [("json", "JSON"), ("form", "Form (x-www-form-urlencoded)")]
    api_body_type = models.CharField(max_length=10, choices=API_BODY_TYPE_CHOICES, default="json")
    # {"access_token": "data.token", ...} - maps a variable name to a
    # dot-path into the JSON response to pull its value from.
    api_response_mapping = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = ("flow", "client_key")

    def __str__(self):
        return self.title or f"Node {self.pk}"


class FlowButton(models.Model):
    """An outgoing edge from a node. For text/image/video/document nodes
    this is a real WhatsApp reply button (kind="reply", up to 3, shown to
    the contact). "capture" nodes get exactly one auto-managed "next" edge,
    and "api_call" nodes get exactly one "success" and one "failure" edge —
    none of those three are ever rendered as WhatsApp buttons."""
    KIND_CHOICES = [
        ("reply", "Reply Button"),
        ("next", "Next"),
        ("success", "On Success"),
        ("failure", "On Failure"),
    ]
    node = models.ForeignKey(FlowNode, on_delete=models.CASCADE, related_name="buttons")
    text = models.CharField(max_length=20)  # WhatsApp reply button title limit
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default="reply")
    order = models.PositiveSmallIntegerField(default=0)
    next_node = models.ForeignKey(
        FlowNode, null=True, blank=True, on_delete=models.SET_NULL, related_name="incoming_buttons"
    )

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.text


class ContactFlowState(models.Model):
    """Tracks which node of which flow a given contact is currently on, so
    an incoming button tap (or captured text reply) can be routed to the
    right "next" message. `variables` holds anything captured or returned
    by an API call during this conversation (e.g. email, access_token)."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="flow_states")
    mobile_number = models.CharField(max_length=20)
    flow = models.ForeignKey(Flow, on_delete=models.CASCADE)
    current_node = models.ForeignKey(FlowNode, null=True, on_delete=models.SET_NULL)
    variables = models.JSONField(default=dict, blank=True)
    # Names of variables (within `variables`) captured from a "sensitive"
    # capture node, to be purged the moment an API Call node next runs.
    sensitive_keys = models.JSONField(default=list, blank=True)
    # Cookies received from an API Call node's response (e.g. a Django
    # CSRF/session cookie set on a GET) are carried forward to later API
    # Call nodes in the same conversation, the way a browser would.
    cookies = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "mobile_number")


class Conversation(models.Model):
    """One chat thread between an account (`user`) and one customer number.

    Everything in the Messages inbox is scoped by `user`: the webhook maps
    the receiving WhatsApp number (phone_number_id) to exactly one account,
    so two accounts that both talk to the same customer number get two
    completely separate conversations."""
    DIRECTION_CHOICES = [("in", "Incoming"), ("out", "Outgoing")]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="conversations")
    # Digits only, WhatsApp "wa_id" format (e.g. 917745968882), no leading "+".
    contact_number = models.CharField(max_length=20)
    # The name the customer set on their own WhatsApp — used when the number
    # isn't saved in this account's Contacts.
    profile_name = models.CharField(max_length=255, blank=True)

    last_message_at = models.DateTimeField(null=True, blank=True)
    last_message_preview = models.CharField(max_length=255, blank=True)
    last_direction = models.CharField(max_length=3, choices=DIRECTION_CHOICES, blank=True)
    # Drives WhatsApp's 24-hour customer-service window: free-form replies
    # are only allowed for 24h after the customer's last message.
    last_inbound_at = models.DateTimeField(null=True, blank=True)
    unread_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    # Set the first time this conversation is handed out by the external
    # Leads API (services.api_views.NewLeadsView) — makes that delivery
    # one-time-only: once set, this contact never appears from that API
    # again, even if they message again later. Unrelated to the Messages
    # inbox, which always shows everything regardless of this flag.
    lead_delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("user", "contact_number")
        ordering = ["-last_message_at", "-id"]
        indexes = [models.Index(fields=["user", "-last_message_at"])]

    def __str__(self):
        return f"{self.user.username} <-> {self.contact_number}"


class ChatMessage(models.Model):
    """A single WhatsApp message (either direction) inside a Conversation."""
    DIRECTION_CHOICES = Conversation.DIRECTION_CHOICES
    STATUS_CHOICES = [
        ("received", "Received"),
        ("sent", "Sent"),
        ("delivered", "Delivered"),
        ("read", "Read"),
        ("failed", "Failed"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="chat_messages")
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    direction = models.CharField(max_length=3, choices=DIRECTION_CHOICES)
    message_type = models.CharField(max_length=20, default="text")

    # Text, or the caption / a short description for non-text messages.
    body = models.TextField(blank=True)
    media_id = models.CharField(max_length=255, blank=True)
    media_mime = models.CharField(max_length=100, blank=True)
    filename = models.CharField(max_length=255, blank=True)
    # The raw inbound message, or the payload we sent — kept so nothing is lost.
    payload = models.JSONField(default=dict, blank=True)

    # Meta's message id. Unique so a re-delivered webhook can't duplicate a
    # message; null for sends that failed before Meta assigned one.
    wamid = models.CharField(max_length=200, unique=True, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="received")
    # Where an outgoing message came from: chat / campaign / flow / api / app.
    source = models.CharField(max_length=20, blank=True)
    error_message = models.TextField(blank=True)

    timestamp = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    # Set once this exact message has been handed out by the external Leads
    # API's no-`reengage_after_days` mode (services.api_views.NewLeadsView),
    # where every inbound message is its own one-time lead. Unrelated to
    # Conversation.lead_delivered_at, which is what reengage_after_days uses.
    lead_delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["timestamp", "id"]
        indexes = [models.Index(fields=["conversation", "timestamp"])]

    def __str__(self):
        return f"{self.direction} {self.message_type} {self.wamid or ''}"
