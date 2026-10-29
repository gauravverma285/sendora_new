import re, json, requests, copy, mimetypes, sys, uuid
from django.conf import settings
from django.db import IntegrityError

# Customer Contacts
import pandas as pd
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import Contact, Tag, OptOutUser, GlobalOptOut, Campaign, CampaignMessage, Flow, FlowNode, FlowButton, ContactFlowState
# from .forms import ContactForm
from django.contrib.auth.decorators import login_required
from accounts.models import UserProfile  # Assuming user profile stores wba_id and api_key

from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.urls import reverse
from . import chat as chat_log  # Messages inbox: recording/reading chat messages
from billing import services as billing
from billing.pages import feature_required

from django.utils import timezone
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
# from datetime import datetime, timezone
from datetime import datetime, timedelta
import calendar
import json
# Create your views here.
from .tasks import run_scheduled_campaign
from .tasks import async_send_messages

# def create_template(request):
#     return render(request,'create_template.html')

# def design(request):
#     return render(request,'design.html')




@login_required
@feature_required('feature_templates')
def template_list(request):
    """Fetch and display WhatsApp message templates."""
    try:
        # Get API credentials from logged-in user's profile
        profile = UserProfile.objects.get(user=request.user)
        wba_id = profile.wba_id
        api_key = profile.api_key
        # print(wba_id)
        # print(api_key)
        # API URL
        url = f"https://graph.facebook.com/v22.0/{wba_id}/message_templates"

        # Headers
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        # Fetch data
        response = requests.get(url, headers=headers)
        response_data = response.json()
        # print("response-->", response)
        # Extract templates
        templates = response_data.get("data", [])
        print("templates-->", templates)

    except Exception as e:
        templates = []
        print("Error fetching templates:", e)

    approved_count = sum(1 for t in templates if t.get("status") == "APPROVED")
    rejected_count = sum(1 for t in templates if t.get("status") == "REJECTED")
    pending_count = len(templates) - approved_count - rejected_count

    return render(request, "template_list.html", {
        "templates": templates,
        "total_templates": len(templates),
        "approved_count": approved_count,
        "pending_count": pending_count,
        "rejected_count": rejected_count,
    })

@login_required
def view_template(request, template_id):
    profile = UserProfile.objects.get(user=request.user)
    api_key = profile.api_key
    wba_id = profile.wba_id

    url = f"https://graph.facebook.com/v22.0/{template_id}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(url, headers=headers)
        template = response.json()
    except Exception as e:
        template = {"error": str(e)}

    return render(request, "view_template.html", {
        "template": template,
        "ACCESS_TOKEN": api_key,
        "APP_ID": wba_id,
        "TEMPLATE_ID": template_id
    })

def rejected_templates(request):
    return render(request,'rejected_templates.html')

def edit_templates_rules(request):
    return render(request,'edit_templates_rules.html')

@login_required
def delete_template(request):
    if request.method == 'POST':
        try:
            # Extract template name from request
            data = json.loads(request.body)
            template_name = data.get("name")

            if not template_name:
                return JsonResponse({"success": False, "message": "Template name is required."})

            # Get user's API credentials
            profile = UserProfile.objects.get(user=request.user)
            wba_id = profile.wba_id
            api_key = profile.api_key

            # WhatsApp API endpoint for deleting a template
            url = f"https://graph.facebook.com/v22.0/{wba_id}/message_templates?name={template_name}"

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            # Send DELETE request
            response = requests.delete(url, headers=headers)

            if response.status_code == 200:
                return JsonResponse({"success": True, "message": f"Template '{template_name}' deleted successfully."})
            else:
                return JsonResponse({"success": False, "message": response.json()})

        except Exception as e:
            print("Error deleting template:", e)
            return JsonResponse({"success": False, "message": str(e)})

    return JsonResponse({"success": False, "message": "Invalid request method."})

# @csrf_exempt  # ⚠️ Not recommended for production
def upload_media(request):

    # Get button action from request
    action = request.GET.get("button")  # Can be 'upload' or 'process'

    # Assuming these values are stored in the user's profile
    profile = UserProfile.objects.get(user=request.user)
    access_token = profile.api_key  # Retrieve the API key
    app_id = profile.app_id  # Retrieve the WhatsApp Business Account ID
    phone_number_id = profile.phone_number_id


    print(app_id)
    print(access_token)
    if request.method == 'POST' and request.FILES.get('file'):
        file = request.FILES['file']
        access_token = access_token  # Replace with dynamic token
    
        if action == "upload":
            api_id = app_id  # Replace with dynamic ID

            # Step 1: Get Session ID from Facebook API
            session_url = f"https://graph.facebook.com/v22.0/{api_id}/uploads"
            params = {
                "file_length": file.size,
                "file_type": file.content_type
            }
            headers = {"Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"}

            session_response = requests.post(session_url, headers=headers, params=params)
            session_data = session_response.json()
            print("Session Response:", session_data)

            if "id" not in session_data:
                return JsonResponse({"error": "Failed to get session ID"}, status=400)

            session_id = session_data["id"]
            print("session_id--->", session_id)

            # Step 2: Upload the file to Facebook
            upload_url = f"https://graph.facebook.com/v22.0/{session_id}"
            headers = {"Authorization": f"OAuth {access_token}",
                    "Content-Type": "application/octet-stream"}
            # files = {"file": file}

            upload_response = requests.post(upload_url, headers=headers, data=file.read())
            upload_data = upload_response.json()

            print("upload_response-->", upload_response)
            print("upload_data-->", upload_data)
            print("upload_data['h']", upload_data["h"])
            # ✅ FIX: No need to check for "h" and return 400 if it exists
            if "h" in upload_data:
                h_value = upload_data["h"].split()[0]  # Extract only "h"
                print("h_value---> campaign wala -->", h_value)
                return JsonResponse({"h": h_value, "message": "Upload successful!"})

            # 🔴 If "h" is missing, return error
            return JsonResponse({"error": "Failed to upload media", "details": upload_data}, status=400)

        elif action == "process":
            # Perform alternative logic for second button
            api_id = phone_number_id
            url = f"https://graph.facebook.com/v22.0/{api_id}/media"
            headers = {
                "Authorization": f"Bearer {access_token}",
            }
            files = {
                "file": (file.name, file.read(), file.content_type),
            }
            data = {
                "messaging_product": "whatsapp",
            }

            response = requests.post(url, headers=headers, files=files, data=data)
            response_data = response.json()

            if "id" in response_data:
                print("id-->", id)
                return JsonResponse({"media_id": response_data["id"], "message": "Upload successful!"})

            return JsonResponse({"error": "Failed to upload media", "details": response_data}, status=400)

    return JsonResponse({"error": "Invalid request"}, status=400)


# @csrf_exempt  # Temporarily disabling CSRF for testing; remove this in production
def create_or_edit_template(request, template_id=None):

    # Assuming these values are stored in the user's profile
    profile = UserProfile.objects.get(user=request.user)
    access_token = profile.api_key  # Retrieve the API key
    app_id = profile.app_id  # Retrieve the WhatsApp Business Account ID
    print("template_id-->",template_id)
    is_edit = template_id is not None  # True if editing
    if request.method == "POST":
        try:
            # Collect basic details
            template_name = request.POST.get("template_name")
            # print(template_name)
            language = request.POST.get("language")
            # print(language)
            category = request.POST.get("category", "MARKETING")

            if category == "AUTHENTICATION":
                # Authentication templates have a fixed shape defined by Meta:
                # no header, no free-text body/footer (Meta generates that
                # text itself), and exactly one OTP button.
                # https://developers.facebook.com/docs/whatsapp/business-management-api/authentication-templates
                add_security_recommendation = request.POST.get("add_security_recommendation") == "on"
                body_component = {
                    "type": "BODY",
                    "add_security_recommendation": add_security_recommendation,
                }

                footer_component = None
                code_expiration_minutes = request.POST.get("code_expiration_minutes", "").strip()
                if code_expiration_minutes:
                    footer_component = {
                        "type": "FOOTER",
                        "code_expiration_minutes": int(code_expiration_minutes),
                    }

                otp_type = request.POST.get("otp_type", "COPY_CODE")
                otp_button_text = request.POST.get("otp_button_text", "Copy Code")
                button_component = {
                    "type": "BUTTONS",
                    "buttons": [{
                        "type": "OTP",
                        "otp_type": otp_type,
                        "text": otp_button_text,
                    }],
                }

                components = [comp for comp in [body_component, footer_component, button_component] if comp]

            else:
                # Process header
                header_type = request.POST.get("header_type", "none")  # none, text, image, video, document
                if header_type != "None":
                    if header_type == "text":
                        header_content = request.POST.get("header_text", "")  # Only used if text header
                    sample_content_header = request.POST.getlist("sample_values_headers")
                    print("sample_content_header",sample_content_header)
                print(header_type)
                header_component = None
                if header_type != "none":
                    header_component = {
                        "type": "HEADER",
                        "format": header_type.upper(),
                    }
                    if header_type == "text":
                        header_component["text"] = header_content  # Add text content if type is text
                        if sample_content_header:
                            header_component["example"] = {
                                "header_text" : sample_content_header
                            }
                    elif header_type in ["image", "video", "document"]:
                        if sample_content_header:
                            header_component["example"] = {
                                "header_handle" : sample_content_header
                            }
                # Process body
                body_text = request.POST.get("body_text")
                sample_content_body = request.POST.getlist("sample_values_body")
                print(body_text)
                print(sample_content_body)
                body_component = {
                    "type": "BODY",
                    "text": body_text,
                }
                if sample_content_body:
                    body_component["example"] = {
                        "body_text":[sample_content_body]
                    }


                # Process footer (optional)
                footer_text = request.POST.get("footer_text", "")
                footer_component = None
                if footer_text:
                    footer_component = {
                        "type": "FOOTER",
                        "text": footer_text,
                    }


                # Process buttons
                # Fetch button types first
                button_types = request.POST.getlist("button_type[]")  # ['QUICK_REPLY', 'URL', 'PHONE_NUMBER', ...]

                # Get all button texts

                button_texts = request.POST.getlist("button_text[]")
                button_urls = request.POST.getlist("button_url[]")
                button_phone_numbers = request.POST.getlist("button_phone_number[]")
                button_copy_example = request.POST.getlist("button_copy_example")
                # button_examples = request.POST.getlist("button_example[]")
                # Fetch all button example fields dynamically
                button_examples = {}
                for key in request.POST.keys():
                    if key.startswith("button_example_"):  # Capture all example fields
                        button_examples[key] = request.POST.getlist(key)

                # Construct button JSON structure
                buttons = []
                url_index = 0
                phone_index = 0
                example_index = 0
                example_copy_index = 0
                url_example_index = 0

                for i, button_type in enumerate(button_types):
                    button_data = {"type": button_type, "text": button_texts[i]}

                    if button_type == "URL":
                        original_url = button_urls[url_index]
                        button_data["url"] = original_url.rstrip("/")  # Remove trailing slash if exists

                        url_index += 1  # Move to next URL

                        # Extract {{x}} placeholders from the URL
                        url_variables = re.findall(r"\{\{([\w\d]+)\}\}", button_data["url"])  # Extract numeric placeholders
                        print(url_variables)


                        formatted_url = button_data["url"]
                        if len(url_variables) > 0:
                            for i in range(1, len(url_variables) + 1):
                                replacement_value = button_examples[f"button_example_{i}[]"][url_example_index]
                                formatted_url = formatted_url.replace(f"{{{{{url_variables[i - 1]}}}}}", replacement_value)  # Replace in URL
                            url_example_index += 1
                            button_data["example"] = [formatted_url]

                    elif button_type == "PHONE_NUMBER":
                        button_data["phone_number"] = button_phone_numbers[phone_index]
                        phone_index += 1  # Move to next phone number

                    elif button_type == "COPY_CODE":
                        if example_index < len(button_examples):
                            button_data["example"] = [button_copy_example[example_copy_index]]
                            example_copy_index += 1  # Move to next example

                    buttons.append(button_data)

                # **Sorting Buttons** - Quick Replies first, then others
                buttons.sort(key=lambda b: b["type"] != "QUICK_REPLY")
                # Final button JSON payload
                button_component = {
                    "type": "BUTTONS",
                    "buttons": buttons
                }

                # print("Final button_component:", button_component)  # Debugging
                # Construct components list
                components = [comp for comp in [header_component, body_component, footer_component] if comp]
                if buttons:
                    components.append(button_component)

            # Prepare final JSON payload
            payload = {
                "name": template_name,
                "language": language,
                "category": category,
                "components": components,
            }
            print("payload:--->", payload)
                # Get API credentials from logged-in user's profile
            profile = UserProfile.objects.get(user=request.user)
            wba_id = profile.wba_id
            api_key = profile.api_key
            # print(wba_id)
            # print(api_key)
            # API URL
            # api_url = f"https://graph.facebook.com/v22.0/{wba_id}/message_templates"

            if is_edit:
                api_url = f"https://graph.facebook.com/v22.0/{template_id}"
                print("edit-->")
                # method = requests.post  # Meta may not allow PUT/PATCH for templates
            else:
                api_url = f"https://graph.facebook.com/v22.0/{wba_id}/message_templates"
                print("edit not-->")
                # method = requests.post

            # Headers
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            response = requests.post(api_url, data=json.dumps(payload), headers=headers)
            print("response--->", response.text)
            if response.status_code == 200:
                return JsonResponse({"status": "success", "message": "Template created successfully!"})
            else:
                # Surface Meta's actual error message (e.g. "Param
                # components[3]['buttons'][1]['phone_number'] is not a valid
                # phone number.") instead of a generic, unactionable message.
                try:
                    error_message = response.json().get("error", {}).get("message", "API request failed.")
                except ValueError:
                    error_message = "API request failed."
                return JsonResponse({"status": "error", "message": error_message, "details": response.text})

        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)})

    return render(request, "create_template.html",{"ACCESS_TOKEN": access_token,
        "APP_ID": app_id, "is_edit": is_edit,"TEMPLATE_ID": template_id})


