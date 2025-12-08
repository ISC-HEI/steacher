# Mailtrap Email Backend Setup

This project uses a custom Django email backend that sends emails via Mailtrap's HTTP API instead of SMTP. This is **significantly faster** than traditional SMTP (typically 10-100x faster).

## Why Mailtrap API Instead of SMTP?

- **Speed**: HTTP API calls are much faster than SMTP protocol
- **No connection overhead**: No TLS handshake or SMTP negotiation
- **Better error handling**: Structured JSON responses
- **Same reliability**: Same Mailtrap service, just faster protocol

## Setup Instructions

### 1. Install Dependencies

The `mailtrap` package is already in `requirements.txt`. Install it:

```bash
pip install -r requirements.txt
```

### 2. Get Your API Token

1. Log in to [Mailtrap](https://mailtrap.io)
2. Go to **API Tokens** → https://mailtrap.io/api-tokens
3. Create a new token or copy an existing one

**Note**: This is different from your SMTP credentials!

### 3. Configure Environment Variables

Add to your `.env` file:

```bash
MAILTRAP_API_KEY=your_api_token_here
DEFAULT_FROM_EMAIL=teachers@steacher.org
```

### 4. Restart Django

The backend is configured automatically when `MAILTRAP_API_KEY` is present:

```bash
python manage.py runserver
```

## Testing

Run the test script to verify everything works:

```bash
cd steacher_app
python test_mailtrap_backend.py
```

This will send three test emails:
1. Simple text email
2. HTML email
3. Magic link simulation (mobile auth)

## How It Works

### Automatic Backend Selection

The `settings.py` automatically chooses the email backend based on available credentials:

1. **If `MAILTRAP_API_KEY` is set**: Uses fast Mailtrap API backend
2. **Else if `MAIL_SMTP_LOGIN` is set**: Falls back to SMTP
3. **Else**: Uses console backend (prints to terminal)

### Configuration in settings.py

```python
MAILTRAP_API_KEY = os.getenv('MAILTRAP_API_KEY')

if MAILTRAP_API_KEY:
    EMAIL_BACKEND = 'exercises.mailtrap_backend.MailtrapBackend'
```

### Usage in Code

No changes needed! Use Django's standard email functions:

```python
from django.core.mail import send_mail

send_mail(
    subject='Your Subject',
    message='Your message',
    from_email=settings.DEFAULT_FROM_EMAIL,
    recipient_list=['user@example.com'],
)
```

For HTML emails:

```python
from django.core.mail import EmailMultiAlternatives

msg = EmailMultiAlternatives(
    subject='Your Subject',
    body='Plain text version',
    from_email=settings.DEFAULT_FROM_EMAIL,
    to=['user@example.com'],
)
msg.attach_alternative('<h1>HTML version</h1>', "text/html")
msg.send()
```

## Features Supported

✅ Plain text emails  
✅ HTML emails (via EmailMultiAlternatives)  
✅ Multiple recipients (to, cc, bcc)  
✅ Attachments  
✅ Custom headers  
✅ Email categories (via `X-Mailtrap-Category` header)

## Troubleshooting

### ImportError: mailtrap package not found

```bash
pip install mailtrap
```

### ValueError: MAILTRAP_API_KEY must be set

Make sure your `.env` file contains:
```
MAILTRAP_API_KEY=your_actual_token
```

And that you've restarted Django after adding it.

### Emails not arriving

1. Check Mailtrap dashboard for delivery status
2. Verify your sending domain is verified in Mailtrap
3. Check if recipient email is on suppression list
4. Look at Django logs for error messages

### Still slow on first email

The first email may still be slower due to:
- HTTP connection establishment
- DNS lookup for mailtrap.io
- API authentication

Subsequent emails will be much faster as connections are reused.

### University emails taking 1-2 minutes

**This is completely normal and expected** for university mail servers, even with verified domains.

#### Understanding the Timing

When you send an email to a university address (e.g., HEVS.CH), the total delivery time breaks down as:

1. **Your code → Mailtrap API: < 1 second** ✓ (this is fast and under your control)
2. **Mailtrap → University mail server: < 1 second** ✓ (also fast)
3. **University internal processing: 60-120 seconds** ⏱️ (this is the delay you observe)

**Example from actual HEVS.CH delivery:**
```
Sent by Mailtrap:  01:00:58 UTC
Received by HEVS:  01:00:59 UTC  (1 second - excellent!)
Delivered to inbox: 01:02:13 UTC  (74 seconds of HEVS processing)
```

#### Why University Mail Servers Take Longer

University mail servers (like HEVS.CH using Microsoft Office 365) perform extensive security processing:

- **SPF/DKIM/DMARC verification** - validates sender authenticity
- **Multiple spam filtering layers** - machine learning models, content analysis
- **Antivirus scanning** - checks attachments and embedded content  
- **Geographic routing** - emails route through multiple Exchange servers
- **Compliance checks** - university-specific policies and regulations
- **Mailbox delivery rules** - user-specific filters and forwarding

This processing is **intentional and cannot be bypassed**. Consumer services like Gmail skip many of these steps.

#### What You Should Do

1. **Verify your domain in Mailtrap** (critical for passing authentication)
   - Go to https://mailtrap.io/domains
   - Ensure steacher.org shows `✓ Verified` with SPF/DKIM/DMARC
   - Without verification, delays can be 5-60 minutes instead of 1-2 minutes

2. **Check Mailtrap dashboard** to confirm fast delivery to university servers
   - Look at Email Logs: https://mailtrap.io/inboxes
   - Status should show "delivered" within 1-2 seconds
   - Verify timestamp shows Mailtrap sent immediately

3. **Set user expectations** in your app messaging
   - Tell students: "Check your email - university mail takes 1-2 minutes"
   - This is normal, not a bug

#### Typical Delivery Times by Service

| Email Service | Expected Delivery Time |
|--------------|------------------------|
| Gmail | 1-10 seconds |
| Office 365 (personal) | 10-30 seconds |
| **Office 365 (enterprise like HEVS.CH)** | **60-120 seconds** |
| Government servers | 2-10 minutes |

**Your 1-2 minute delivery to HEVS.CH is right in the expected range.**

#### When to Investigate

Only investigate if:
- Mailtrap dashboard shows delays (> 5 seconds to send)
- Emails are marked as spam or bounced
- Delivery takes > 5 minutes consistently
- Domain shows as "not verified" in Mailtrap

Otherwise, accept that university mail processing takes time and is outside your control.

## Reverting to SMTP

If you need to revert to SMTP, just remove or comment out `MAILTRAP_API_KEY` from your `.env` file:

```bash
# MAILTRAP_API_KEY=...  # Commented out
```

The system will automatically fall back to SMTP if credentials are available.

## Production Deployment

For production, set the environment variable in your deployment:

**Docker Compose:**
```yaml
environment:
  - MAILTRAP_API_KEY=${MAILTRAP_API_KEY}
```

**Heroku:**
```bash
heroku config:set MAILTRAP_API_KEY=your_token
```

**Environment file:**
```bash
export MAILTRAP_API_KEY=your_token
```

