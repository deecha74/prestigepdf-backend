# PrestigePDF Production Deployment Cheatsheet

Quick step-by-step guide for setting up Cloudflare, Nginx, Systemd, and connecting the frontend for production deployment.

---

## Step 1: Cloudflare Setup (DNS & SSL)

1. **Add A Record for Backend**:
   - **Type**: `A`
   - **Name**: `api` *(do NOT type `.domain.com` after it)*
   - **IPv4 Address**: Your Linux VPS IP (e.g. `169.58.188.234`)
   - **Proxy Status**: **Proxied (Orange Cloud 🧡)**

2. **Remove Wildcard Collision** *(If present)*:
   - Delete any `*.domain.com` CNAME record that redirects all subdomains to another portfolio/website.

3. **Set SSL/TLS Encryption Mode**:
   - Go to **Cloudflare Dashboard** → **SSL/TLS** → **Overview**
   - Set encryption mode to **`Flexible`** (or **`Full`** if Nginx has SSL certificates configured).

---

## Step 2: FastAPI Service Setup (Systemd on VPS)

1. **Create systemd unit file**: `/etc/systemd/system/prestigepdf-backend.service`

```ini
[Unit]
Description=PrestigePDF FastAPI Backend Service
After=network.target

[Service]
User=root
WorkingDirectory=/var/www/prestigepdf-backend
ExecStart=/var/www/prestigepdf-backend/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --workers 4
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

2. **Enable and start the service**:
```bash
sudo systemctl daemon-reload
sudo systemctl enable prestigepdf-backend
sudo systemctl start prestigepdf-backend
sudo systemctl status prestigepdf-backend
```

---

## Step 3: Nginx Reverse Proxy Setup

1. **Create Nginx site config**: `/etc/nginx/sites-available/api.prestigepdf.com`

```nginx
server {
    listen 80;
    server_name api.prestigepdf.com;

    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

2. **Enable site and reload Nginx**:
```bash
sudo ln -s /etc/nginx/sites-available/api.prestigepdf.com /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## Step 4: Google AdSense Consent Management (CMP)

To comply with Google AdSense requirements for EEA, UK, and Switzerland users:
1. Log into **Google AdSense** → **Privacy & messaging** → **GDPR**.
2. Select **Google's CMP (Consent Management Platform)**.
3. Choose **Two choices (Consent and Manage options)** for maximum compliance & user retention.
4. Publish the consent message — Google automatically serves the consent modal via your site's AdSense script (`ca-pub-...`).

---

## Step 5: Fixing 404 Errors on Direct Page Load / Refresh (SPA Routing)

### Option A: Apache / cPanel / Shared Hosting (.htaccess)
Create `.htaccess` in your `public/` directory (or web root `/public_html/.htaccess`):

```apache
<IfModule mod_rewrite.c>
  RewriteEngine On
  RewriteBase /
  RewriteCond %{REQUEST_FILENAME} -f [OR]
  RewriteCond %{REQUEST_FILENAME} -d
  RewriteRule ^ - [L]
  RewriteRule ^ index.html [L]
</IfModule>
```

### Option B: Nginx VPS Frontend Config
In your Nginx site block for `prestigepdf.com`:

```nginx
location / {
    root /var/www/prestigepdf-frontend/dist;
    try_files $uri $uri/ /index.html;
}
```