@csrf_exempt
@login_required
def toggle_opt_out(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            enabled = data.get("enabled", False)

            opt_out_entry, created = GlobalOptOut.objects.update_or_create(
                user=request.user,
                defaults={"is_enabled": enabled}
            )

            return JsonResponse({"success": True, "enabled": enabled})
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
    return JsonResponse({"error": "Invalid request method"}, status=405)



def add_contact(request):
    if request.method == "POST":
        # File upload handling
        if request.FILES.get("file"):

            file = request.FILES["file"]
            print("Received file:", file.name)
            try:
                if file.name.lower().endswith(".csv"):
                    df = pd.read_csv(file, dtype=str)
                else:
                    df = pd.read_excel(file, dtype=str)  # Read Excel and ensure all data is string

                # Debugging: Print DataFrame to verify structure
                print("File Data:\n", df)  # Print entire dataframe

                # Check if required columns exist
                required_columns = {"Mobile Number"}
                missing_columns = required_columns - set(df.columns)
                if missing_columns:
                    messages.error(request, f"Missing columns: {', '.join(missing_columns)}")
                    print("Error: Missing columns", missing_columns)  # Debugging
                    return redirect("contacts_list")
                # Ensure 'Age', 'Email' and 'Tags' are present for safe access
                df["Age"] = df.get("Age", None)
                df["Email"] = df.get("Email", "")
                df["Tags"] = df.get("Tags", "")

                # Cache user-specific tags to avoid multiple DB hits
                user_tags = {tag.name: tag for tag in Tag.objects.filter(user=request.user)}

                # Plan limit — checked once up front, then tracked as we go
                # so an import that would cross the limit partway through
                # stops adding NEW contacts (updates to existing ones are
                # always allowed; they don't grow the count).
                contact_count = Contact.objects.filter(user=request.user).count()
                plan = billing.get_active_plan(request.user)
                contact_limit = plan.limit(billing.MAX_CONTACTS, default=0) if plan else 0

                skipped_no_country_code = 0
                skipped_over_limit = 0

                # Loop through rows and save contacts
                # Save contacts
                for index, row in df.iterrows():
                    name = str(row["Name"]).strip()
                    mobile_number = str(row["Mobile Number"]).strip()

                    # Skip empty rows
                    # if not name or not mobile_number:
                    if not mobile_number:
                        print(f"Skipping row {index} due to missing Mobile Number")  # Debugging
                        continue

                    # Require a country code (e.g. +919876543210) — a bare
                    # local number like 9876543210 is ambiguous and will fail
                    # to send via the WhatsApp API, so reject it here instead
                    # of saving a contact that can never be messaged.
                    if not re.match(r'^\+[1-9]\d{6,14}$', mobile_number):
                        skipped_no_country_code += 1
                        print(f"Skipping row {index}: '{mobile_number}' is missing a country code")
                        continue

                    # Handle optional fields safely
                    age = int(row["Age"]) if pd.notna(row.get("Age")) and row["Age"].strip() else None
                    email = str(row["Email"]).strip() if pd.notna(row.get("Email")) else ""
                    tags_str = str(row["Tags"]).strip() if pd.notna(row.get("Tags")) else ""

                    tag_objects = []
                    if tags_str:
                        tag_names = [tag.strip() for tag in tags_str.split(",")]
                        for tag_name in tag_names:
                            if tag_name not in user_tags:
                                # if tag not present then it will create
                                user_tags[tag_name], _ = Tag.objects.get_or_create(user=request.user, name=tag_name)
                            tag_objects.append(user_tags[tag_name])

                    is_new = not Contact.objects.filter(user=request.user, mobile_number=mobile_number).exists()
                    if is_new and contact_limit is not None and contact_count >= contact_limit:
                        skipped_over_limit += 1
                        continue

                    try:
                        # Create or update contact
                        # Looked up by (user, number) — never by number alone,
                        # otherwise importing a number another account already
                        # has would re-assign THEIR contact to this account.
                        contact, created = Contact.objects.update_or_create(
                            user=request.user,
                            mobile_number=mobile_number,
                            defaults={
                                "name": name,
                                "age": age,
                                "email": email or None,
                            },
                        )
                        # Associate tags
                        if tag_objects:
                            contact.tags.set(tag_objects)

                        if created:
                            contact_count += 1

                        action = "Created" if created else "Updated"
                        print(f"{action} contact: {name}, {mobile_number}, Age={age}, Tags={tags_str}")

                    except IntegrityError:
                        messages.error(request, f"Row {index}: Duplicate mobile number '{mobile_number}'")
                        print(f"Duplicate mobile number at row {index}: {mobile_number}")

                if skipped_over_limit:
                    messages.error(
                        request,
                        f"{skipped_over_limit} contact(s) were skipped: your plan allows up to {contact_limit} "
                        f"contacts. Upgrade your plan to upload more."
                    )
                if skipped_no_country_code:
                    messages.error(
                        request,
                        f"{skipped_no_country_code} contact(s) were skipped: mobile number must include a country "
                        f"code (e.g. +919876543210), not a bare number like 9876543210. Fix those rows and re-upload."
                    )
                messages.success(request, "Contacts uploaded successfully!")
                return redirect("contacts_list")

            except Exception as e:
                messages.error(request, f"Error processing file: {e}")
                print("Error processing file:", e)  # Debugging
                return redirect("contacts_list")

        
        # Manual form submission handling
        else:
            name = request.POST.get('name')
            mobile_number = request.POST.get('mobile_number')
            email = request.POST.get('email', '').strip()
            age = request.POST.get('age')

            # ✅ Ensure age is either an integer or None
            age = int(age) if age else None

            tag_ids = request.POST.getlist('tags')  # Get multiple tag values

            errors = {}

            # Validate name and mobile number (required fields)
            # if not name:
            #     errors['name'] = "Name is required."
            if not mobile_number:
                errors['mobile_number'] = "Mobile number is required."

            # Validate age (optional but must be positive if provided)
            if age:
                try:
                    age = int(age)
                    if age < 0:
                        errors['age'] = "Age cannot be negative."
                except ValueError:
                    errors['age'] = "Age must be a valid number."

            current_contacts = Contact.objects.filter(user=request.user).count()
            allowed, limit = billing.check_limit(request.user, billing.MAX_CONTACTS, current_contacts)
            if not allowed:
                errors['mobile_number'] = f"Your plan allows up to {limit} contacts. Upgrade your plan to add more."

            # If there are validation errors, re-render the form with errors
            if errors:
                tags = Tag.objects.filter(user=request.user)
                return render(request, "add_contact.html", {
                    "tags": tags,
                    "errors": errors,
                    "form_data": {
                        "name": name,
                        "mobile_number": mobile_number,
                        "email": email,
                        "age": age,
                        "tag_ids": tag_ids,
                    }
                })
            # Try to save the contact and handle unique constraint violation
        try:
            contact = Contact.objects.create(
                name=name,
                mobile_number=mobile_number,
                email=email or None,
                age=age,
                user=request.user
            )
            contact.tags.set(Tag.objects.filter(id__in=tag_ids))

            messages.success(request, "Contacts uploaded successfully!")
            return redirect("contacts_list")

        except IntegrityError as e:
            if 'mobile_number' in str(e):
                errors['mobile_number'] = "You already have a contact with this mobile number."
            else:
                errors['database'] = "An unexpected error occurred. Please try again."

            # Re-render form with error
            tags = Tag.objects.filter(user=request.user)
            return render(request, "add_contact.html", {
                "tags": tags,
                "errors": errors,
                "form_data": {
                    "name": name,
                    "mobile_number": mobile_number,
                    "email": email,
                    "age": age,
                    "tag_ids": tag_ids,
                }
            })
    # else:
    #     form = ContactForm(user=request.user)

    tags = Tag.objects.filter(user=request.user)  # User-specific tags
    return render(request, "add_contact.html", {"tags": tags})


@feature_required('feature_contacts')
def contacts_list(request):
    # Filter contacts by the logged-in user
    contacts = Contact.objects.filter(user=request.user).prefetch_related('tags')
    tags = Tag.objects.filter(user=request.user)  # Get user-specific tags
    print("tags-->", tags)
    
    tag_filter = request.GET.get("tag", "")
    age_filter = request.GET.get("age_filter", "")
    age_value = request.GET.get("age_value")
    age_value_2 = request.GET.get("age_value_2")


    # Filter by tag
    if tag_filter:
        contacts = contacts.filter(tags__name__icontains=tag_filter)

    # Filter by age
    if age_value and age_value.isdigit():
        age_value = int(age_value)
        if age_filter == "greater":
            contacts = contacts.filter(age__gt=age_value)
        elif age_filter == "smaller":
            contacts = contacts.filter(age__lt=age_value)
        elif age_filter == "between" and age_value_2 and age_value_2.isdigit():
            contacts = contacts.filter(age__gte=age_value, age__lte=int(age_value_2))

    if request.method == "POST":
        contact_ids = request.POST.getlist('contact_ids')
        if contact_ids:
            Contact.objects.filter(id__in=contact_ids, user=request.user).delete()
        return redirect('contacts_list')
    # Fetch global opt-out setting for the user
    # opt_out_entry = OptOutUser.objects.filter(user=request.user).first()
    # global_opt_out_enabled = opt_out_entry.is_enabled if opt_out_entry else True
    opt_out_entry = GlobalOptOut.objects.filter(user=request.user).first()
    global_opt_out_enabled = opt_out_entry.is_enabled if opt_out_entry else False

    all_contacts = Contact.objects.filter(user=request.user)
    total_contacts = all_contacts.count()
    with_tags_count = all_contacts.filter(tags__isnull=False).distinct().count()
    without_tags_count = total_contacts - with_tags_count
    opted_out_count = OptOutUser.objects.filter(user=request.user).count()

    return render(request, "contacts_list.html", {
        "contacts": contacts,
        "tags": tags,
        "global_opt_out_enabled": global_opt_out_enabled,
        "total_contacts": total_contacts,
        "with_tags_count": with_tags_count,
        "without_tags_count": without_tags_count,
        "opted_out_count": opted_out_count,
    })

@csrf_exempt
@login_required
def update_contact(request, contact_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            # Scoped to the signed-in account: without this, any contact id
            # (from any account, even logged out) could be edited.
            contact = Contact.objects.get(id=contact_id, user=request.user)

            contact.name = data.get('name', contact.name)
            contact.mobile_number = data.get('mobile_number', contact.mobile_number)
            contact.email = data.get('email', contact.email) or None

            age_value = data.get('age', contact.age)
            if age_value in (None, ''):
                contact.age = None
            else:
                try:
                    contact.age = int(age_value)
                except (TypeError, ValueError):
                    return JsonResponse({'error': "Age must be a valid number."}, status=400)

            contact.save()

            if 'tags' in data:
                tag_ids = data.get('tags') or []
                contact.tags.set(Tag.objects.filter(id__in=tag_ids, user=contact.user))

            return JsonResponse({'success': True})
        except Contact.DoesNotExist:
            return JsonResponse({'error': 'Contact not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return JsonResponse({'error': 'Invalid request'}, status=400)


def create_message_sending_payload(template, final_data):
    
    output_components = []
    # Process HEADER
    for comp in template["components"]:
        if comp["type"] == "HEADER":
            header_parameters = []
            if "example" in comp:
                if comp["format"] == "TEXT":
                    for i in range(len(comp["example"]["header_text"])):
                        if final_data["header_info"][f"header_tag_{i+1}"]:
                            header_parameters.append({"type": "text", "text": f"{final_data["header_info"][f"header_tag_{i+1}"]}_tag"})
                        else:
                            header_parameters.append({"type": "text", "text": final_data["header_info"][f"header_value_{i+1}"]})
                else:
                    # link = comp["example"]["header_handle"][0]
                    id = final_data["header_info"]["header_value"]
                    if not id:
                        raise ValueError(
                            f"Please upload a {comp['format'].lower()} file for the header and wait for "
                            f"the upload to finish (the 'Upload' button) before sending — no media was attached."
                        )
                    if comp["format"] == "IMAGE":
                        header_parameters.append({"type": comp["format"].lower(), f"{comp["format"]}".lower():{"id":id}})
                    elif comp["format"] == "DOCUMENT":
                        # caption = final_data["header_info"]["header_caption"]
                        filename = final_data["header_info"]["header_file_name"]
                        header_parameters.append({"type": comp["format"].lower(), f"{comp["format"]}".lower():{"id":id,"filename":filename}}) # no caption required for template doc messsage
                        # header_parameters.append({"type": comp["format"].lower(), f"{comp["format"]}".lower():{"id":id,"caption":caption,"filename":filename}})
                    elif comp["format"] == "VIDEO":
                        # caption = final_data["header_info"]["header_caption"]
                        header_parameters.append({"type": comp["format"].lower(), f"{comp["format"]}".lower():{"id":id}}) # no caption required for template video messsage
                        # header_parameters.append({"type": comp["format"].lower(), f"{comp["format"]}".lower():{"id":id,"caption":caption}})
            elif comp["format"] == "LOCATION":
                latitude = final_data["header_info"]["header_latitude"]
                longitude = final_data["header_info"]["header_longitude"]
                name = final_data["header_info"]["header_location_name"]
                address = final_data["header_info"]["header_location_address"]
                header_parameters.append({"type": comp["format"].lower(), f"{comp["format"]}".lower():{"latitude":latitude,"longitude":longitude,"name":name,"address":address}})

            output_components.append({
                "type": "HEADER",
                "parameters": header_parameters
            })

    # Process BODY (required)
    for comp in template["components"]:
        if comp["type"] == "BODY":
            body_parameters = []
            if "example" in comp:
                for i in range(len(comp["example"]["body_text"][0])):
                    if final_data["body_info"][f"body_tag_{i+1}"]:
                        body_parameters.append({"type": "text", "text": f"{final_data["body_info"][f"body_tag_{i+1}"]}_tag"})
                    else:
                        body_parameters.append({"type": "text", "text": final_data["body_info"][f"body_value_{i+1}"]})
            output_components.append({
                "type": "BODY",
                "parameters": body_parameters
            })

    # Process BUTTONS
    for comp in template["components"]:
        if comp["type"] == "BUTTONS":
            for index, button in enumerate(comp["buttons"]):
                if button["type"] == "URL":
                    button_parameters = []
                    if "example" in button:
                        # url_template = button["url"]
                        # example_url = button["example"][0]
                        

                        # url_template_parts = button["url"].split("/")
                        # example_url_parts = button["example"][0].split("/")
                        
                        # variable_match = {}
                        # for i in range(len(url_template_parts)):
                        #     if "{{" in url_template_parts[i]:
                        #         variable_match[url_template_parts[i]] = example_url_parts[i]
                        
                        # for i in variable_match:
                        button_parameters.append({"type": "text", "text": final_data["buttons_info"][f"button_value_{index}_URL"] })
                        # A static URL button (no variable in the URL) needs no
                        # entry in components at all — Meta rejects a bare
                        # {"type":"BUTTON","sub_type":"URL",...} with no
                        # parameters (#132018 "does not require parameters").
                        output_components.append({
                            "type": "BUTTON",
                            "sub_type": "URL",
                            "index": index,
                            "parameters": button_parameters,
                        })
                elif button["type"] == "QUICK_REPLY":
                    output_components.append({
                        "type": "BUTTON",
                        "sub_type": "QUICK_REPLY",
                        "index": index, 
                    })
                elif button["type"] == "PHONE_NUMBER":
                    output_components.append({
                        "type": "BUTTON",
                        "sub_type": "VOICE_CALL",
                        "index": index, 
                    })
                elif button["type"] == "COPY_CODE":
                    output_components.append({
                        "type": "BUTTON",
                        "sub_type": "COPY_CODE",
                        "index": index, 
                        "parameters": [{"type": "coupon_code", "coupon_code": final_data["buttons_info"]["button_value_COPY_CODE"]
                                        }]

                    })
                

    # final_comp = json.dumps(output_components)
    return(output_components)



def send_message_to_user(payload, recipients, final_data, user, campaign=None):
    """Send `payload` to every recipient in `recipients` (a list of
    (name, mobile_number) pairs).

    When `campaign` is given, each send is logged as a CampaignMessage
    (keyed on the wamid Meta returns) so the webhook can later attribute
    delivered/read/failed status updates back to this exact campaign —
    that's what campaign_analytics is built from. `campaign` is left None
    for one-off test sends (the campaign wizard's "Send test message"),
    which shouldn't show up in any campaign's analytics.
    """
    try:
        print("Sending Payload:", payload)
        print("Recipients:", recipients)

        # Fetch UserProfile for phone_number_id and api_key
        profile = UserProfile.objects.get(user=user)
        phone_number_id = profile.phone_number_id
        api_key = profile.api_key

        if not (phone_number_id and api_key):
            raise ValueError("Missing phone_number_id or API key.")

        sending_message_url = f"https://graph.facebook.com/v22.0/{phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        responses = []

        for num in recipients:
            print("num-->", num)
            print("num[1]-->", num[1])

            # Create a unique copy of payload for each recipient
            user_payload = copy.deepcopy(payload)
            user_payload["to"] = num[1]  # Set recipient phone number
            print("num[1]-->", num[1])
            # payload["to"] = num[1]

            # replacing tags — only template messages use this variable system
            if user_payload.get("type") == "template":
                for ch in user_payload["template"]["components"]:
                    if ch["type"] == "HEADER":
                        if "parameters" in ch and len(ch["parameters"]):
                            print("length bta:",len(ch["parameters"]))
                            print("cuasing header")

                            for i, param in enumerate(ch.get('parameters')):
                                if "text" in param:
                                    if param["text"] == "name_tag" and num[0]:
                                        param["text"] = num[0]
                                    elif param["text"] == "phone_number_tag" and num[1]:
                                        param["text"] = num[1]
                                    else:
                                        param["text"] = final_data["header_info"].get(f"header_value_{i+1}", "")

                    elif ch["type"] == "BODY":
                        if "parameters" in ch and len(ch["parameters"]):
                            print("length bta:",len(ch["parameters"]))
                            print("cuasing body")
                            for i, param in enumerate(ch.get('parameters')):
                                if "text" in param:
                                    if param["text"] == "name_tag" and num[0]:
                                        param["text"] = num[0]
                                    elif param["text"] == "phone_number_tag" and num[1]:
                                        param["text"] = num[1]
                                    else:
                                        param["text"] = final_data["body_info"].get(f"body_value_{i+1}", "")
            elif final_data.get("personalize") and num[0]:
                # Text/image/document/interactive campaigns: swap a literal
                # "{{name}}" placeholder for the recipient's own name instead
                # of Meta's template-variable system (they don't have one).
                recipient_name = num[0]
                if user_payload.get("type") == "text":
                    user_payload["text"]["body"] = user_payload["text"]["body"].replace("{{name}}", recipient_name)
                elif user_payload.get("type") == "image" and "caption" in user_payload.get("image", {}):
                    user_payload["image"]["caption"] = user_payload["image"]["caption"].replace("{{name}}", recipient_name)
                elif user_payload.get("type") == "document" and "caption" in user_payload.get("document", {}):
                    user_payload["document"]["caption"] = user_payload["document"]["caption"].replace("{{name}}", recipient_name)
                elif user_payload.get("type") == "interactive":
                    body = user_payload.get("interactive", {}).get("body", {})
                    if "text" in body:
                        body["text"] = body["text"].replace("{{name}}", recipient_name)

            # replacing tags

            print("aakhri_payload-->",user_payload)
            response = requests.post(sending_message_url, json=user_payload, headers=headers)
            try:
                response_json = response.json()
            except ValueError:
                response_json = {}
            print(f"Sent to {num}: {response.status_code} - {response_json}")

            responses.append({
                "number": num,
                "status": response.status_code,
                "response": response_json
            })

            if campaign is not None:
                if response.status_code == 200:
                    sent_messages = response_json.get("messages") or []
                    wamid = sent_messages[0].get("id") if sent_messages else None
                    CampaignMessage.objects.create(
                        campaign=campaign, user=user,
                        contact_name=num[0] or "", mobile_number=num[1],
                        wamid=wamid, status="sent", sent_at=timezone.now(),
                    )
                else:
                    api_error = response_json.get("error", {})
                    CampaignMessage.objects.create(
                        campaign=campaign, user=user,
                        contact_name=num[0] or "", mobile_number=num[1],
                        status="failed", failed_at=timezone.now(),
                        error_code=str(api_error.get("code", "")),
                        error_title=api_error.get("type", ""),
                        error_message=api_error.get("message", ""),
                        error_details=(api_error.get("error_data") or {}).get("details", ""),
                    )

                # Also show it in this account's Messages inbox (campaign
                # sends only — one-off test sends stay out of the inbox).
                chat_log.record_outbound(
                    user, num[1], user_payload, response_json, response.status_code == 200, "campaign"
                )

        if all(res["status"] == 200 for res in responses):
            return {"status": "success", "message": "Messages sent successfully!", "responses": responses}
        else:
            return {"status": "partial_success", "message": "Some messages failed.", "responses": responses}

    except Exception as e:
        print("Error sending message:", e)
        return {"status": "error", "message": str(e)}

@feature_required('feature_campaigns')
def campaign_list(request):
    campaigns = Campaign.objects.filter(user=request.user).order_by('-start_time')

    now = timezone.now()
    total_campaigns = campaigns.count()
    draft_count = sum(1 for c in campaigns if c.is_draft)
    completed_count = sum(1 for c in campaigns if not c.is_draft and c.end_time)
    scheduled_count = sum(1 for c in campaigns if not c.is_draft and c.is_scheduled and c.scheduled_time and c.scheduled_time > now)
    ongoing_count = sum(
        1 for c in campaigns
        if not c.is_draft and not c.end_time and not (c.is_scheduled and c.scheduled_time and c.scheduled_time > now)
    )

    return render(request, 'campaign_list.html', {
        "campaigns": campaigns,
        "total_campaigns": total_campaigns,
        "draft_count": draft_count,
        "completed_count": completed_count,
        "scheduled_count": scheduled_count,
        "ongoing_count": ongoing_count,
    })

from datetime import datetime, timedelta
import requests
from django.shortcuts import render
from django.http import JsonResponse

from datetime import datetime, timedelta
import requests
from django.shortcuts import render
from django.http import JsonResponse

def get_date_range(period, start_date=None, end_date=None):
    now = datetime.now()
    max_days = 90  # Maximum insight range allowed

    if start_date and end_date:
        start_date = datetime.strptime(start_date, "%Y-%m-%d")
        end_date = datetime.strptime(end_date, "%Y-%m-%d")
        
        # Restrict date range to last 90 days only
        earliest_allowed = now - timedelta(days=max_days)
        if start_date < earliest_allowed:
            start_date = earliest_allowed
        if end_date < earliest_allowed:
            end_date = earliest_allowed
        if end_date > now:
            end_date = now
    else:
        if period == "7d":
            start_date = now - timedelta(days=7)
        elif period == "30d":
            start_date = now - timedelta(days=30)
        elif period == "60d":
            start_date = now - timedelta(days=60)
        elif period == "90d":
            start_date = now - timedelta(days=90)
        else:
            start_date = now - timedelta(days=30)  # Default to last 30 days

        end_date = now

    return int(start_date.timestamp()), int(end_date.timestamp())

def fetch_analytics(request):
    profile = UserProfile.objects.get(user=request.user)
    access_token = profile.api_key
    wba_id = profile.wba_id

    period = request.GET.get("period", "30d")
    start_date = request.GET.get("start_date", None)
    end_date = request.GET.get("end_date", None)

    start_timestamp, end_timestamp = get_date_range(period, start_date, end_date)

    url = f"https://graph.facebook.com/v22.0/{wba_id}?fields=conversation_analytics.start({start_timestamp}).end({end_timestamp}).granularity(DAILY).dimensions(['CONVERSATION_CATEGORY','CONVERSATION_TYPE'])"
    
    headers = {"Authorization": f"Bearer {access_token}"}
    
    cost_conversation_data = {"dates": [], "total_conversations": [], "total_cost": []}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        print("response.text-->",response.text)
        data = response.json()

        for entry in data.get("conversation_analytics", {}).get("data", []):
            for point in entry.get("data_points", []):
                date = point.get("end", "Unknown")
                date = timezone.datetime.fromtimestamp(date).strftime("%d-%m-%Y") if date != "Unknown" else date
                cost_conversation_data["dates"].append(date)
                cost_conversation_data["total_conversations"].append(point.get("conversation", 0))
                cost_conversation_data["total_cost"].append(point.get("cost", 0))

    except Exception as e:
        print(f"Error fetching analytics: {e}")

    return JsonResponse(cost_conversation_data)


def services(request):
    profile = UserProfile.objects.get(user=request.user)
    access_token = profile.api_key
    wba_id = profile.wba_id

    now = datetime.now()
    print("now-->", now)
    # Get first and last day of the month
    first_day = datetime(now.year, now.month, 1)
    last_day = datetime(now.year, now.month + 1, 1)

    print("first_day-->", first_day)
    print("last_day-->", last_day)
    # Convert to UNIX timestamps
    start_timestamp = int(first_day.timestamp())
    end_timestamp = int(last_day.timestamp())


    url = f"https://graph.facebook.com/v22.0/{wba_id}?fields=conversation_analytics.start({start_timestamp}).end({end_timestamp}).granularity(DAILY).dimensions(['CONVERSATION_CATEGORY','CONVERSATION_TYPE'])"
    
    headers = {"Authorization": f"Bearer {access_token}"}
    
    total_conversations = 0
    total_cost = 0
    cost_conversation_data = {"total_conversations" : 0, "total_cost": 0}
    try:
        response = requests.get(url, headers=headers)
        print("response.text-->", response.text)
        response.raise_for_status()  # Raise an error for bad status codes (e.g., 401, 403, 500)
        data = response.json()

        total_conversations = 0
        total_cost = 0

        for entry in data.get("conversation_analytics", {}).get("data", []):
            for point in entry.get("data_points", []):
                total_conversations += point.get("conversation", 0)
                total_cost += point.get("cost", 0)

        cost_conversation_data["total_conversations"] = total_conversations
        cost_conversation_data["total_cost"] = total_cost
        print("cost_conversation_data-->", cost_conversation_data)

    except KeyError:
        print("KeyError: Missing expected data in API response")
    except ValueError:
        print("ValueError: Could not parse JSON response")
    except requests.RequestException as e:
        print(f"RequestException: {e}")

    # return {"total_conversations": total_conversations, "total_cost": total_cost}

    hour = timezone.localtime().hour
    if hour < 12:
        greeting = "Morning"
    elif hour < 17:
        greeting = "Afternoon"
    else:
        greeting = "Evening"

    messages_sent = sum(
        len(c.contact_numbers or [])
        for c in Campaign.objects.filter(user=request.user).exclude(end_time=None)
    )
    active_contacts = Contact.objects.filter(user=request.user).count()

    return render(request, 'services.html', {
        "cost_conversation_data": cost_conversation_data,
        "greeting": greeting,
        "messages_sent": messages_sent,
        "active_contacts": active_contacts,
    })

def _daily_counts(queryset, date_field):
    """{date: count} of `queryset` rows grouped by the local-timezone date of
    `date_field`, skipping rows where it's not set."""
    rows = (
        queryset.filter(**{f"{date_field}__isnull": False})
        .annotate(day=TruncDate(date_field))
        .values("day")
        .annotate(n=Count("id"))
    )
    return {row["day"]: row["n"] for row in rows}


def _resolve_insight_period(request):
    """Reads `range` (today | 7d | 30d | custom) plus `start_date`/`end_date`
    (for custom) from the querystring and returns (range_key, period_start,
    period_end, prev_start, prev_end) — the previous period being an
    equal-length window immediately before period_start, used for the KPI
    cards' "vs previous period" comparison. Defaults to "today" when no
    `range` is given."""
    today = timezone.localtime().date()
    range_key = request.GET.get("range", "today")

    if range_key == "7d":
        period_start, period_end = today - timedelta(days=6), today
    elif range_key == "30d":
        period_start, period_end = today - timedelta(days=29), today
    elif range_key == "custom":
        try:
            period_start = datetime.strptime(request.GET.get("start_date", ""), "%Y-%m-%d").date()
            period_end = datetime.strptime(request.GET.get("end_date", ""), "%Y-%m-%d").date()
        except ValueError:
            range_key = "today"
            period_start = period_end = today
        else:
            if period_start > period_end:
                period_start, period_end = period_end, period_start
    else:
        range_key = "today"
        period_start = period_end = today

    period_days = (period_end - period_start).days + 1
    prev_end = period_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=period_days - 1)
    return range_key, period_start, period_end, prev_start, prev_end


def _count_between(queryset, date_field, start, end):
    return queryset.filter(**{
        f"{date_field}__date__gte": start,
        f"{date_field}__date__lte": end,
    }).count()


def _pct_change(current, previous):
    """Percent change of `current` vs `previous`, treating "no data in the
    previous period" as +100% when there's activity now, 0% when there
    still isn't — never a divide-by-zero."""
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round((current - previous) / previous * 100, 1)


# (metric key, CampaignMessage date field, label, icon, color)
_KPI_METRICS = [
    ("sent", "sent_at", "Total Sent", "mdi-send-outline", "blue"),
    ("delivered", "delivered_at", "Delivered", "mdi-check-circle-outline", "green"),
    ("read", "read_at", "Read", "mdi-eye-outline", "purple"),
    ("clicked", "clicked_at", "Clicked", "mdi-cursor-default-click-outline", "teal"),
    ("replied", "replied_at", "Replied", "mdi-reply-outline", "orange"),
    ("failed", "failed_at", "Failed", "mdi-alert-circle-outline", "red"),
]


def _build_insight_period_data(msgs, period_start, period_end, prev_start, prev_end):
    """KPI cards (current vs previous period, plus a per-day sparkline) and
    the per-day chart data — all scoped to `period_start..period_end` — for
    every metric in _KPI_METRICS."""
    daily_by_field = {
        field: _daily_counts(msgs.filter(status="failed") if field == "failed_at" else msgs, field)
        for _, field, _, _, _ in _KPI_METRICS
    }

    kpi_cards = []

    day_count = (period_end - period_start).days + 1
    days = [period_start + timedelta(days=i) for i in range(day_count)]

    # A single-day period (the "Today" default) gives a line chart exactly
    # one point — nothing to draw a line between, so it renders blank.
    # Extend the chart's own x-axis one extra day back so there's always a
    # visible trend, without changing what the KPI totals below are scoped
    # to (still exactly `days`, i.e. just today).
    chart_days = days if len(days) > 1 else [period_start - timedelta(days=1)] + days
    graph_data = {"dates": [d.strftime("%d %b") for d in chart_days]}

    for key, field, label, icon, color in _KPI_METRICS:
        by_day = daily_by_field[field]
        graph_data[key] = [by_day.get(day, 0) for day in chart_days]

        current_total = sum(by_day.get(day, 0) for day in days)
        base_qs = msgs.filter(status="failed") if field == "failed_at" else msgs
        previous_total = _count_between(base_qs, field, prev_start, prev_end)
        change = _pct_change(current_total, previous_total)

        kpi_cards.append({
            "key": key,
            "label": label,
            "icon": icon,
            "color": color,
            "value": current_total,
            "change_abs": abs(change),
            # "flat" (no arrow, neutral color) when nothing changed, rather
            # than defaulting a genuine 0% to a green "up" arrow.
            "change_direction": "up" if change > 0 else ("down" if change < 0 else "flat"),
        })

    return kpi_cards, graph_data


@login_required
def campaign_analytics(request):
    campaign_name = request.GET.get("campaign_name")
    campaign = get_object_or_404(Campaign, campaign_name=campaign_name, user=request.user)

    total_audience = len(campaign.contact_numbers)
    contact_numbers = campaign.contact_numbers

    # Built entirely from our own CampaignMessage rows (populated at send
    # time, updated by the webhook's per-message status updates) rather than
    # Meta's template_analytics endpoint — that endpoint totals up every
    # send of a template across the whole WABA, so two campaigns sharing a
    # template (or the same template reused later) showed mixed-together
    # numbers there. Counting our own rows keeps each campaign's numbers to
    # only the messages *it* sent.
    msgs = campaign.messages.all()

    # Meta's per-message status webhook carries a billing *category*
    # (marketing/utility/...), not a cost figure — real cost is only
    # available WABA-wide via conversation_analytics, which can't be split
    # back out per-campaign. Left at 0 rather than showing a borrowed number.
    total_credit_usage = 0

    range_key, period_start, period_end, prev_start, prev_end = _resolve_insight_period(request)
    kpi_cards, graph_data = _build_insight_period_data(msgs, period_start, period_end, prev_start, prev_end)

    return render(request, "campaign_analytics.html", {
        "total_credit_usage": total_credit_usage,
        "campaign_name": campaign_name,
        "template_name": campaign.template_name,
        "start_time": campaign.start_time,
        "end_time": campaign.end_time,
        "total_audience": total_audience,
        "contact_numbers": contact_numbers,
        "kpi_cards": kpi_cards,
        "graph_data": json.dumps(graph_data),
        "insight_range": range_key,
        "period_start": period_start,
        "period_end": period_end,
    })


@login_required
def export_campaign_analytics(request):
    """Multi-sheet Excel download, period-scoped the same way the page
    above it is: a "Summary" sheet (the same dashboard numbers shown on
    screen — KPI totals + daily breakdown) plus one sheet per recipient
    status (Read/Delivered/Clicked/Replied/Failed) listing the actual
    contacts in that bucket for the selected period."""
    import io

    campaign_name = request.GET.get("campaign_name")
    campaign = get_object_or_404(Campaign, campaign_name=campaign_name, user=request.user)
    msgs = campaign.messages.all()

    range_key, period_start, period_end, prev_start, prev_end = _resolve_insight_period(request)
    kpi_cards, graph_data = _build_insight_period_data(msgs, period_start, period_end, prev_start, prev_end)
    preview = _campaign_message_preview(campaign)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        summary_rows = [
            ["Campaign", campaign_name],
            ["Template", campaign.template_name],
            ["Period", f"{period_start} to {period_end}"],
            [],
            ["Metric", "Total", "% vs previous period"],
        ]
        for card in kpi_cards:
            sign = "-" if card["change_direction"] == "down" else "+"
            summary_rows.append([card["label"], card["value"], f"{sign}{card['change_abs']}%"])
        summary_rows.append([])
        summary_rows.append(["Date", "Sent", "Delivered", "Read", "Clicked", "Replied", "Failed"])
        for i, date_label in enumerate(graph_data["dates"]):
            summary_rows.append([
                date_label, graph_data["sent"][i], graph_data["delivered"][i], graph_data["read"][i],
                graph_data["clicked"][i], graph_data["replied"][i], graph_data["failed"][i],
            ])
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="Summary", header=False, index=False)

        # One sheet per status tab — same rows the recipients table on
        # screen would show for this status at this same date range.
        for key, label, field, _, _ in _RECIPIENT_TABS:
            qs = _recipient_status_queryset(msgs, key, field, period_start, period_end).order_by("-id")
            rows = []
            for m in qs:
                ts = getattr(m, field, None)
                row = {
                    "Name": m.contact_name,
                    "Phone Number": m.mobile_number,
                    "Message Preview": preview,
                    f"{label} At": timezone.localtime(ts).strftime("%b %d, %Y %I:%M %p") if ts else "",
                    "Status": m.get_status_display(),
                }
                if key == "failed":
                    retryable = _is_retryable_failure(m)
                    row["Retryable"] = "Unknown" if retryable is None else ("Yes" if retryable else "No")
                    row["Error Message"] = m.error_message
                    row["Error Details"] = m.error_details
                rows.append(row)

            columns = ["Name", "Phone Number", "Message Preview", f"{label} At", "Status"]
            if key == "failed":
                columns += ["Retryable", "Error Message", "Error Details"]
            df = pd.DataFrame(rows, columns=columns)
            # Excel sheet names are capped at 31 characters — "Delivered
            # Contacts" etc. all fit comfortably under that.
            df.to_excel(writer, sheet_name=f"{label} Contacts"[:31], index=False)

    output.seek(0)
    filename = f"{campaign_name}_insights_{period_start}_{period_end}.xlsx"
    response = HttpResponse(
        output.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# Tab key -> (label, CampaignMessage timestamp field or None for "failed",
# icon, color) shown on the Campaign Insights recipients table.
_RECIPIENT_TABS = [
    ("read", "Read", "read_at", "mdi-eye-outline", "purple"),
    ("delivered", "Delivered", "delivered_at", "mdi-check-circle-outline", "green"),
    ("clicked", "Clicked", "clicked_at", "mdi-cursor-default-click-outline", "teal"),
    ("replied", "Replied", "replied_at", "mdi-reply-outline", "orange"),
    ("failed", "Failed", "failed_at", "mdi-alert-circle-outline", "red"),
]
_RECIPIENT_TAB_FIELDS = {key: field for key, _, field, _, _ in _RECIPIENT_TABS}

# Best-effort classification of a failure as worth retrying or not, from the
# error text Meta gave us (see CampaignMessage.error_title/error_message,
# saved in send_message_to_user / _handle_status_update). This is a
# heuristic, not an official list of Meta error codes — phrasing can change,
# so treat "Permanent" as a hint to double-check, not a guarantee.
_PERMANENT_FAILURE_HINTS = (
    "not a whatsapp user", "not on whatsapp", "not registered", "does not exist",
    "invalid phone number", "invalid recipient", "opted out", "account restricted",
    "template does not exist", "template was rejected", "parameter",
    # A free-form (non-template) message sent outside the 24h customer
    # service window — resending the exact same text won't help until the
    # contact messages in again; only switching to a template message would
    # get through immediately, which a plain retry doesn't do.
    "re-engagement message", "24 hours have passed",
)


def _is_retryable_failure(msg):
    text = f"{msg.error_title} {msg.error_message} {msg.error_details}".lower()
    if not text.strip():
        return None  # no error detail captured — unknown, not a guess either way
    return not any(hint in text for hint in _PERMANENT_FAILURE_HINTS)


def _campaign_message_preview(campaign):
    """One representative line of what this campaign actually sent — not
    resolved per-recipient (personalization here is just a name swap), just
    enough to recognize the message in the recipients table."""
    if campaign.message_type == "template":
        return f"Template: {campaign.template_name}" if campaign.template_name else "Template message"
    if campaign.message_type == "text":
        return campaign.message_text or ""
    label = campaign.media_caption or campaign.media_filename or f"{campaign.message_type} message"
    return f"[{campaign.message_type.title()}] {label}"


def _recipient_status_queryset(msgs, key, field, period_start=None, period_end=None):
    """Rows belonging to one recipient-table tab — "failed" is a status
    value, every other tab is "this timestamp field got set" — optionally
    narrowed to rows where that same field falls within a date range."""
    qs = msgs.filter(status="failed") if key == "failed" else msgs.filter(**{f"{field}__isnull": False})
    if period_start and period_end:
        qs = qs.filter(**{f"{field}__date__gte": period_start, f"{field}__date__lte": period_end})
    return qs


@login_required
def campaign_recipients(request):
    """Paginated, searchable, per-status recipient list for a campaign —
    powers the table on the Campaign Insights page that "Retarget" is built
    on top of. Scoped to the same date range as the KPI cards/chart above it
    (via `range`/`start_date`/`end_date`, same as campaign_analytics —
    defaults to "today"), so the two sections always agree with each other."""
    campaign_name = request.GET.get("campaign_name")
    campaign = get_object_or_404(Campaign, campaign_name=campaign_name, user=request.user)
    msgs = campaign.messages.all()

    _, period_start, period_end, _, _ = _resolve_insight_period(request)

    counts = {
        key: _recipient_status_queryset(msgs, key, field, period_start, period_end).count()
        for key, _, field, _, _ in _RECIPIENT_TABS
    }

    status = request.GET.get("status", "read")
    if status not in _RECIPIENT_TAB_FIELDS:
        status = "read"
    field = _RECIPIENT_TAB_FIELDS[status]
    qs = _recipient_status_queryset(msgs, status, field, period_start, period_end)

    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(mobile_number__icontains=q) | Q(contact_name__icontains=q))
    qs = qs.order_by("-id")

    try:
        page = max(int(request.GET.get("page", 1)), 1)
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = int(request.GET.get("page_size", 50))
    except (TypeError, ValueError):
        page_size = 50
    page_size = max(min(page_size, 200), 10)

    total = qs.count()
    start = (page - 1) * page_size
    rows = list(qs[start:start + page_size])
    preview = _campaign_message_preview(campaign)

    data_rows = []
    for m in rows:
        ts = getattr(m, field, None)
        data_rows.append({
            "id": m.id,
            "name": m.contact_name or "",
            "mobile_number": m.mobile_number,
            "message_preview": preview,
            "timestamp": timezone.localtime(ts).strftime("%b %d, %Y %I:%M %p") if ts else "",
            "status": m.get_status_display(),
            "status_key": m.status,
            "is_retryable": _is_retryable_failure(m) if m.status == "failed" else None,
            "error_message": m.error_message if m.status == "failed" else "",
            "error_details": m.error_details if m.status == "failed" else "",
        })

    return JsonResponse({
        "rows": data_rows,
        "counts": counts,
        "total": total,
        "page": page,
        "page_size": page_size,
        "status": status,
    })


@login_required
@require_POST
def campaign_retarget(request):
    """Takes a set of CampaignMessage ids (selected on the recipients
    table), resolves them back to this user's Contacts, and stashes that
    selection in the session for the campaign wizard to pick up via
    ?retarget=<token> — see create_campaign's GET branch. Opted-out
    contacts are excluded under the same "Opt-Out Customers" switch on the
    Contacts page that every other campaign send already respects (see
    _campaign_audience_queryset) — retargeting doesn't apply a stricter
    rule of its own."""
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "message": "Invalid request."}, status=400)

    campaign_name = data.get("campaign_name")
    message_ids = data.get("message_ids") or []
    campaign = get_object_or_404(Campaign, campaign_name=campaign_name, user=request.user)

    numbers = list(
        campaign.messages.filter(id__in=message_ids).values_list("mobile_number", flat=True).distinct()
    )
    if not numbers:
        return JsonResponse({"success": False, "message": "No recipients selected."}, status=400)

    contacts = list(Contact.objects.filter(user=request.user, mobile_number__in=numbers))

    opt_out_setting = GlobalOptOut.objects.filter(user=request.user).first()
    respect_opt_outs = bool(opt_out_setting and opt_out_setting.is_enabled)
    if respect_opt_outs:
        opted_out_ids = set(
            OptOutUser.objects.filter(user=request.user, contact__in=contacts).values_list("contact_id", flat=True)
        )
    else:
        opted_out_ids = set()
    contact_ids = [c.id for c in contacts if c.id not in opted_out_ids]
    skipped_opted_out = len(opted_out_ids)
    skipped_no_contact = len(numbers) - len(contacts)

    if not contact_ids:
        return JsonResponse({
            "success": False,
            "message": "Everyone in this selection has opted out or no longer has a saved contact.",
        }, status=400)

    token = uuid.uuid4().hex
    request.session[f"retarget_{token}"] = {
        "campaign_id": campaign.id,
        "campaign_name": campaign.campaign_name,
        "contact_ids": contact_ids,
        "skipped_opted_out": skipped_opted_out,
        "skipped_no_contact": skipped_no_contact,
    }

    return JsonResponse({
        "success": True,
        "redirect_url": f"{reverse('create_campaign')}?retarget={token}",
        "selected_count": len(contact_ids),
        "skipped_opted_out": skipped_opted_out,
    })


