# Docker Deployment

1. `cp .env.example .env`
2. Edit `.env`: set `JWT_SECRET_KEY` and `POSTGRES_PASSWORD` (generate secrets with `python -c "import secrets;print(secrets.token_urlsafe(48))"`). Optionally set `LLM_API_KEY` for the AI assistant.
3. `docker compose up --build -d`
4. Open http://localhost:8080 (the web app). The API is reachable at http://localhost:8080/api/ (for agents use `http://localhost:8080/api` as the server address, for example `http://localhost:8080/api/v1/evaluate`).

Useful commands: `docker compose logs -f backend`, `docker compose ps`, `docker compose down` (keeps data), `docker compose down -v` (**deletes the database volume**).

Notes
- Services restart automatically (`restart: unless-stopped`) and have health checks. The database lives in the `falconeye_pgdata` volume.
- The backend is not published directly; it is reached through the nginx container, which is why `TRUST_PROXY` is on.
- This setup serves plain HTTP. For real deployments put a TLS reverse proxy in front of port 8080, set `COOKIE_SECURE=true`, set `CORS_ORIGINS` to your real address and consider `ENABLE_API_DOCS=false`.
- Back up with `docker compose exec db pg_dump -U falconeye falconeye > backup.sql`.
- Run one backend container: the rate limiter keeps its counters in memory.
