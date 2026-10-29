from django.shortcuts import render

# Create your views here.
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from .models import UserProfile
from .forms import UserDetailForm, UserProfileForm

# views.py
import random
import string
import json
import logging
from django.core.cache import cache
import requests

from django.conf import settings
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.http import JsonResponse

from django.contrib.auth import get_user_model, login
from django.contrib.auth.backends import ModelBackend
from rest_framework.authtoken.models import Token

from billing import services as billing



from django.contrib.auth import login

logger = logging.getLogger(__name__)

@login_required
def user_detail_view(request):
    user = request.user

    # Ensure the user has a profile
    profile, created = UserProfile.objects.get_or_create(user=user)
    api_token, _ = Token.objects.get_or_create(user=user)

    if request.method == 'POST':
        user_form = UserDetailForm(request.POST, instance=user)
        profile_form = UserProfileForm(request.POST, instance=profile)
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, "Your profile has been updated successfully.")
            return redirect('user_detail')  # Replace with your URL name
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        user_form = UserDetailForm(instance=user)
        profile_form = UserProfileForm(instance=profile)

    api_rate_limit = billing.get_api_rate_limit(user)

    return render(request, 'user_detail.html', {
        'user_form': user_form,
        'profile_form': profile_form,
        'META_APP_ID': settings.META_APP_ID,
        'META_CONFIG_ID': settings.META_CONFIG_ID,
        'api_token': api_token.key,
        'api_rate_limit': api_rate_limit,
        'has_api_access': api_rate_limit is None or api_rate_limit > 0,
    })


@login_required
@require_POST
def regenerate_api_token(request):
    Token.objects.filter(user=request.user).delete()
    Token.objects.create(user=request.user)
    messages.success(request, "Your API token has been regenerated. Update anywhere the old one was used.")
    return redirect('user_detail')


@login_required
@require_POST
def update_avatar(request):
    photo = request.FILES.get('avatar')
    if not photo:
        return JsonResponse({'success': False, 'error': 'No file was uploaded.'}, status=400)

    if not photo.content_type.startswith('image/'):
        return JsonResponse({'success': False, 'error': 'Please upload an image file (JPG or PNG).'}, status=400)

    max_bytes = 2 * 1024 * 1024  # 2MB, matches the hint shown on the profile page
    if photo.size > max_bytes:
        return JsonResponse({'success': False, 'error': 'Image must be 2MB or smaller.'}, status=400)

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    profile.avatar = photo
    profile.save()
    return JsonResponse({'success': True, 'avatar_url': profile.avatar.url})


