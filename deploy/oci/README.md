# ORA backend on Oracle Cloud Always Free

This deployment keeps the existing Vercel frontend and runs the FastAPI backend as a persistent Docker service with a durable Docker volume. Oracle Cloud Always Free is the recommended zero-monthly-cost target when an Always Free VM is available in the account's home region.

## 1. Create the VM

Create an Ubuntu VM using the OCI Ampere A1 Flex Always Free shape. Allocate 2 OCPUs and 12 GB RAM if available. Use the VM's public IPv4 address and create ingress rules for TCP ports 80 and 443. Keep SSH on port 22 restricted to your own IP where possible.

OCI may report an out-of-capacity error for Always Free shapes. If that happens, try another availability domain in the home region or retry later. Do not create paid resources unless you intentionally choose to do so.

## 2. Install Docker and clone ORA

On the VM, install Docker using the official Docker documentation for Ubuntu, then enable the Docker service. Clone the repository and enter it:

```bash
sudo mkdir -p /opt/ora
sudo chown "$USER":"$USER" /opt/ora
git clone https://github.com/elishaoigara/ORA.git /opt/ora
cd /opt/ora
```

## 3. Configure secrets

Copy the production template and edit it on the VM. Do not commit this file:

```bash
cp .env.production.example .env.production
chmod 600 .env.production
nano .env.production
```

Set `API_DOMAIN` to the backend DNS name, such as `api.example.com`. Set `FRONTEND_URL` and `CORS_ORIGINS` to the exact Vercel production URL. Generate separate random values for `ORA_API_TOKEN` and `ORA_INTERNAL_TOKEN`. For example:

```bash
openssl rand -hex 32
```

Set the Groq, Telegram, Google, WhatsApp, and other connector credentials that ORA actually uses. Do not paste credentials into GitHub, screenshots, issue trackers, or chat logs.

## 4. Start the backend

For a temporary HTTP-only test using the VM IP:

```bash
docker compose -f docker-compose.prod.yml up -d --build ora-backend
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f --tail=100 ora-backend
```

For production HTTPS, create a DNS A record pointing `api.example.com` to the VM's public IP, confirm DNS resolves, then start Caddy:

```bash
docker compose -f docker-compose.prod.yml --profile https up -d --build
docker compose -f docker-compose.prod.yml ps
```

Caddy obtains and renews the TLS certificate automatically for `API_DOMAIN`. The ORA data volume is named `ora-data` and survives container recreation.

## 5. Connect Vercel

In the Vercel project settings, add these variables for the Production environment and redeploy the frontend:

```text
VITE_API_URL=https://api.example.com
VITE_ORA_API_TOKEN=<same value as backend ORA_API_TOKEN>
```

The backend must contain:

```text
FRONTEND_URL=https://your-production-vercel-domain
CORS_ORIGINS=https://your-production-vercel-domain
```

Do not include a trailing slash in `VITE_API_URL` or in the CORS origin.

## 6. Configure Google OAuth

Update the Google OAuth application's authorized redirect URI to:

```text
https://api.example.com/api/auth/google/callback
```

Set the same value in `.env.production` as `GOOGLE_REDIRECT_URI`, then restart the backend:

```bash
docker compose -f docker-compose.prod.yml restart ora-backend
```

## 7. Verify

```bash
curl -fsS https://api.example.com/api/health
curl -i https://api.example.com/api/status
curl -i -H "X-ORA-Token: $ORA_API_TOKEN" https://api.example.com/api/status
```

The health endpoint should return HTTP 200 without authentication. The protected status endpoint should reject a request without `X-ORA-Token` and succeed with the configured token.

## 8. Back up ORA data

The Docker volume is persistent, but persistent does not mean backed up. Create a scheduled archive of the volume to a separate location. At minimum, stop the service briefly, archive `/var/lib/docker/volumes/ora-data/_data`, and copy the encrypted archive off the VM. Test restoring a backup before trusting it.

## 9. Updating ORA

```bash
cd /opt/ora
git pull --ff-only origin main
docker compose -f docker-compose.prod.yml --profile https up -d --build
```

Check the deployment after each update:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --tail=100 ora-backend
```

If a deployment fails, keep the previous image available and inspect logs before deleting volumes. Never run `docker compose down -v` on production because it deletes the ORA data volume.