@login_required
def stop_campaign(request):
    if request.method == "POST":
        data = json.loads(request.body)
        campaign_name = data.get("campaign_name")

        campaign = get_object_or_404(Campaign, campaign_name=campaign_name, user=request.user)
        
        if not campaign.end_time:  # Only stop if not already ended
            campaign.end_time = timezone.now()
            campaign.save()
            return JsonResponse({"success": True})
    
    return JsonResponse({"success": False})

@login_required
def start_campaign(request):
    if request.method == "POST":
        data = json.loads(request.body)
        campaign_name = data.get("campaign_name")

        campaign = get_object_or_404(Campaign, campaign_name=campaign_name, user=request.user)

        if campaign.end_time:  # Only start if it was previously stopped
            campaign.end_time = None
            campaign.save()
            return JsonResponse({"success": True})

    return JsonResponse({"success": False})

def check_campaign_name(request):
    name = request.GET.get('name', '')
    exists = Campaign.objects.filter(campaign_name__iexact=name, user=request.user).exists()
    return JsonResponse({'exists': exists})

@login_required
def delete_campaign(request, campaign_id):
    campaign = get_object_or_404(Campaign, id=campaign_id, user=request.user)

    if request.method == "POST":
        campaign.delete()
        messages.success(request, "Campaign deleted successfully.")
    
    return redirect('campaign_list')

