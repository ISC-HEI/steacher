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

