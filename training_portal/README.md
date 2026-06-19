# Training Simulator Portal

A secure starter web app for uploading interactive training simulators, selling client access, launching training content, supporting a client forum, and issuing completion certificates.

## Built-in features

- Client signup and signin
- Default admin bootstrap login: `ADMIN` / `admin1`
- Admin settings page to replace the default username and password
- Admin-controlled access: pending, active, suspended
- Upload/remove/publish/hide training simulators
- Supports `.html` simulator files and `.zip` simulator bundles containing a top-level `index.html`
- Client dashboard with simulator launcher
- Forum for active clients
- Completion tracking
- Printable certificate with client name, training title, completion date, and unique certificate ID
- Encrypted PII fields for name and email using Fernet
- HMAC email lookup so email can be checked without storing plaintext search keys
- Password hashing with Werkzeug PBKDF2
- CSRF protection on POST requests
- Secure cookie settings
- Audit log for admin review
- Local HTTPS dev launch with `ssl_context="adhoc"`

## Important security approach

Do **not** store credit card numbers in this app. Use Stripe Checkout, a Stripe Payment Link, PayPal, Square, or another payment provider. This starter stores only a client's access status.

For production PII security:

1. Use a managed database with encryption at rest.
2. Store `.env` secrets in your deployment platform's secret manager, not inside GitHub.
3. Keep `APP_FERNET_KEY`, `APP_HMAC_KEY`, and `SECRET_KEY` backed up securely. If you lose the Fernet key, encrypted names/emails cannot be recovered.
4. Keep `SESSION_COOKIE_SECURE=true` and serve only over HTTPS.
5. Put uploaded simulator files behind authenticated routes only, which this app does.
6. Change `ADMIN/admin1` immediately before sharing the site.

## Run locally

```bash
cd training_portal
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env  # Windows
# or: cp .env.example .env
python run.py
```

Open:

```text
https://localhost:8443
```

Your browser will warn you about a self-signed local certificate. That is expected for local development.

## Admin login

Initial admin login:

```text
Username: ADMIN
Password: admin1
```

After first login, go to **Admin → Settings** and replace the username and password.

## Uploading training simulators

From **Admin → Upload training**:

- Upload a single `.html` file, or
- Upload a `.zip` file with `index.html` at the top level.

Example zip structure:

```text
my-simulator.zip
├── index.html
├── styles.css
├── script.js
└── assets/
    └── image.png
```

## Paid access workflow

1. Create a Stripe or PayPal payment link.
2. Paste that link into `.env` as `PAYMENT_LINK`.
3. Client signs up.
4. Client clicks payment link.
5. Admin activates client in **Admin → Clients** after payment is confirmed.

Production upgrade: add a Stripe webhook route that automatically changes `subscription_status` to `active` after a successful checkout session.

## Production HTTPS deployment

Use one of these options:

### Option A: Platform HTTPS

Deploy to Render, Railway, Fly.io, DigitalOcean App Platform, Azure App Service, AWS Elastic Beanstalk, or similar. Most platforms provide HTTPS automatically.

Recommended production command:

```bash
gunicorn 'wsgi:app' --bind 0.0.0.0:$PORT --workers 3
```

### Option B: VPS with Nginx and Let's Encrypt

Run the app behind Nginx and install a certificate with Certbot.

Example Nginx reverse proxy:

```nginx
server {
    server_name yourdomain.com www.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

Run Gunicorn locally on the server:

```bash
gunicorn 'wsgi:app' --bind 127.0.0.1:8000 --workers 3
```

Then use Certbot:

```bash
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

## Suggested future upgrades

- Stripe webhook for automatic activation
- Password reset email flow
- Email verification
- Two-factor authentication for admin
- Progress tracking inside each simulator
- Badges and leaderboard
- Announcements page
- Training search/filter by category and level
- Admin analytics charts
- Course bundles and skill paths
- Forum moderation tools
- SCORM/xAPI support for enterprise training packages
