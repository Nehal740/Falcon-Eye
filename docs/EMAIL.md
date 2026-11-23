# Email: welcome, confirmation and password reset

Falcon Eye sends these emails:

| When | Email |
|---|---|
| Someone creates an account | Welcome + "confirm your email" link |
| Someone presses **Forgot password** | A one-time link to choose a new password |
| A password is changed (by the person or by a reset) | A security notice, so a stolen account is noticed |
| Someone presses **Resend email** in the yellow banner | A new confirmation link |

Email is optional. **Without SMTP settings nothing is sent**, sign-up and sign-in still work, and "Forgot password" says email is not set up. For a real deployment you should set it up.

## How it behaves (security)
- Links contain a random one-time token. Only a hash is stored. A reset link works **once** and expires after 60 minutes; a confirmation link after 48 hours. Asking for a new link cancels the older one.
- The token sits after the `#` in the link, so it is never sent to a web server, proxy or log.
- "Forgot password" answers the same way whether or not an account exists, so it cannot be used to find out who is registered. Each address gets at most 3 reset emails an hour.
- A successful reset signs out every device, clears an account lockout, and sends a "password changed" notice.
- Confirming the email is **not required** to use Falcon Eye (so a mail outage never locks anyone out). Unconfirmed users see a banner.
- Emails are sent in the background; a mail failure is logged (type of failure only, never passwords or links) and never breaks sign-up.
- Known limit: session checks use whole seconds, so a session started in the same second as a password reset is not signed out.

## Step 1: choose where mail comes from
You need an SMTP account. Options:

1. **The mailbox from your hosting** (simplest if you already own a domain and hosting). Create `no-reply@yourdomain.com` in the hosting panel and look for "Mail client settings" (SMTP server, port, user, password). Usually `mail.yourdomain.com`, port `587` (`starttls`) or `465` (`ssl`).
2. **A sending service** such as Brevo, Resend, Mailgun or Amazon SES. Most have a free tier. Create an account, add your domain, and copy their SMTP settings.
3. **Gmail** only for quick tests: turn on 2-step verification, create an *App password*, use `smtp.gmail.com`, port `587`, your Gmail address as user. Emails will show your Gmail address as sender. Not for production.

## Step 2: put the settings in `.env`
```
SMTP_HOST=mail.yourdomain.com
SMTP_PORT=587
SMTP_USER=no-reply@yourdomain.com
SMTP_PASSWORD=the-mailbox-password
SMTP_SECURITY=starttls
EMAIL_FROM=Falcon Eye <no-reply@yourdomain.com>
APP_BASE_URL=https://falconeye.yourdomain.com
```
Leave `APP_BASE_URL` empty when testing locally. Restart the backend: `docker compose up -d --force-recreate backend` (or restart uvicorn).

## Step 3: make mail arrive in the inbox, not in spam
In your domain's DNS panel add the records your mail provider tells you to add:
- **SPF** (a `TXT` record) says which servers may send for your domain.
- **DKIM** (a `TXT` or `CNAME` record) signs each email.
- **DMARC** (a `TXT` record on `_dmarc.yourdomain.com`), for example `v=DMARC1; p=none; rua=mailto:you@yourdomain.com`.

Providers show these records on their "domain verification" page. Without them, mail from a new domain often goes to spam. The sender address must belong to the domain you verified.

## Step 4: test
1. Open the app, press **Sign up** with an address you own. Check the inbox (and spam) for the welcome email, click **Confirm my email**.
2. Sign out, press **Forgot password?**, enter the address, click the link, choose a new password, and sign in.
3. If nothing arrives: `docker compose logs backend --tail 30`. `Email not sent: the mail server rejected SMTP_USER/SMTP_PASSWORD` means wrong credentials; `mail server answered 5xx` usually means the sender address is not allowed; `TimeoutError` or `gaierror` means a wrong host or port, or the server blocks outgoing mail ports (some VPS providers block port 25 but allow 587).

## Testing without a mail server
Set `EMAIL_LOG_LINKS=true` (development only; the backend refuses it in production). The email text, including the link, is printed in the backend log instead of being sent.

## Not included yet
Emails for new approval requests, workspace invitations and weekly summaries are not built. The email service (`email_service.py`) is ready for them.