def _safe_json_for_script(value):
    """json.dumps output embedded straight into a <script> block as-is can be
    broken out of by a literal "</script>" inside user-authored strings
    (campaign name, message text, ...) — escape it so that's inert."""
    return json.dumps(value).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _campaign_audience_queryset(request, audience_mode, tags_list, contact_ids):
    """Resolve the recipient list for a campaign based on the chosen
    audience mode, shared between the live preview refresh and the final
    submit so both always agree on who gets the message."""
    contacts = Contact.objects.filter(user=request.user)

    if audience_mode == "tag" and tags_list:
        contacts = contacts.filter(tags__name__in=tags_list).distinct()
    elif audience_mode == "manual" and contact_ids:
        contacts = contacts.filter(id__in=contact_ids)
    # "all" (or an empty filter for tag/manual) -> every contact

    opt_out_entry = GlobalOptOut.objects.filter(user=request.user).first()
    if opt_out_entry and opt_out_entry.is_enabled:
        contacts = contacts.exclude(opt_outs__user=request.user)

    return contacts


@login_required
def campaign_search_contacts(request):
    """Powers the 'Manually Select' contact picker on the create-campaign page.
    Also used to resolve names/numbers for a set of ids (?ids=1,2,3) when
    resuming a draft that only stored the selected contact ids."""
    from django.db.models import Q

    query = request.GET.get("q", "").strip()
    ids_param = [int(i) for i in request.GET.get("ids", "").split(",") if i.strip().isdigit()]

    contacts = Contact.objects.filter(user=request.user)
    if ids_param:
        contacts = contacts.filter(id__in=ids_param)
    elif query:
        contacts = contacts.filter(Q(name__icontains=query) | Q(mobile_number__icontains=query))
    contacts = contacts.order_by("name")[:50]
    return JsonResponse({
        "contacts": [
            {"id": c.id, "name": c.name or c.mobile_number, "mobile_number": c.mobile_number}
            for c in contacts
        ]
    })