@login_required
@require_POST
def whatsapp_embedded_signup_callback(request):
    """
    Receives the `code` (from the FB.login() JS callback) and the `data`
    payload (from the WA_EMBEDDED_SIGNUP postMessage event) sent by the
    embedded signup button on the profile page, exchanges the code for an
    access token, and stores the customer's own WABA/phone number/token on
    their UserProfile so all later template/campaign calls run against
    their own WhatsApp Business Account.

    https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/implementation
    """
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "message": "Invalid JSON payload."}, status=400)

    code = body.get("code")
    data = body.get("data") or {}
    event_type = body.get("event")  # e.g. FINISH, FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING (Coexistence)
    waba_id = data.get("waba_id")
    phone_number_id = data.get("phone_number_id")
    business_id = data.get("business_id")
    is_coexistence = event_type == "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING"

    if not code:
        return JsonResponse({"success": False, "message": "Missing authorization code."}, status=400)
    if not waba_id:
        return JsonResponse({"success": False, "message": "Missing waba_id."}, status=400)
    # Coexistence's FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING payload only ever
    # contains waba_id — no phone_number_id/business_id — because the number
    # was already registered before onboarding. We look phone_number_id up
    # below once we have a token. For every other flow it's required upfront.
    if not is_coexistence and not phone_number_id:
        return JsonResponse({"success": False, "message": "Missing phone_number_id."}, status=400)

    graph_version = settings.META_GRAPH_API_VERSION

    # Step 1: Exchange the authorization code for an access token that can
    # manage the customer's WABA (granted to our app during signup).
    token_response = requests.get(
        f"https://graph.facebook.com/{graph_version}/oauth/access_token",
        params={
            "client_id": settings.META_APP_ID,
            "client_secret": settings.META_APP_SECRET,
            "code": code,
        },
    )
    token_data = token_response.json()
    access_token = token_data.get("access_token")

    if not access_token:
        logger.error("Embedded signup token exchange failed: %s", token_data)
        return JsonResponse({
            "success": False,
            "message": "Could not exchange authorization code for an access token.",
            "details": token_data,
        }, status=400)

    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    # Coexistence never gives us phone_number_id directly — look it up from
    # the WABA now that we have a token that can read it.
    if is_coexistence and not phone_number_id:
        try:
            numbers_response = requests.get(
                f"https://graph.facebook.com/{graph_version}/{waba_id}/phone_numbers",
                headers=headers,
            )
            numbers_data = numbers_response.json().get("data", [])
            if numbers_data:
                phone_number_id = numbers_data[0].get("id")
            logger.info("Looked up phone number for Coexistence WABA %s: %s", waba_id, numbers_data)
        except Exception as e:
            logger.warning("Could not look up phone number for WABA %s: %s", waba_id, e)

        if not phone_number_id:
            return JsonResponse({
                "success": False,
                "message": "Connected to Facebook, but could not find a phone number on this WhatsApp Business Account.",
            }, status=400)

    # Step 2: Subscribe our app to this WABA so we receive webhooks
    # (messages, statuses) for this customer's number. Not fatal if it fails.
    try:
        subscribe_response = requests.post(
            f"https://graph.facebook.com/{graph_version}/{waba_id}/subscribed_apps",
            headers=headers,
        )
        logger.info("Subscribed app to WABA %s: %s", waba_id, subscribe_response.text)
    except Exception as e:
        logger.warning("Could not subscribe app to WABA %s: %s", waba_id, e)

    # Step 3: Register the phone number for Cloud API messaging.
    # Only for brand-new numbers. A Coexistence number is already active on
    # the WhatsApp Business app with its own 2-step-verification PIN set by
    # the business — calling /register here would generate a new random PIN
    # and overwrite theirs, potentially locking them out of the app they're
    # still using. Skip it for Coexistence completions.
    if is_coexistence:
        logger.info(
            "Skipping /register for WABA %s / phone %s — Coexistence signup, number already active.",
            waba_id, phone_number_id,
        )

        # Step 3b: Kick off the one-time contacts + message-history sync.
        # Meta requires this be done within 24 hours of onboarding and only
        # once per onboarding cycle — the actual contacts/messages arrive
        # later as `smb_app_state_sync` / `history` webhooks (make sure both
        # of those, plus `smb_message_echoes`, are subscribed in the App
        # Dashboard's WhatsApp webhook fields — this call alone won't do
        # anything unless they are).
        for sync_type in ("smb_app_state_sync", "history"):
            try:
                sync_response = requests.post(
                    f"https://graph.facebook.com/{graph_version}/{phone_number_id}/smb_app_data",
                    headers=headers,
                    json={"messaging_product": "whatsapp", "sync_type": sync_type},
                )
                logger.info("Requested %s sync for phone %s: %s", sync_type, phone_number_id, sync_response.text)
            except Exception as e:
                logger.warning("Could not request %s sync for phone %s: %s", sync_type, phone_number_id, e)
    else:
        try:
            pin = "".join(random.choices(string.digits, k=6))
            register_response = requests.post(
                f"https://graph.facebook.com/{graph_version}/{phone_number_id}/register",
                headers=headers,
                json={"messaging_product": "whatsapp", "pin": pin},
            )
            logger.info("Registered phone number %s: %s", phone_number_id, register_response.text)
        except Exception as e:
            logger.warning("Could not register phone number %s: %s", phone_number_id, e)

    # Step 4: The postMessage payload only ever carries IDs (waba_id,
    # phone_number_id) — the actual WhatsApp number isn't in it, so it has to
    # be fetched separately or the profile's Phone field stays empty forever.
    display_phone_number = None
    try:
        number_response = requests.get(
            f"https://graph.facebook.com/{graph_version}/{phone_number_id}",
            headers=headers,
            params={"fields": "display_phone_number"},
        )
        display_phone_number = number_response.json().get("display_phone_number")
        logger.info("Fetched display phone number for %s: %s", phone_number_id, display_phone_number)
    except Exception as e:
        logger.warning("Could not fetch display phone number for %s: %s", phone_number_id, e)

    # Step 5: Persist the customer's own WABA credentials on their profile.
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    profile.wba_id = waba_id
    profile.phone_number_id = phone_number_id
    profile.business_id = business_id
    profile.api_key = access_token
    profile.app_id = settings.META_APP_ID
    profile.meta_connected_at = timezone.now()
    if display_phone_number:
        profile.phone_number = display_phone_number
    profile.save()

    return JsonResponse({
        "success": True,
        "message": "WhatsApp Business Account connected successfully.",
        "waba_id": waba_id,
        "phone_number_id": phone_number_id,
        "phone_number": display_phone_number,
    })



