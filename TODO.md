
# TODO

- [ ] Codemirror: set right syntax suggestions for SQL and Python.
- [ ] add rewards, gamification, etc.

- [ ] Frontend: List exercises in course detail page: make sure non-staff users can't add new exercises or edit existing ones.
- [ ] Frontend: Display completion status for exercises and courses using Trace.complete.
- [ ] Frontend: Mark trace as complete when user finishes an exercise.
- [ ] Frontend: Disable further editing or submissions for completed traces.
- [ ] Frontend: Show user progress (e.g., progress bar, summary).
- [ ] Frontend: Allow users to view their past attempts (traces).
- [ ] Backend: Add endpoints and logic for annotating GuidanceLog and Trace objects for evaluation purposes.
- [ ] Backend: Add admin and UI for annotating/labeling traces and logs.

# LATER
- [] Frontend: style login page at templates/registration/login.html

Fix this interaction

```
For this first exercise, write an SQL query to list all students from the `students` table

select from student
SQL Error: error: relation "student" does not exist

What do you think might be missing after the SELECT keyword in your query on line 1?
```

## Run code in a sandbox

- jobe?
- https://modal.com/docs/examples/safe_code_execution
- piston? https://github.com/engineer-man/piston?tab=readme-ov-file#License



## Emails

The email went into my spam folder when I tested the "Reset" option setting. How can I avoid that? Here's the message that Jimmy printed.

Be careful with this message.

This message isn't authenticated and the sender can't be verified. Use caution when clicking links, downloading attachments, or replying with personal information.



- Root cause: you sent via Mailgun’s sandbox/login while using From register@steacher.org. SPF/DKIM/DMARC don’t align, so Gmail flags “isn’t authenticated”.

### Fix deliverability: align domain + authenticate
1) Create a Mailgun custom sending domain (recommended a subdomain):
   - Example: mg.steacher.org
   - In Mailgun, copy the exact DNS records it shows and add them at your DNS provider:
     - SPF (TXT) for the domain
     - DKIM (TXT) for the domain
     - Tracking CNAME (optional)
     - MX (optional, for incoming)
   - Wait for Mailgun to verify (can take minutes to hours).

2) Set DMARC on the root domain (steacher.org) to start in monitor mode:
```txt
Host: _dmarc.steacher.org
Type: TXT
Value: v=DMARC1; p=none; rua=mailto:dmarc@steacher.org; adkim=s; aspf=s; pct=100
```
- After a few days, raise policy to p=quarantine (then p=reject) once you see passes.

3) Create SMTP credentials for your new domain in Mailgun:
   - postmaster@mg.steacher.org + its SMTP password.

4) Set your environment to match the sending domain:
```bash
# ~/.bashrc or ~/.bash_profile
export MAILGUN_DOMAIN='mg.steacher.org'
export MAILGUN_SMTP_LOGIN='postmaster@mg.steacher.org'
export MAILGUN_SMTP_PASSWORD='YOUR_SMTP_PASSWORD'
export DEFAULT_FROM_EMAIL='Steacher <no-reply@mg.steacher.org>'
```
Then:
```bash
source ~/.bashrc
```
- This aligns From with the authenticated domain so SPF/DKIM/DMARC pass.

5) Optional (API route, no SMTP creds): use Anymail + API key instead of SMTP. If you do, set:
- EMAIL_BACKEND=anymail.backends.mailgun.EmailBackend
- MAILGUN_API_KEY, MAILGUN_DOMAIN, DEFAULT_FROM_EMAIL, and add ANYMAIL config in settings.

### Content/operational tips
- Use a consistent From: name (e.g., “Steacher”) and real From domain (no generic “@gmail.com”).
- Don’t use URL shorteners; send HTTPS links that match your app’s domain.
- Warm up the domain a bit and enroll in Gmail Postmaster Tools for visibility.

After updating DNS and env, send another reset email; Gmail should show “signed by mg.steacher.org” and stop flagging it as unauthenticated.