def create_campaign(request):
    # Always fetch approved templates from Meta's API if possible
    approved_template_names = []
    try:
        profile = UserProfile.objects.get(user=request.user)
        wba_id = profile.wba_id
        api_key = profile.api_key
        if wba_id and api_key:
            url = f"https://graph.facebook.com/v22.0/{wba_id}/message_templates"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                approved_template_names = [
                    tpl.get('name') for tpl in data.get("data", []) if tpl.get("status") == "APPROVED"
                ]
            else:
                print("Error fetching templates:", response.text)
    except Exception as e:
        print("Error fetching user profile or templates:", e)

    total_contacts = Contact.objects.filter(user=request.user).count()
    prebuilt_tags = list(Tag.objects.filter(is_prebuilt=True).values_list("name", flat=True))

    # Kept JSON-safe throughout the POST branch below — a real Tag queryset
    # is only ever attached right before a template render, never before a
    # JsonResponse (an AJAX refresh returning a raw QuerySet would crash).
    context = {
        "approved_templates": approved_template_names,
        "total_contacts": total_contacts,
        "prebuilt_tags": prebuilt_tags,
        "prebuilt_tags_json": _safe_json_for_script(prebuilt_tags),
    }

    if request.method != "POST":
        context["tags"] = Tag.objects.filter(user=request.user)

        draft_id = request.GET.get("draft_id", "").strip()
        if draft_id:
            draft = Campaign.objects.filter(id=draft_id, user=request.user, is_draft=True).first()
            if draft:
                context["draft_json"] = _safe_json_for_script({
                    "id": draft.id,
                    "campaign_name": draft.campaign_name,
                    "message_type": draft.message_type,
                    "campaign_type": draft.campaign_type,
                    "audience_mode": draft.audience_mode,
                    "audience_tags": draft.audience_tags or [],
                    "audience_contact_ids": draft.audience_contact_ids or [],
                    "template_name": draft.template_name,
                    "message_text": draft.message_text,
                    "media_id": draft.media_id,
                    "media_filename": draft.media_filename,
                    "media_caption": draft.media_caption,
                    "add_unsubscribe_button": draft.add_unsubscribe_button,
                    "track_status": draft.track_status,
                    "is_scheduled": draft.is_scheduled,
                    "scheduled_time": draft.scheduled_time.strftime("%Y-%m-%dT%H:%M") if draft.scheduled_time else "",
                })
            else:
                messages.error(request, "That draft could not be found.")

        # Coming from "Retarget" on a campaign's Insights recipients table
        # (see campaign_retarget) — one-time token, so this only prefills
        # once even if the page gets reloaded/bookmarked.
        retarget_token = request.GET.get("retarget", "").strip()
        if retarget_token:
            retarget_data = request.session.pop(f"retarget_{retarget_token}", None)
            original = None
            contact_ids = []
            if retarget_data:
                original = Campaign.objects.filter(id=retarget_data["campaign_id"], user=request.user).first()
                contact_ids = retarget_data.get("contact_ids", [])

            if original and contact_ids:
                suggested_name = f"{original.campaign_name} - Retarget - {timezone.localtime().strftime('%d %b')}"
                base_name, n = suggested_name, 2
                while Campaign.objects.filter(user=request.user, campaign_name=suggested_name).exists():
                    suggested_name = f"{base_name} ({n})"
                    n += 1

                context["draft_json"] = _safe_json_for_script({
                    "id": "",
                    "campaign_name": suggested_name,
                    "message_type": original.message_type,
                    "campaign_type": original.campaign_type,
                    "audience_mode": "manual",
                    "audience_tags": [],
                    "audience_contact_ids": contact_ids,
                    "template_name": original.template_name,
                    "message_text": original.message_text,
                    "media_id": original.media_id,
                    "media_filename": original.media_filename,
                    "media_caption": original.media_caption,
                    "add_unsubscribe_button": original.add_unsubscribe_button,
                    "track_status": original.track_status,
                    "is_scheduled": False,
                    "scheduled_time": "",
                })
                context["retargeted_from_id"] = original.id
                # Rendered as a banner that stays put in the audience panel
                # (see campaign.html) rather than the auto-dismissing toast
                # messages.info() produces — a "why did only 1 of the 2
                # contacts I picked end up selected" moment is exactly the
                # kind of thing that's easy to miss once it's gone.
                context["retarget_notice"] = {
                    "original_name": original.campaign_name,
                    "selected_count": len(contact_ids),
                    "skipped_opted_out": retarget_data.get("skipped_opted_out", 0),
                    "skipped_no_contact": retarget_data.get("skipped_no_contact", 0),
                }
            else:
                messages.error(
                    request,
                    "That retargeting link has expired or has no valid contacts left. "
                    "Please try again from the campaign's Insights page.",
                )

        return render(request, "campaign.html", context)

    action = request.POST.get("action", "refresh")  # refresh | test | submit
    send_mode = request.POST.get("send_mode", "now")  # now | schedule | draft
    # A draft is allowed to be incomplete — only "test" and an actual
    # now/schedule submit require a fully valid, sendable message. Errors
    # collected below are returned directly in the JSON response instead of
    # Django's messages framework, which otherwise queues them in the
    # session and leaks them onto whatever page the user visits next (this
    # view is called via AJAX almost every keystroke, so it never itself
    # renders a page for the messages to show up on).
    requires_valid_message = action == "test" or (action == "submit" and send_mode != "draft")
    errors = []

    draft_id = request.POST.get("draft_id", "").strip()
    retargeted_from_id = request.POST.get("retargeted_from_id", "").strip()
    campaign_name = request.POST.get("campaign_name", "").strip()
    message_type = request.POST.get("message_type", "template").strip()
    campaign_type = request.POST.get("campaign_type", "broadcast").strip()
    audience_mode = request.POST.get("audience_mode", "all").strip()
    add_unsubscribe_button = request.POST.get("add_unsubscribe_button") == "1"
    track_status = request.POST.get("track_status") == "1"

    tags_param = [t.strip() for t in request.POST.get("tags", "").split(",") if t.strip()]
    contact_ids_param = [int(c) for c in request.POST.get("contact_ids", "").split(",") if c.strip().isdigit()]

    contacts = _campaign_audience_queryset(request, audience_mode, tags_param, contact_ids_param)
    customer_list = list(contacts.values_list('name', 'mobile_number'))

    context["campaign_name"] = campaign_name
    context["audience_total"] = total_contacts
    context["audience_selected"] = len(customer_list)
    context["audience_unselected"] = max(total_contacts - len(customer_list), 0)

    selected_template_name = request.POST.get("template_name", "").strip()
    selected_tpl = None
    sending_payload = None
    final_data = {}
    message_text = ""
    media_id = ""
    media_caption = ""
    media_filename = ""

    if message_type == "template":
        if selected_template_name:
            try:
                profile = UserProfile.objects.get(user=request.user)
                wba_id, api_key = profile.wba_id, profile.api_key
                if wba_id and api_key:
                    template_details_url = f"https://graph.facebook.com/v22.0/{wba_id}/message_templates?name={selected_template_name}"
                    headers = {
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    }
                    response = requests.get(template_details_url, headers=headers)
                    if response.status_code == 200:
                        tpl_data = response.json().get("data", [])
                        selected_tpl = next((tpl for tpl in tpl_data if tpl.get("name") == selected_template_name), None)
                        if selected_tpl:
                            context["template_data"] = selected_tpl
                            final_data_json = request.POST.get("final_data") or "{}"
                            final_data = json.loads(final_data_json)
                            if action in ("test", "submit"):
                                try:
                                    components = create_message_sending_payload(selected_tpl, final_data)
                                    sending_payload = {
                                        "messaging_product": "whatsapp",
                                        "to": "",
                                        "type": "template",
                                        "template": {
                                            "name": selected_tpl.get("name"),
                                            "language": {"code": selected_tpl.get("language", "en")},
                                            "components": components,
                                        },
                                    }
                                except ValueError as e:
                                    if requires_valid_message:
                                        errors.append(str(e))
                            context["final_data"] = final_data
                        elif requires_valid_message:
                            errors.append("No template details found for the selected template.")
                    elif requires_valid_message:
                        errors.append(f"Error fetching template details: {response.text}")
                elif requires_valid_message:
                    errors.append("WBA ID or API key is missing in your profile.")
            except Exception as e:
                print("Error fetching template details:", e)
                if requires_valid_message:
                    errors.append("Error fetching template details.")
        elif requires_valid_message:
            errors.append("No template selected.")

    elif message_type in ("text", "image", "document"):
        message_text = request.POST.get("message_text", "").strip()
        media_id = request.POST.get("media_id", "").strip()
        media_caption = request.POST.get("media_caption", "").strip()
        media_filename = request.POST.get("media_filename", "").strip()

        # Non-template messages don't have Meta's variable-substitution
        # system, so personalization here is a simple {{name}} placeholder
        # swapped in per-recipient at send time (see send_message_to_user).
        final_data = {"personalize": campaign_type == "personalized"}
        context["final_data"] = final_data

        missing_required = (
            (message_type == "text" and not message_text)
            or (message_type in ("image", "document") and not media_id)
        )

        if requires_valid_message and missing_required:
            errors.append("Message text is required." if message_type == "text" else "Please upload a file first.")
        elif not missing_required:
            # Matches Meta's documented Cloud API message shapes exactly —
            # recipient_type is technically optional but included for spec
            # compliance; caption/filename are only sent when present since
            # Meta doesn't want empty-string values for optional fields.
            if add_unsubscribe_button:
                body_text = message_text if message_type == "text" else (media_caption or " ")
                interactive = {
                    "type": "button",
                    "body": {"text": body_text},
                    "action": {"buttons": [
                        {"type": "reply", "reply": {"id": "unsubscribe", "title": "Unsubscribe"}}
                    ]},
                }
                if message_type == "image":
                    interactive["header"] = {"type": "image", "image": {"id": media_id}}
                elif message_type == "document":
                    doc_header = {"id": media_id}
                    if media_filename:
                        doc_header["filename"] = media_filename
                    interactive["header"] = {"type": "document", "document": doc_header}
                sending_payload = {
                    "messaging_product": "whatsapp", "recipient_type": "individual", "to": "",
                    "type": "interactive", "interactive": interactive,
                }
            elif message_type == "text":
                sending_payload = {
                    "messaging_product": "whatsapp", "recipient_type": "individual", "to": "",
                    "type": "text", "text": {"body": message_text, "preview_url": False},
                }
            elif message_type == "image":
                image_obj = {"id": media_id}
                if media_caption:
                    image_obj["caption"] = media_caption
                sending_payload = {
                    "messaging_product": "whatsapp", "recipient_type": "individual", "to": "",
                    "type": "image", "image": image_obj,
                }
            else:  # document
                document_obj = {"id": media_id}
                if media_caption:
                    document_obj["caption"] = media_caption
                if media_filename:
                    document_obj["filename"] = media_filename
                sending_payload = {
                    "messaging_product": "whatsapp", "recipient_type": "individual", "to": "",
                    "type": "document", "document": document_obj,
                }

    if action == "test":
        test_number = request.POST.get("test_number", "").strip()
        if not test_number:
            errors.append("Please enter a test number.")
        if not errors:
            result = send_message_to_user(sending_payload, [("Test Contact", test_number)], final_data, request.user)
            if result.get("status") == "success":
                context["test_success"] = f"Test message sent to {test_number}"
            else:
                # Surface Meta's actual rejection reason (e.g. a missing
                # template variable) instead of silently reporting success —
                # send_message_to_user's HTTP call can fail even though this
                # view's own validation passed.
                detail = result.get("message", "Unknown error")
                responses = result.get("responses") or []
                if responses:
                    api_error = responses[0].get("response", {}).get("error", {})
                    detail = api_error.get("message") or detail
                errors.append(f"Test message failed: {detail}")

    elif action == "submit":
        scheduled_time_raw = request.POST.get("scheduled_time")
        is_draft = send_mode == "draft"
        is_scheduled = send_mode == "schedule"

        # A <input type="datetime-local"> normally has no seconds, but be
        # lenient about the format anyway — this used to call strptime with
        # a single hardcoded format and no error handling at all, so any
        # mismatch (or an empty value slipping past client-side checks) blew
        # up as an unhandled 500 instead of a clean validation error.
        scheduled_time = None
        if is_scheduled:
            for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
                try:
                    scheduled_time = datetime.strptime(scheduled_time_raw, fmt)
                    break
                except (ValueError, TypeError):
                    continue
            if scheduled_time is not None and timezone.is_naive(scheduled_time):
                scheduled_time = timezone.make_aware(scheduled_time)

        existing_draft = None
        if draft_id:
            existing_draft = Campaign.objects.filter(id=draft_id, user=request.user).first()

        # Only a draft turning into a real (sent/scheduled) campaign counts
        # against the plan's limit — saving/re-saving a draft never does.
        if not is_draft and (existing_draft is None or existing_draft.is_draft):
            current_campaigns = Campaign.objects.filter(user=request.user, is_draft=False).count()
            allowed, limit = billing.check_limit(request.user, billing.MAX_CAMPAIGNS, current_campaigns)
            if not allowed:
                errors.append(f"Your plan allows up to {limit} campaign(s). Upgrade your plan to send more.")

        name_conflict = Campaign.objects.filter(user=request.user, campaign_name=campaign_name)
        if existing_draft:
            name_conflict = name_conflict.exclude(id=existing_draft.id)

        if not campaign_name:
            errors.append("Campaign name is required.")
        elif name_conflict.exists():
            errors.append("A campaign with this name already exists. Please choose a different name.")
        elif is_scheduled and scheduled_time is None:
            errors.append("Please choose a valid date and time to schedule this campaign.")
        elif not is_draft and not sending_payload and not errors:
            errors.append("Please finish setting up your message before sending.")
        elif not is_draft and not customer_list:
            errors.append("No contacts match your audience selection.")

        if not errors:
            start_time = scheduled_time if is_scheduled else timezone.now()
            contact_numbers = [number for _, number in customer_list]

            campaign_fields = dict(
                campaign_name=campaign_name,
                template_name=selected_template_name if message_type == "template" else "",
                template_id=selected_tpl.get("id") if selected_tpl else None,
                message_type=message_type,
                campaign_type=campaign_type,
                add_unsubscribe_button=add_unsubscribe_button,
                track_status=track_status,
                is_draft=is_draft,
                contact_numbers=contact_numbers,
                is_scheduled=is_scheduled,
                scheduled_time=scheduled_time,
                start_time=start_time,
                final_data=final_data,
                sending_payload=sending_payload,
                customer_list=customer_list,
                audience_mode=audience_mode,
                audience_tags=tags_param,
                audience_contact_ids=contact_ids_param,
                message_text=message_text,
                media_id=media_id,
                media_caption=media_caption,
                media_filename=media_filename,
            )

            if existing_draft:
                for field, value in campaign_fields.items():
                    setattr(existing_draft, field, value)
                existing_draft.save()
                campaign = existing_draft
            else:
                # Only set on first creation — never overwritten when
                # resuming/re-saving an existing draft, so a draft saved
                # partway through a retarget doesn't lose that lineage on a
                # later edit where this hidden field isn't re-populated.
                retargeted_from = (
                    Campaign.objects.filter(id=retargeted_from_id, user=request.user).first()
                    if retargeted_from_id.isdigit() else None
                )
                campaign = Campaign.objects.create(
                    user=request.user, retargeted_from=retargeted_from, **campaign_fields
                )

            if is_draft:
                messages.success(request, "Campaign saved as draft.")
            elif is_scheduled:
                run_scheduled_campaign.apply_async(args=[campaign.id, campaign.user.id], eta=scheduled_time)
                messages.success(request, "Campaign scheduled successfully.")
            else:
                async_send_messages.delay(sending_payload, customer_list, final_data, request.user.id, campaign.id)
                messages.success(request, f"Message sent to {len(customer_list)} contacts.")

            return redirect('campaign_list')

    context["errors"] = errors

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse(context)

    context["tags"] = Tag.objects.filter(user=request.user)
    return render(request, 'campaign.html', context)



