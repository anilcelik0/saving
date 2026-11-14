# Copy to local_config.py (git-ignored) before `flet build apk` for a real phone.
# The phone and the computer must be on the same Wi-Fi; use the computer's LAN IP (ipconfig -> IPv4 Address)
# nginx listens on port 80 (NGINX_PORT in .env; add ":<port>" to the URL if you change it). Also add that IP to DJANGO_ALLOWED_HOSTS in .env.
API_URL = "http://192.168.1.20/api/v1"
