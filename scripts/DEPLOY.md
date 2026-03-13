# Deploy PortPax API (api.portpax.com)

VPS dedicado Ubuntu. Código en `/home/git/backend`, Gunicorn con systemd, Nginx + Let's Encrypt.

## Requisitos

- SSH: Host `portpax-api` en `~/.ssh/config` (api.portpax.com, root).
- En el servidor: `.env` en `/home/git/backend/.env` (no se sube por rsync; configurar una vez).

## Deploy habitual

Desde el directorio **backend** del repo:

```bash
./scripts/deploy.sh
```

El script hace rsync (excluye `.venv`, `.env`, `.git`), chown a `git`, pip install, migrate, collectstatic y reinicia `portpax-api`.

## Variables en `.env` (producción)

- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`: para Postgres y para `config/local_settings.py`.
- `DJANGO_SECRET_KEY`: opcional; si no está, se usa un fallback (cambiar en producción por uno fuerte, p. ej. `openssl rand -base64 48`).

`local_settings.py` carga `.env` y, si existe `POSTGRES_DB`, activa configuración de producción: Postgres, `DEBUG=False`, `ALLOWED_HOSTS` (api.portpax.com), CORS (itm.portpax.com, localhost).

## Setup una sola vez (ya hecho en este servidor)

1. **Paquetes:** Postgres, Nginx, Certbot, Python3, venv, libpq-dev (ver `setup.sh`).
2. **Postgres:** Copiar `.env` al servidor y ejecutar `scripts/init_db.sh` (crea usuario y DB).
3. **Nginx + SSL:** Config en `scripts/nginx-api.portpax.com.conf`, certbot para api.portpax.com.
4. **Systemd:** `scripts/portpax-api.service` en `/etc/systemd/system/`, `systemctl enable --now portpax-api`.

## CORS

El frontend (itm.portpax.com) está permitido en `CORS_ALLOWED_ORIGINS` vía `local_settings.py`. Para más orígenes: variable de entorno `CORS_ORIGINS` (lista separada por comas) en `.env`.
