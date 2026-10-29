from django.core.mail import send_mail
from django.shortcuts import render, redirect
from django.contrib import messages
from django.conf import settings
# from django.http import HttpResponse
# Create your views here.
def index(request):
    if request.user.is_authenticated:
        return redirect('services')
    return render(request,'index.html')
    # return HttpResponse('this is home page')
def about(request):
    return render(request,'about.html')
    # return HttpResponse('this is home page')

# def contact(request):
#     return render(request,'contact.html')




def contact(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        subject = request.POST.get('subject', '').strip()
        message = request.POST.get('message', '').strip()

        full_message = f"From: {name} <{email}>\n\n{message}"

        try:
            send_mail(
                subject=subject,
                message=full_message,
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=[settings.EMAIL_HOST_USER],
                fail_silently=False,
            )
            messages.success(request, 'Your message has been sent successfully!')
        except Exception as e:
            messages.error(request, f'Error sending message: {e}')

        return redirect('contact')  # use your contact page URL name

    return render(request, 'contact.html')

def pricing(request):
    return render(request,'pricing.html')

def faqs(request):
    return render(request,'faqs.html')

def privacy_policy(request):
    return render(request, 'privacy_policy.html')

def terms_of_service(request):
    return render(request, 'terms_of_service.html')

def how_it_works(request):
    return render(request,'how_it_works.html')

# steps to follow
def step1(request):
    return render(request,'steps/step1.html')