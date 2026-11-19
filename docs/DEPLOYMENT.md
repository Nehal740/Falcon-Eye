# Deploying Falcon Eye to your own server and domain

Target: one Ubuntu 22.04/24.04 VPS (2 GB RAM or more), Docker, and a
sub-domain such as `falconeye.yourdomain.com`. HTTPS is automatic (Caddy).

## 0. What you need
- A VPS with root/SSH access (shared cPanel hosting cannot run this).
- DNS access for your domain.
- This repository on GitHub.

## 1. Point the domain at the server
In your DNS panel add an **A record**: name `falconeye`, value = the server's
public IP. Wait a few minutes, then check with `nslookup falconeye.yourdomain.com`.

## 2. Prepare the server (once)
```bash
ssh root@SERVER_IP
git clone https://github.com/YOURNAME/Falcon-Eye.git
cd Falcon-Eye
bash scripts/server-setup.sh
```
(Better security: create a non-root user later and disable password SSH login.)

## 3. Create the production settings
```bash
cp .env.example .env
python3 -c "import secrets;print(secrets.token_urlsafe(48))"   # JWT_SECRET_KEY
python3 -c "import secrets;print(secrets.token_urlsafe(24))"   # POSTGRES_PASSWORD
nano .env
```
Fill in: `JWT_SECRET_KEY`, `POSTGRES_PASSWORD`, `DOMAIN`, `ACME_EMAIL`, and the
`LLM_*` lines if you want AI answers. Do not put quotes around values.

## 4. Start
```bash
docker compose -f docker-compose.prod.yml --env-file .env up --build -d
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs backend --tail 50
```
Open `https://falconeye.yourdomain.com`. Agents call
`https://falconeye.yourdomain.com/api/v1/evaluate`.

## 5. Backups (do this on day one)
```bash
bash scripts/backup.sh                 # test it once
crontab -e                             # then add this line (daily at 03:00):
0 3 * * * cd /root/Falcon-Eye && bash scripts/backup.sh >> backup.log 2>&1
```
Copy backups off the server regularly. Test a restore with `scripts/restore.sh`
on a spare machine before you need it.

## 6. Updating
```bash
cd Falcon-Eye && git pull
docker compose -f docker-compose.prod.yml --env-file .env up --build -d
```
The database upgrades itself at start-up.

## 7. Operating rules
- Run exactly **one** backend container (rate limits are kept in memory).
- Never run `docker compose down -v`: it deletes the database.
- Keep `.env` private. Rotate `JWT_SECRET_KEY` if it ever leaks (everyone is signed out).
- Check `docker compose ... logs backend` after each update.