@login_required
@feature_required('feature_tags')
def tag_list(request):
    # Render page for HTML or return JSON for AJAX
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        tags = Tag.objects.filter(user=request.user)
        return JsonResponse({"tags": list(tags.values('id', 'name'))})

    from django.db.models import Count, Q

    prebuilt_tags = Tag.objects.filter(is_prebuilt=True).annotate(
        contact_count=Count('contact', filter=Q(contact__user=request.user), distinct=True)
    ).order_by('name')
    user_tags = Tag.objects.filter(user=request.user, is_prebuilt=False).annotate(
        contact_count=Count('contact', filter=Q(contact__user=request.user), distinct=True)
    ).order_by('name')

    all_contacts = Contact.objects.filter(user=request.user)
    total_contacts = all_contacts.count()
    contacts_tagged = all_contacts.filter(tags__isnull=False).distinct().count()
    contacts_untagged = total_contacts - contacts_tagged

    context = {
        "prebuilt_tags": prebuilt_tags,
        "user_tags": user_tags,
        "total_tags": prebuilt_tags.count() + user_tags.count(),
        "contacts_tagged": contacts_tagged,
        "contacts_untagged": contacts_untagged,
    }
    return render(request, 'tag_list.html', context)

@login_required
def create_tag(request):
    if request.method == "POST":
        name = request.POST.get("name")
        if name:
            tag, created = Tag.objects.get_or_create(name=name, user=request.user)
            print(tag)
            return JsonResponse({"id": tag.id, "name": tag.name})
    return JsonResponse({"error": "Invalid data"}, status=400)

@login_required
def update_tag(request, tag_id):
    if request.method == "POST":
        tag = get_object_or_404(Tag, id=tag_id, user=request.user, is_prebuilt=False)
        name = request.POST.get("name", "").strip()
        if not name:
            return JsonResponse({"error": "Tag name cannot be empty."}, status=400)
        tag.name = name
        try:
            tag.save()
        except IntegrityError:
            return JsonResponse({"error": "You already have a tag with that name."}, status=400)
        return JsonResponse({"id": tag.id, "name": tag.name})
    return JsonResponse({"error": "Invalid request"}, status=400)

@login_required
def delete_tag(request, tag_id):
    if request.method == "POST":
        tag = get_object_or_404(Tag, id=tag_id, user=request.user, is_prebuilt=False)
        tag.delete()
        return JsonResponse({"success": True})
    return JsonResponse({"error": "Invalid request"}, status=400)



@login_required
@feature_required('feature_flows')
def flow_list(request):
    flows = Flow.objects.filter(user=request.user).order_by('-updated_at')
    total_flows = flows.count()
    active_flows = sum(1 for f in flows if f.is_active)
    return render(request, "flow_list.html", {
        "flows": flows,
        "total_flows": total_flows,
        "active_flows": active_flows,
        "inactive_flows": total_flows - active_flows,
    })


@login_required
@require_POST
def flow_create(request):
    current_flows = Flow.objects.filter(user=request.user).count()
    allowed, limit = billing.check_limit(request.user, billing.MAX_FLOWS, current_flows)
    if not allowed:
        messages.error(request, f"Your plan allows up to {limit} flow(s). Upgrade your plan to create more.")
        return redirect('flow_list')

    name = request.POST.get("name", "").strip() or "Untitled Flow"
    flow = Flow.objects.create(user=request.user, name=name)
    return redirect('flow_builder', flow_id=flow.id)


@login_required
@require_POST
def flow_delete(request, flow_id):
    flow = get_object_or_404(Flow, id=flow_id, user=request.user)
    flow.delete()
    messages.success(request, "Flow deleted.")
    return redirect('flow_list')


@login_required
@require_POST
def flow_toggle_active(request, flow_id):
    flow = get_object_or_404(Flow, id=flow_id, user=request.user)
    flow.is_active = not flow.is_active
    flow.save(update_fields=["is_active"])
    return JsonResponse({"success": True, "is_active": flow.is_active})


@login_required
def flow_builder(request, flow_id):
    flow = get_object_or_404(Flow, id=flow_id, user=request.user)
    nodes = []
    for node in flow.nodes.all():
        nodes.append({
            "client_key": node.client_key,
            "title": node.title,
            "message_type": node.message_type,
            "body_text": node.body_text,
            "media_id": node.media_id,
            "media_filename": node.media_filename,
            "pos_x": node.pos_x,
            "pos_y": node.pos_y,
            "is_end": node.is_end,
            "is_start": flow.start_node_id == node.id,
            "capture_variable": node.capture_variable,
            "capture_sensitive": node.capture_sensitive,
            "api_url": node.api_url,
            "api_method": node.api_method,
            "api_body_type": node.api_body_type,
            "api_headers": node.api_headers or {},
            "api_body": node.api_body or {},
            "api_response_mapping": node.api_response_mapping or {},
            "buttons": [
                {"text": b.text, "kind": b.kind, "next_client_id": b.next_node.client_key if b.next_node else None}
                for b in node.buttons.all()
            ],
        })
    context = {
        "flow": flow,
        "flow_json": _safe_json_for_script({
            "id": flow.id,
            "name": flow.name,
            "trigger_keywords": flow.trigger_keywords or [],
            "trigger_any_message": flow.trigger_any_message,
            "is_active": flow.is_active,
            "nodes": nodes,
        }),
    }
    return render(request, "flow_builder.html", context)


@login_required
@require_POST
def flow_save(request, flow_id):
    flow = get_object_or_404(Flow, id=flow_id, user=request.user)
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid data."}, status=400)

    name = (payload.get("name") or "").strip()
    if not name:
        return JsonResponse({"success": False, "error": "Flow name is required."}, status=400)

    trigger_keywords = [
        k.strip().lower() for k in payload.get("trigger_keywords", []) if isinstance(k, str) and k.strip()
    ]
    is_active = bool(payload.get("is_active"))

    # Two active flows sharing a trigger keyword would make "which one runs"
    # undefined (arbitrary DB row order) — so we block the ambiguity here
    # instead of leaving it to chance at webhook time.
    if is_active and trigger_keywords:
        other_active_flows = Flow.objects.filter(user=request.user, is_active=True).exclude(id=flow.id)
        for other in other_active_flows:
            clash = set(trigger_keywords) & {k.lower() for k in (other.trigger_keywords or [])}
            if clash:
                return JsonResponse({
                    "success": False,
                    "error": "The keyword \"{}\" is already used by another active flow, \"{}\". "
                             "Only one active flow can use a given trigger keyword - "
                             "pause that flow, change its keyword, or remove it from this flow."
                             .format(sorted(clash)[0], other.name),
                }, status=400)

    flow.name = name
    flow.trigger_keywords = trigger_keywords
    flow.trigger_any_message = bool(payload.get("trigger_any_message"))
    flow.is_active = is_active

    nodes_payload = payload.get("nodes", [])
    node_by_key = {}
    seen_keys = []
    start_key = None

    for n in nodes_payload:
        key = (n.get("client_key") or "").strip()
        if not key:
            continue
        seen_keys.append(key)
        api_headers = n.get("api_headers")
        api_body = n.get("api_body")
        api_response_mapping = n.get("api_response_mapping")
        node, _ = FlowNode.objects.update_or_create(
            flow=flow, client_key=key,
            defaults={
                "title": (n.get("title") or "")[:255],
                "message_type": n.get("message_type") if n.get("message_type") in dict(FlowNode.MESSAGE_TYPE_CHOICES) else "text",
                "body_text": n.get("body_text") or "",
                "media_id": n.get("media_id") or "",
                "media_filename": n.get("media_filename") or "",
                "pos_x": float(n.get("pos_x") or 40),
                "pos_y": float(n.get("pos_y") or 40),
                "is_end": bool(n.get("is_end")),
                "capture_variable": (n.get("capture_variable") or "").strip()[:100],
                "capture_sensitive": bool(n.get("capture_sensitive")),
                "api_url": (n.get("api_url") or "").strip()[:500],
                "api_method": (n.get("api_method") or "POST").strip().upper()[:10],
                "api_body_type": n.get("api_body_type") if n.get("api_body_type") in dict(FlowNode.API_BODY_TYPE_CHOICES) else "json",
                "api_headers": api_headers if isinstance(api_headers, dict) else {},
                "api_body": api_body if isinstance(api_body, dict) else {},
                "api_response_mapping": api_response_mapping if isinstance(api_response_mapping, dict) else {},
            },
        )
        node_by_key[key] = node
        if n.get("is_start"):
            start_key = key

    # Nodes removed on the canvas since the last save -> remove from the DB too.
    FlowNode.objects.filter(flow=flow).exclude(client_key__in=seen_keys).delete()

    # Buttons have no identity worth preserving across saves — rebuild them.
    for n in nodes_payload:
        node = node_by_key.get((n.get("client_key") or "").strip())
        if not node:
            continue
        node.buttons.all().delete()
        for i, b in enumerate((n.get("buttons") or [])[:3]):
            text = (b.get("text") or "").strip()[:20]
            if not text:
                continue
            kind = b.get("kind") if b.get("kind") in dict(FlowButton.KIND_CHOICES) else "reply"
            next_node = node_by_key.get((b.get("next_client_id") or "").strip())
            FlowButton.objects.create(node=node, text=text, kind=kind, order=i, next_node=next_node)

    flow.start_node = node_by_key.get(start_key) or (node_by_key[seen_keys[0]] if seen_keys else None)
    flow.save()

    return JsonResponse({"success": True})


def _build_flow_node_payload(node, to_number, variables=None):
    """Mirrors the Cloud API payload shapes used elsewhere in this file
    (see create_campaign) — text/image/video/document, or an interactive
    button message whenever the node has reply buttons attached. Only
    kind="reply" edges are real WhatsApp buttons — a "capture" node's
    "next" edge and an "api_call" node's "success"/"failure" edges are
    flow-control only and must never be sent to the contact.

    `variables` fills {{name}} placeholders in the text/media_id/filename
    — e.g. a message that shows "Net pay: {{net_pay}}" after an API Call
    node fetched it, or a document node whose media_id is {{slip_media_id}}
    (a media_id an API Call node uploaded to WhatsApp on this node's behalf)."""
    variables = variables or {}
    body_text = _render_template(node.body_text or "", variables)
    media_id = _render_template(node.media_id or "", variables)
    media_filename = _render_template(node.media_filename or "", variables)
    buttons = list(node.buttons.filter(kind="reply"))

    if buttons:
        interactive = {"type": "button", "body": {"text": body_text.strip() or " "}}
        if node.message_type == "image" and media_id:
            interactive["header"] = {"type": "image", "image": {"id": media_id}}
        elif node.message_type == "video" and media_id:
            interactive["header"] = {"type": "video", "video": {"id": media_id}}
        elif node.message_type == "document" and media_id:
            doc = {"id": media_id}
            if media_filename:
                doc["filename"] = media_filename
            interactive["header"] = {"type": "document", "document": doc}

        interactive["action"] = {
            "buttons": [
                {"type": "reply", "reply": {"id": f"flowbtn_{b.id}", "title": _render_template(b.text, variables)}}
                for b in buttons
            ]
        }
        return {
            "messaging_product": "whatsapp", "recipient_type": "individual", "to": to_number,
            "type": "interactive", "interactive": interactive,
        }

    if node.message_type == "image" and media_id:
        image_obj = {"id": media_id}
        if body_text:
            image_obj["caption"] = body_text
        return {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to_number, "type": "image", "image": image_obj}

    if node.message_type == "video" and media_id:
        video_obj = {"id": media_id}
        if body_text:
            video_obj["caption"] = body_text
        return {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to_number, "type": "video", "video": video_obj}

    if node.message_type == "document" and media_id:
        doc_obj = {"id": media_id}
        if body_text:
            doc_obj["caption"] = body_text
        if media_filename:
            doc_obj["filename"] = media_filename
        return {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to_number, "type": "document", "document": doc_obj}

    return {
        "messaging_product": "whatsapp", "recipient_type": "individual", "to": to_number,
        "type": "text", "text": {"body": body_text, "preview_url": False},
    }


