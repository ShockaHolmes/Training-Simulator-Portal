# Security checklist before going live

- [ ] Replace the default `ADMIN/admin1` login.
- [ ] Set strong production values for `SECRET_KEY`, `APP_FERNET_KEY`, and `APP_HMAC_KEY`.
- [ ] Confirm `.env` is not committed to GitHub.
- [ ] Use HTTPS only.
- [ ] Use a production database with encryption at rest.
- [ ] Use Stripe/PayPal/Square for payments; do not store card numbers.
- [ ] Keep server packages patched.
- [ ] Back up the database and encryption keys securely.
- [ ] Limit admin access to trusted devices/users.
- [ ] Review audit logs regularly.
- [ ] Test simulator ZIP uploads to ensure every bundle contains only safe expected files.
