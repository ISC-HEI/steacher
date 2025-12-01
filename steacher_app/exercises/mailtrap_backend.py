# Custom Django email backend using Mailtrap's HTTP API for faster email delivery
import logging
from typing import List

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.message import EmailMessage, EmailMultiAlternatives

try:
    import mailtrap as mt
    MAILTRAP_AVAILABLE = True
except ImportError:
    MAILTRAP_AVAILABLE = False

logger = logging.getLogger(__name__)


class MailtrapBackend(BaseEmailBackend):
    """
    Email backend that sends emails via Mailtrap's HTTP API.
    
    Much faster than SMTP as it uses REST API instead of SMTP protocol.
    Requires MAILTRAP_API_KEY in settings.
    """
    
    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        
        if not MAILTRAP_AVAILABLE:
            raise ImportError(
                "mailtrap package is required for MailtrapBackend. "
                "Install it with: pip install mailtrap"
            )
        
        api_key = getattr(settings, 'MAILTRAP_API_KEY', None)
        if not api_key:
            raise ValueError(
                "MAILTRAP_API_KEY must be set in settings to use MailtrapBackend"
            )
        
        self.client = mt.MailtrapClient(token=api_key)
    
    def send_messages(self, email_messages: List[EmailMessage]) -> int:
        """
        Send one or more EmailMessage objects and return the number of sent messages.
        """
        if not email_messages:
            return 0
        if len(email_messages) > 20:
            raise ValueError("Too many emails to send at once. Max is 20.")
        
        num_sent = 0
        for message in email_messages:
            try:
                self._send_message(message)
                num_sent += 1
            except Exception as e:
                logger.exception(f"Failed to send email via Mailtrap: {e}")
                if not self.fail_silently:
                    raise
        
        return num_sent
    
    def _send_message(self, message: EmailMessage):
        """Convert Django EmailMessage to Mailtrap Mail and send it."""
        
        # Extract sender
        sender_email = message.from_email
        sender_name = None
        if '<' in sender_email:
            # Handle "Name <email@example.com>" format
            parts = sender_email.split('<')
            sender_name = parts[0].strip().strip('"')
            sender_email = parts[1].strip('>')
        
        sender = mt.Address(email=sender_email, name=sender_name)
        
        # Extract recipients
        to_addresses = [self._parse_address(addr) for addr in message.to]
        cc_addresses = [self._parse_address(addr) for addr in message.cc] if message.cc else None
        bcc_addresses = [self._parse_address(addr) for addr in message.bcc] if message.bcc else None
        
        # Get body content
        text_content = message.body
        html_content = None
        
        # Handle HTML content from EmailMultiAlternatives
        if isinstance(message, EmailMultiAlternatives):
            for content, mimetype in message.alternatives:
                if mimetype == 'text/html':
                    html_content = content
                    break
        
        # Handle attachments
        attachments = []
        if message.attachments:
            for attachment in message.attachments:
                attachments.append(self._process_attachment(attachment))
        
        # Extract custom headers
        custom_headers = {}
        if message.extra_headers:
            custom_headers = message.extra_headers
        
        # Build Mailtrap Mail object
        mail_kwargs = {
            'sender': sender,
            'to': to_addresses,
            'subject': message.subject,
            'text': text_content,
        }
        
        if html_content:
            mail_kwargs['html'] = html_content
        
        if cc_addresses:
            mail_kwargs['cc'] = cc_addresses
        
        if bcc_addresses:
            mail_kwargs['bcc'] = bcc_addresses
        
        if attachments:
            mail_kwargs['attachments'] = attachments
        
        if custom_headers:
            mail_kwargs['headers'] = custom_headers
        
        # Add category if specified in headers
        if 'X-Mailtrap-Category' in custom_headers:
            mail_kwargs['category'] = custom_headers.pop('X-Mailtrap-Category')
        
        mail = mt.Mail(**mail_kwargs)
        
        # Send the email
        response = self.client.send(mail)
        
        logger.debug(f"Mailtrap API response: {response}")
        
        return response
    
    def _parse_address(self, address: str) -> mt.Address:
        """Parse email address string into Mailtrap Address object."""
        if '<' in address:
            # Handle "Name <email@example.com>" format
            parts = address.split('<')
            name = parts[0].strip().strip('"')
            email = parts[1].strip('>')
            return mt.Address(email=email, name=name)
        else:
            # Plain email address
            return mt.Address(email=address.strip())
    
    def _process_attachment(self, attachment) -> mt.Attachment:
        """Convert Django attachment to Mailtrap Attachment object."""
        import base64
        
        if isinstance(attachment, tuple):
            # Attachment is (filename, content, mimetype)
            filename, content, mimetype = attachment
        else:
            # MIMEBase object or similar
            filename = attachment.get_filename()
            content = attachment.get_payload(decode=True)
            mimetype = attachment.get_content_type()
        
        # Ensure content is bytes
        if isinstance(content, str):
            content = content.encode('utf-8')
        
        # Base64 encode the content
        encoded_content = base64.b64encode(content)
        
        return mt.Attachment(
            content=encoded_content,
            filename=filename,
            mimetype=mimetype,
            disposition=mt.Disposition.ATTACHMENT,
        )

