from app import create_app

app = create_app()

if __name__ == "__main__":
    # Local HTTPS: install pyOpenSSL, then run `python run.py`.
    # Production should use a real TLS certificate through a reverse proxy or platform HTTPS.
    app.run(host="0.0.0.0", port=8443, ssl_context="adhoc", debug=True)