def _send_flow_node(user, to_number, node, variables=None):
    try:
        profile = UserProfile.objects.get(user=user)
    except UserProfile.DoesNotExist:
        return
    if not (profile.phone_number_id and profile.api_key):
        _safe_print(f"[Flow] cannot send node {node.id} - {user.username} has no connected phone_number_id/api_key.")
        return

    payload = _build_flow_node_payload(node, to_number, variables)
    graph_version = settings.META_GRAPH_API_VERSION
    url = f"https://graph.facebook.com/{graph_version}/{profile.phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {profile.api_key}", "Content-Type": "application/json"}
    try:
        response = requests.post(url, json=payload, headers=headers)
        _safe_print(f"[Flow] sent node {node.id} to {to_number}: {response.status_code} {response.text}")
        try:
            flow_response_json = response.json()
        except ValueError:
            flow_response_json = {}
        chat_log.record_outbound(user, to_number, payload, flow_response_json, response.ok, "flow")
    except Exception as e:
        _safe_print(f"[Flow] error sending node {node.id} message:", e)


def _render_template(value, variables):
    """Fills {{variable}} placeholders (in strings, or recursively inside
    dicts/lists) from a ContactFlowState's captured variables — e.g. an
    api_headers value of "Bearer {{access_token}}"."""
    if isinstance(value, str):
        def repl(m):
            return str(variables.get(m.group(1).strip(), ""))
        return re.sub(r"\{\{\s*([\w.]+)\s*\}\}", repl, value)
    if isinstance(value, dict):
        return {k: _render_template(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [_render_template(v, variables) for v in value]
    return value


def _extract_path(data, path):
    """Pulls a value out of a parsed JSON response by dot-path, e.g.
    "data.access_token" or "items.0.id"."""
    current = data
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return current


def _extract_css(html_text, selector):
    """Pulls the text content of the first element matching a CSS
    selector out of an HTML page — for the very common case where an
    internal dashboard (any platform, not a JSON API) just renders a
    number/value inside some element. Use the browser's own "Inspect
    Element" on the real page to find the right selector (e.g. right-click
    the number -> Inspect -> read its class/id off the highlighted tag).
    An optional "|attr:name" suffix reads that attribute instead of text,
    e.g. "a.download-link|attr:href"."""
    from bs4 import BeautifulSoup
    attr = None
    if "|attr:" in selector:
        selector, attr = selector.split("|attr:", 1)
    try:
        soup = BeautifulSoup(html_text or "", "html.parser")
        el = soup.select_one(selector.strip())
    except Exception:
        return None
    if el is None:
        return None
    if attr:
        return el.get(attr.strip())
    return el.get_text(strip=True)


def _extract_regex(text, pattern):
    """Pulls a value out of any raw response text (HTML, plain text,
    whatever) by regex — the most platform-agnostic extraction available,
    since it doesn't care about markup at all, just the surrounding text.
    Returns the first capture group if the pattern has one, otherwise the
    whole match."""
    try:
        m = re.search(pattern, text or "", re.DOTALL)
    except re.error:
        return None
    if not m:
        return None
    return m.group(1) if m.groups() else m.group(0)


def _extract_near_label(html_text, label):
    """The non-technical option: type the exact label text you see on the
    page (e.g. "Payable Salary", "Username", "First Name") and this finds
    the value next to it — a number, a name, an email, anything — no
    regex or CSS knowledge required.

    Primary strategy: most dashboards mark up a label and its value as
    sibling elements (<label>Username</label><p>info@dovix.ai</p>, or
    <span class="amount-label">Gross</span><span class="amount-value">
    ...</span>) — so this looks for the element whose OWN text is EXACTLY
    the label, then reads the next sibling element's text, whatever it
    is. Matching the *exact* text of a whole element (not just "label
    appears somewhere nearby") also naturally tells apart a real label
    from an unrelated heading that happens to contain the same words —
    e.g. a page title "Payable Salary — September 2026" doesn't exactly
    equal "Payable Salary", so it's correctly skipped in favor of the
    actual <span class="amount-label">Payable Salary</span>.

    Fallback: if the label and value aren't separate sibling elements
    (just adjacent text), grabs the number right after it instead — a
    match with a currency symbol next to it wins over a bare one (so a
    trailing year in a heading loses to a real amount), and among ties
    the last occurrence wins, since headings read first and the actual
    figure tends to appear later in the page."""
    if not label:
        return None
    label = label.strip()
    from bs4 import BeautifulSoup
    try:
        soup = BeautifulSoup(html_text or "", "html.parser")
    except Exception:
        soup = None

    if soup is not None:
        for node in soup.find_all(string=lambda s: s and s.strip() == label):
            label_el = node.parent
            if label_el is None:
                continue
            # Tier 1: a value sitting right after the label WITHIN the
            # same element, e.g. "Working Days <span>24</span>" — the
            # label text and its value share one parent, no separate
            # sibling tag involved.
            sib = node.next_sibling
            while sib is not None:
                value = sib.get_text(strip=True) if hasattr(sib, "get_text") else str(sib).strip()
                if value:
                    return value.lstrip("₹$€£").strip()
                sib = sib.next_sibling
            # Tier 2: label and value are separate sibling elements, e.g.
            # <label>Username</label><p>info@dovix.ai</p>.
            sib = label_el.find_next_sibling()
            while sib is not None:
                value = sib.get_text(strip=True)
                if value:
                    return value.lstrip("₹$€£").strip()
                sib = sib.find_next_sibling()

    text = soup.get_text(separator=" ", strip=True) if soup is not None else (html_text or "")
    pattern = re.escape(label) + r".{0,40}?(?P<symbol>[₹$€£])?\s*(?P<value>[\d][\d,]*\.?\d{0,2})"
    matches = list(re.finditer(pattern, text, re.DOTALL))
    if not matches:
        return None
    with_symbol = [m for m in matches if m.group("symbol")]
    candidates = with_symbol or matches
    return candidates[-1].group("value")


def _safe_print(*args, **kwargs):
    """print() that never raises on a Windows console using a legacy
    codepage (e.g. cp1252) that can't represent a captured/scraped value
    like a rupee sign or emoji — replaces what it can't show instead of
    crashing mid-flow and silently aborting the conversation."""
    text = " ".join(str(a) for a in args)
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    safe_text = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
    print(safe_text, **kwargs)


def _mask_secret(value):
    """Shows just enough of a value to recognize it without exposing it in
    logs — used for anything header/variable-named like a token or key."""
    s = "" if value is None else str(value)
    if len(s) <= 8:
        return "***"
    return f"{s[:4]}...{s[-4:]}"


def _looks_secret(name):
    name = (name or "").lower()
    return any(word in name for word in ("auth", "key", "token", "secret", "password", "pwd"))


def _log_safe_dict(d):
    return {k: (_mask_secret(v) if _looks_secret(k) else v) for k, v in (d or {}).items()}


def _truncate_for_log(value, limit=600):
    s = value if isinstance(value, str) else json.dumps(value, default=str)
    return s if len(s) <= limit else f"{s[:limit]}...(truncated, {len(s)} chars total)"


def _guess_filename_from_response(response, content_type):
    disposition = response.headers.get("Content-Disposition", "")
    m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', disposition)
    if m:
        return m.group(1).strip()
    ext = mimetypes.guess_extension((content_type or "").split(";")[0].strip()) or ""
    return f"file{ext}"


def _upload_response_as_media(user, response):
    """Uploads a raw (non-JSON) API response body straight to WhatsApp as
    media, and returns the resulting media_id (or None on failure). Used
    when an "api_call" node's response mapping asks for "file" — e.g. a
    PDF salary slip. We fetch it ourselves (using this conversation's own
    carried-forward session) rather than asking Meta to fetch it, so this
    works identically whether the source URL is public or requires being
    logged in, on any backend platform."""
    try:
        profile = UserProfile.objects.get(user=user)
    except UserProfile.DoesNotExist:
        return None
    if not (profile.phone_number_id and profile.api_key):
        return None

    content_type = (response.headers.get("Content-Type") or "application/octet-stream").split(";")[0].strip()
    filename = _guess_filename_from_response(response, content_type)
    graph_version = settings.META_GRAPH_API_VERSION
    url = f"https://graph.facebook.com/{graph_version}/{profile.phone_number_id}/media"
    headers = {"Authorization": f"Bearer {profile.api_key}"}
    files = {"file": (filename, response.content, content_type)}
    data = {"messaging_product": "whatsapp"}
    try:
        upload_response = requests.post(url, headers=headers, files=files, data=data)
        result = upload_response.json()
        _safe_print(f"[Flow API]   uploaded response body as WhatsApp media "
              f"({content_type}, {len(response.content)} bytes, filename={filename}): "
              f"{upload_response.status_code} {result}")
        return result.get("id")
    except Exception as e:
        _safe_print(f"[Flow API]   failed to upload response body as media: {e}")
        return None


def _execute_api_call_node(state, node):
    """Calls the client-configured external API for an "api_call" node,
    filling {{variable}} placeholders from this contact's captured
    variables, and saves the mapped response fields back onto the state.
    Returns True on a 2xx response, False otherwise (drives the
    success/failure branch in _process_and_send). Every step is logged
    with a "[Flow API]" prefix (secrets masked) so a misbehaving client
    integration can be diagnosed straight from the server log."""
    variables = state.variables or {}
    method = (node.api_method or "POST").upper()
    url = _render_template(node.api_url or "", variables)
    headers = _render_template(node.api_headers or {}, variables)
    body = _render_template(node.api_body or {}, variables)
    # Carried forward from any earlier API Call node this conversation has
    # already run — the way a browser keeps cookies between requests to
    # the same site. This is what makes a Django-style flow work: fetch a
    # CSRF cookie on a GET, then that cookie rides along on the POST.
    cookies = dict(state.cookies or {})

    body_type = node.api_body_type or "json"
    label = node.title or node.client_key
    _safe_print(f"[Flow API] node {node.id} ('{label}') -> {method} {url}")
    if headers:
        _safe_print(f"[Flow API]   headers: {_log_safe_dict(headers)}")
    if body:
        _safe_print(f"[Flow API]   body ({body_type}): {_truncate_for_log(body)}")
    if cookies:
        _safe_print(f"[Flow API]   cookies carried forward: {list(cookies.keys())}")

    ok = False
    data = {}
    response = None
    response_cookies = {}
    try:
        # A JSON API expects json=; a classic HTML-form endpoint (like
        # Django's request.POST, which never sees a raw JSON body) needs
        # data= instead, which sends application/x-www-form-urlencoded.
        if body_type == "form":
            response = requests.request(method, url, headers=headers, data=(body or None), cookies=cookies, timeout=15)
        else:
            response = requests.request(method, url, headers=headers, json=(body or None), cookies=cookies, timeout=15)
        ok = response.ok
        # A login view commonly responds with a redirect (302 -> the
        # dashboard) and sets the session cookie on THAT hop, not on the
        # final page it redirects to — response.cookies alone only reflects
        # the last response, silently dropping anything set earlier in the
        # chain. Merge cookies from every hop so nothing gets lost.
        response_cookies = {}
        for hop in list(response.history) + [response]:
            response_cookies.update(hop.cookies.get_dict())
        try:
            data = response.json()
        except ValueError:
            data = {}
        _safe_print(f"[Flow API]   <- {response.status_code} {'OK' if ok else 'NOT OK'} : {_truncate_for_log(response.text)}")
        if response_cookies:
            _safe_print(f"[Flow API]   received cookies: {list(response_cookies.keys())}")
    except Exception as e:
        _safe_print(f"[Flow API]   <- request failed before the client ever responded: {e}")

    # New/updated cookies carry forward regardless of this call's own
    # success/failure — a CSRF cookie is often set on a perfectly normal
    # 200 that isn't "the API call" itself, just the page that hands it out.
    cookies.update(response_cookies)
    state.cookies = cookies

    saved = {}
    if ok:
        for varname, path in (node.api_response_mapping or {}).items():
            if not varname or not path:
                continue
            if path == "file":
                # The response itself is the file (a PDF, image, etc.) —
                # fetched with this conversation's own session, so it works
                # regardless of whether the source URL is public or
                # requires login, and regardless of what backend serves it.
                value = _upload_response_as_media(state.user, response) if response is not None else None
            elif path.startswith("cookie."):
                value = cookies.get(path[len("cookie."):])
            elif path.startswith("label:"):
                # The easy, non-technical option — type the label text
                # visible on the page and this grabs the number after it.
                value = _extract_near_label(response.text, path[len("label:"):]) if response is not None else None
            elif path.startswith("css:"):
                # For a plain HTML page (a dashboard, not a JSON API) —
                # pulls the text of the first element matching a CSS
                # selector, found via "Inspect Element" on the real page.
                value = _extract_css(response.text, path[len("css:"):]) if response is not None else None
            elif path.startswith("regex:"):
                # The most universal option — matches any pattern in the
                # raw response text regardless of markup/format.
                value = _extract_regex(response.text, path[len("regex:"):]) if response is not None else None
            else:
                value = _extract_path(data, path)
            variables[varname] = value
            saved[varname] = value
        if saved:
            _safe_print(f"[Flow API]   saved variables: {_log_safe_dict(saved)}")
        elif node.api_response_mapping:
            _safe_print(f"[Flow API]   response mapping configured but nothing matched - check the field paths")

    state.variables = variables
    # A password (or anything else marked "sensitive" when captured) has
    # now been used to log in — it doesn't need to sit in the database
    # any longer than that, regardless of whether this call succeeded.
    purged = [k for k in (state.sensitive_keys or []) if k in variables]
    for key in (state.sensitive_keys or []):
        variables.pop(key, None)
    if purged:
        _safe_print(f"[Flow API]   discarded sensitive variable(s) now that they've been used: {purged}")
    state.sensitive_keys = []
    state.save()

    _safe_print(f"[Flow API] node {node.id} ('{label}') result: {'SUCCESS' if ok else 'FAILURE'} branch")
    return ok


def _node_edge(node, kind):
    return node.buttons.filter(kind=kind).select_related("next_node").first()


def _process_and_send(user, sender_id, state, node, depth=0):
    """Sends `node` to the contact and parks the conversation there —
    except "api_call" nodes, which run immediately (no user input needed)
    and recurse straight into their success/failure edge. `depth` guards
    against a misconfigured API loop (e.g. success -> itself) hanging the
    webhook request forever."""
    if depth > 10:
        _safe_print(f"[Flow] stopped after 10 auto-processed nodes in a row for {user.username}/{sender_id} - "
              f"check for a success/failure edge that loops back on itself.")
        return

    if node.message_type == "api_call":
        ok = _execute_api_call_node(state, node)
        branch = "success" if ok else "failure"
        edge = _node_edge(node, branch)
        if edge and edge.next_node:
            _safe_print(f"[Flow] node {node.id} -> following '{branch}' edge to node {edge.next_node.id} "
                  f"('{edge.next_node.title or edge.next_node.client_key}') for {sender_id}")
            _process_and_send(user, sender_id, state, edge.next_node, depth + 1)
        else:
            _safe_print(f"[Flow] node {node.id} has no '{branch}' edge connected - ending the conversation for {sender_id}.")
            state.delete()
        return

    _send_flow_node(user, sender_id, node, state.variables)
    state.current_node = node
    state.save()
    if node.is_end:
        _safe_print(f"[Flow] node {node.id} is an End message - closing the session for {sender_id}")
        state.delete()


def _find_matching_flow(user, text):
    """Trigger-keyword lookup done in Python rather than a JSONField query —
    SQLite doesn't support list-containment lookups the way Postgres does,
    and the per-user flow count is small enough that this is plenty fast."""
    text = (text or "").strip().lower()
    if not text:
        return None
    fallback = None
    for flow in Flow.objects.filter(user=user, is_active=True).order_by("id"):
        if text in [k.lower() for k in (flow.trigger_keywords or [])]:
            return flow
        if flow.trigger_any_message and fallback is None:
            fallback = flow
    return fallback


def _handle_flow_message(user, sender_id, message, message_type):
    """Advances (or starts) a contact's position in one of this user's
    flows. Runs independently of the opt-out check below — a message can
    be relevant to both. Order matters here: a contact mid-"capture" (e.g.
    asked for their email) must have their next text saved as the answer
    *before* it's ever checked against trigger keywords — otherwise typing
    an email that happens to match another flow's keyword would wrongly
    restart that flow instead of logging in."""
    state = (
        ContactFlowState.objects.filter(user=user, mobile_number=sender_id)
        .select_related("current_node", "flow")
        .first()
    )

    if state and state.current_node and state.current_node.message_type == "capture":
        if message_type != "text":
            # Re-prompt — we're waiting on a typed answer, not this.
            _send_flow_node(user, sender_id, state.current_node, state.variables)
            return
        answer = message.get("text", {}).get("body", "").strip()
        if not answer:
            return
        node = state.current_node
        variables = state.variables or {}
        if node.capture_variable:
            variables[node.capture_variable] = answer
        state.variables = variables
        if node.capture_sensitive and node.capture_variable:
            sensitive_keys = state.sensitive_keys or []
            if node.capture_variable not in sensitive_keys:
                sensitive_keys.append(node.capture_variable)
            state.sensitive_keys = sensitive_keys
        state.save()

        if node.capture_variable:
            shown = "***hidden (sensitive)***" if node.capture_sensitive else answer[:80]
            _safe_print(f"[Flow] node {node.id} captured '{node.capture_variable}' = '{shown}' for {sender_id}")

        edge = _node_edge(node, "next")
        if edge and edge.next_node:
            _process_and_send(user, sender_id, state, edge.next_node)
        else:
            state.delete()
        return

    if message_type == "interactive":
        interactive = message.get("interactive", {})
        if interactive.get("type") != "button_reply":
            return
        reply_id = interactive.get("button_reply", {}).get("id", "")
        if not reply_id.startswith("flowbtn_"):
            return
        try:
            button_id = int(reply_id.split("_", 1)[1])
        except ValueError:
            return

        button = FlowButton.objects.filter(id=button_id, node__flow__user=user).select_related("node__flow", "next_node").first()
        if not button:
            return

        if not state:
            state = ContactFlowState.objects.create(
                user=user, mobile_number=sender_id, flow=button.node.flow, current_node=button.node,
            )

        if button.next_node:
            _process_and_send(user, sender_id, state, button.next_node)
        else:
            # Button isn't wired to another message — treat as the end of the flow.
            state.delete()
        return

    if message_type == "text":
        text = message.get("text", {}).get("body", "")
        flow = _find_matching_flow(user, text)
        if flow and flow.start_node:
            # A fresh trigger always starts clean — no stale variables or
            # position left over from a previous, unrelated conversation.
            ContactFlowState.objects.filter(user=user, mobile_number=sender_id).delete()
            new_state = ContactFlowState.objects.create(
                user=user, mobile_number=sender_id, flow=flow, current_node=flow.start_node,
            )
            _process_and_send(user, sender_id, new_state, flow.start_node)


def _handle_status_update(status_update):
    """One entry from a webhook's `value.statuses[]` — Meta's per-message
    delivery status for a wamid we sent. Looked up against CampaignMessage
    (populated at send time by send_message_to_user) so the count on each
    campaign's analytics page reflects only messages *that campaign* sent,
    instead of Meta's template_analytics endpoint, which lumps together
    every campaign that ever used the same template."""
    wamid = status_update.get("id")
    status_type = status_update.get("status")  # sent | delivered | read | failed
    if not wamid or not status_type:
        return

    # Keep the Messages inbox's ticks/failures in sync too. Done first and
    # independently: a message sent from the chat, a flow or the API has no
    # CampaignMessage row, but still needs its status updated.
    chat_log.apply_status(wamid, status_type, timezone.now(), status_update.get("errors"))

    try:
        msg = CampaignMessage.objects.get(wamid=wamid)
    except CampaignMessage.DoesNotExist:
        # Not one of ours (e.g. sent before this tracking existed, or via
        # the external send-message API, which isn't tied to a campaign).
        return

    timestamp = status_update.get("timestamp")
    when = timezone.make_aware(datetime.fromtimestamp(int(timestamp))) if timestamp else timezone.now()

    # Statuses arrive in order (sent -> delivered -> read) but a later one
    # should never get clobbered by a stale/out-of-order duplicate webhook —
    # each stage only records its own timestamp once, and `status` only
    # ever moves forward, never backward.
    STAGE_RANK = {"queued": 0, "sent": 1, "delivered": 2, "read": 3, "failed": 4}

    if status_type == "sent":
        msg.sent_at = msg.sent_at or when
    elif status_type == "delivered":
        msg.delivered_at = msg.delivered_at or when
    elif status_type == "read":
        msg.read_at = msg.read_at or when
    elif status_type == "failed":
        msg.failed_at = msg.failed_at or when
        errors = status_update.get("errors") or []
        if errors:
            err = errors[0]
            msg.error_code = str(err.get("code", ""))
            msg.error_title = err.get("title", "")
            msg.error_message = err.get("message", "")
            msg.error_details = (err.get("error_data") or {}).get("details", "")
    else:
        return

    if STAGE_RANK.get(status_type, 0) > STAGE_RANK.get(msg.status, 0):
        msg.status = status_type
    msg.save()


def _attribute_campaign_reply(message, message_type):
    """If this inbound message quotes/replies to a message we sent as part
    of a campaign (`context.id` == that message's wamid), record it as a
    reply — and, for a button tap, also as a click. Only quick-reply/
    interactive button taps are attributable this way; Meta doesn't report
    per-message clicks for URL buttons over the webhook."""
    context_id = message.get("context", {}).get("id")
    if not context_id:
        return

    now = timezone.now()
    CampaignMessage.objects.filter(wamid=context_id, replied_at__isnull=True).update(replied_at=now)
    if message_type in ("button", "interactive"):
        CampaignMessage.objects.filter(wamid=context_id, clicked_at__isnull=True).update(clicked_at=now)


def _opt_out_contact_by_number(mobile_number, owner_user=None):
    """Shared by both opt-out triggers (template QUICK_REPLY 'Stop Promotions'
    and the interactive 'Unsubscribe' reply button on text/image/document
    campaigns) so a contact opting out either way is recorded the same way.

    `owner_user` is the account whose WhatsApp number received the "stop" —
    several accounts can now hold the same customer number, and opting out
    of one business must not opt them out of another. If the owner couldn't
    be determined, only act when exactly one account has this number (so
    it's unambiguous); otherwise skip rather than guess."""
    print(f"User {mobile_number} has opted out of promotions.")
    contacts = Contact.objects.filter(mobile_number=mobile_number)
    if owner_user is not None:
        contacts = contacts.filter(user=owner_user)
    matches = list(contacts[:2])

    if not matches:
        print(f"Contact {mobile_number} not found in the database.")
        return
    if len(matches) > 1:
        print(f"Contact {mobile_number} exists in several accounts and the receiving account is unknown — skipped.")
        return

    contact = matches[0]
    OptOutUser.objects.get_or_create(user=contact.user, contact=contact)


@csrf_exempt
def whatsapp_webhook(request):
    verify_token = settings.META_WEBHOOK_VERIFY_TOKEN


    # Handling verification requests from Meta
    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")

        if mode == "subscribe" and token == verify_token:
            return HttpResponse(challenge, content_type="text/plain")

        return JsonResponse({"error": "Verification failed"}, status=403)

    # Handling actual incoming messages
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            print("Received Webhook Data:", json.dumps(data, indent=2))

            for entry in data.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    field = change.get("field")

                    # Embedded Signup completion/removal notifications. This
                    # arrives independently of the JS embedded-signup callback
                    # (which is what actually saves wba_id/phone_number_id/
                    # api_key onto the right UserProfile, since it runs in the
                    # signed-in customer's own browser session). This webhook
                    # has no session context to tell us *which* Django user it
                    # belongs to, so we can only correlate it after that
                    # callback has already saved a matching wba_id — treat it
                    # as a confirmation/audit signal, not the primary path.
                    if field == "account_update":
                        account_event = value.get("event")
                        waba_id = value.get("waba_info", {}).get("waba_id")
                        print(f"Account update: {account_event} for WABA {waba_id}")

                        if account_event == "PARTNER_ADDED" and waba_id:
                            updated = UserProfile.objects.filter(wba_id=waba_id).update(
                                meta_connected_at=timezone.now()
                            )
                            if not updated:
                                print(f"No UserProfile found yet for WABA {waba_id} (PARTNER_ADDED) — "
                                      "embedded signup callback may not have run yet.")

                        elif account_event == "PARTNER_REMOVED" and waba_id:
                            UserProfile.objects.filter(wba_id=waba_id).update(
                                wba_id=None,
                                phone_number_id=None,
                                business_id=None,
                                api_key=None,
                                meta_connected_at=None,
                            )
                            print(f"Cleared connection details for WABA {waba_id} (PARTNER_REMOVED)")

                        continue

                    # Ensure 'messages' key exists
                    if "messages" in value:
                        # This webhook is shared across every business on the
                        # platform — figure out which of our users this
                        # message was sent TO (their connected number) so
                        # flow lookups only ever consider that user's flows.
                        phone_number_id = value.get("metadata", {}).get("phone_number_id")
                        owner_profile = UserProfile.objects.filter(phone_number_id=phone_number_id).first() if phone_number_id else None

                        # The name each customer set on their own WhatsApp.
                        profile_names = {
                            c.get("wa_id"): (c.get("profile") or {}).get("name", "")
                            for c in value.get("contacts", [])
                        }

                        for message in value["messages"]:
                            sender_id = message.get("from")
                            message_type = message.get("type")

                            # Store it in this account's Messages inbox first,
                            # so it's kept even if flow handling below errors.
                            if owner_profile:
                                chat_log.record_inbound(owner_profile.user, message, profile_names)

                            if owner_profile:
                                try:
                                    _handle_flow_message(owner_profile.user, sender_id, message, message_type)
                                except Exception as e:
                                    print("Flow handling error:", e)

                            # A reply/button-tap that quotes one of our sent
                            # messages carries that message's wamid in
                            # `context.id` — attribute it to whichever
                            # campaign sent it, regardless of message type.
                            try:
                                _attribute_campaign_reply(message, message_type)
                            except Exception as e:
                                print("Campaign reply attribution error:", e)

                            # Handling text messages
                            if message_type == "text":
                                message_text = message.get("text", {}).get("body", "").strip().lower()
                                print(f"Text Message from {sender_id}: {message_text}")

                                if message_text == "stop promotions":
                                    _opt_out_contact_by_number(sender_id, owner_profile.user if owner_profile else None)

                            # Handling button click messages (template QUICK_REPLY buttons)
                            elif message_type == "button":
                                button_payload = message.get("button", {}).get("payload", "").strip().lower()
                                print(f"Button Click from {sender_id}: {button_payload}")

                                if button_payload == "stop promotions":
                                    _opt_out_contact_by_number(sender_id, owner_profile.user if owner_profile else None)

                            # Handling interactive reply-button clicks (used by the
                            # "Add Unsubscribe Button" option on text/image/document
                            # campaigns, since those aren't sent as templates).
                            elif message_type == "interactive":
                                interactive = message.get("interactive", {})
                                if interactive.get("type") == "button_reply":
                                    reply_id = interactive.get("button_reply", {}).get("id", "").strip().lower()
                                    print(f"Interactive button reply from {sender_id}: {reply_id}")
                                    if reply_id == "unsubscribe":
                                        _opt_out_contact_by_number(sender_id, owner_profile.user if owner_profile else None)

                    # Handling per-message delivery status updates (sent/
                    # delivered/read/failed). This is what campaign_analytics
                    # is built from — see _handle_status_update.
                    elif "statuses" in value:
                        for status_update in value["statuses"]:
                            print(
                                f"Message {status_update.get('id')} to "
                                f"{status_update.get('recipient_id')} is now "
                                f"{status_update.get('status')}"
                            )
                            try:
                                _handle_status_update(status_update)
                            except Exception as e:
                                print("Status update handling error:", e)

                    # Coexistence: a message sent from the WhatsApp Business
                    # *phone app* on a number that's also on the Cloud API.
                    # Shown in the same conversation as a message we sent.
                    elif "message_echoes" in value:
                        echo_phone_id = value.get("metadata", {}).get("phone_number_id")
                        echo_owner = UserProfile.objects.filter(phone_number_id=echo_phone_id).first() if echo_phone_id else None
                        if echo_owner:
                            for echo in value["message_echoes"]:
                                chat_log.record_echo(echo_owner.user, echo)


            return JsonResponse({"status": "received"}, status=200)

        except json.JSONDecodeError:
            print("Error: Invalid JSON received")
            return JsonResponse({"error": "Invalid JSON"}, status=400)

    return JsonResponse({"status": "invalid request"}, status=400)