def send_otp_view(request):
    if request.method == 'POST':
        phone = request.POST.get('phone')
        if not phone:
            messages.error(request, 'Phone number is required.')
            return redirect('send_otp')

        otp = str(random.randint(100000, 999999))
        cache.set(f'otp_{phone}', otp, timeout=300)

        try:
            response = requests.post(
                "https://graph.facebook.com/v22.0/674293212423873/messages",  # Replace with your ID
                headers={
                    "Authorization": "Bearer EAAzBJcs4opgBO8XI1hFBNzwj0QQyzDj3ZAxeEIvd4Uh0GPEfFTWRTYzhqAZCV29sNJPy9lQXTVvHbTVWaKhX5OBodPpeRKDRi0qFJ1NY0DhH4ZBQTZCfFyR8KUFTDsdcpmTeh0cVGeSUcHKViofstRe99YUmSe2a1FNmqhjG5X0C4LFOUD5MnbJG7m4JurQZCi4o2uQSZCseluZBrS73AKKLoy60rSZAWZBsZD",  # Replace with your token
                    "Content-Type": "application/json"
                },
                json={
                    "messaging_product": "whatsapp",
                    "to": f"{phone}",
                    "type": "text",
                    "text": {"body": f"{otp} is your one-time OTP for login."}
                }
            )
            print("WhatsApp API Response:", response.status_code, response.text)
            if response.status_code == 200:
                request.session['otp_phone'] = phone
                messages.success(request, f"OTP sent to {phone}")
                return redirect('verify_otp')
            else:
                messages.error(request, "Failed to send OTP. Please try again.")
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
    return render(request,'account/whatsapp_send_otp.html')



def verify_otp_view(request):
    if request.method == 'POST':
        otp_entered = request.POST.get('otp')
        phone = request.session.get('otp_phone')

        if not phone:
            messages.error(request, 'Session expired. Please request OTP again.')
            return redirect('send_otp')

        expected_otp = cache.get(f'otp_{phone}')
        if expected_otp and otp_entered == expected_otp:
            User = get_user_model()
            user, created = User.objects.get_or_create(
                username=phone,
                defaults={'email': f'{phone}@whatsapp.local'}
            )
            # 👇 This line is critical when using multiple auth backends
            user.backend = 'django.contrib.auth.backends.ModelBackend'

            login(request, user)
            cache.delete(f'otp_{phone}')
            messages.success(request, 'Logged in successfully.')
            return redirect('services')
        else:
            messages.error(request, 'Invalid or expired OTP. Please try again.')

    return render(request, 'account/whatsapp_verify_otp.html')

# def handler_404(request, exception):
#     return render(request,'404.html', {})