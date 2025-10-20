# Fixing time zone difference on server
_Exported on 9/18/2025 at 15:59:31 GMT+2 from Cursor (1.6.27)_

---

**User**

somehow my remote cloud hoster server is 2h ahead of my local time

e.g. 

Thu Sep 18 15:49:46 CEST 2025 in my local timezone
but
Thu Sep 18 01:49:44 PM UTC 2025
when i `date` on my remote server

---

**Cursor**

Your server is set to UTC, while your local machine is on CEST (UTC+2). That’s why `date` differs by 2 hours. You can either keep the server on UTC (recommended for servers) or switch it to your local timezone.

### Check current timezone
```bash
timedatectl status
date +"%Y-%m-%d %H:%M:%S %Z %z"
```

### Change server timezone (systemd hosts, e.g., Ubuntu/Debian/CentOS)
```bash
sudo timedatectl list-timezones | grep Europe/
sudo timedatectl set-timezone Europe/Zurich    # or Europe/Berlin, etc.
timedatectl status
```

### If using Docker/Compose
- Set TZ for each service (and ensure image has tzdata if needed):
```yaml
services:
  web:
    environment:
      - TZ=Europe/Zurich
```
- Debian/Ubuntu-based image needs tzdata:
```Dockerfile
RUN apt-get update && apt-get install -y tzdata && rm -rf /var/lib/apt/lists/*
ENV TZ=Europe/Zurich
```
- Alpine-based:
```Dockerfile
RUN apk add --no-cache tzdata
ENV TZ=Europe/Zurich
```

### Django tip
- Keep `USE_TZ = True` and set your preferred display zone:
```python
USE_TZ = True
TIME_ZONE = "Europe/Zurich"  # for localized display; data stored in UTC
```

Optional DB check (PostgreSQL):
```sql
SHOW TIME ZONE;
-- per-session:
SET TIME ZONE 'Europe/Zurich';
```

```shellscript
timedatectl status
date +"%Y-%m-%d %H:%M:%S %Z %z"
```

```shellscript
sudo timedatectl list-timezones | grep Europe/
sudo timedatectl set-timezone Europe/Zurich    # or Europe/Berlin, etc.
timedatectl status
```

```yaml
services:
  web:
    environment:
      - TZ=Europe/Zurich
```

```dockerfile
RUN apt-get update && apt-get install -y tzdata && rm -rf /var/lib/apt/lists/*
ENV TZ=Europe/Zurich
```

```dockerfile
RUN apk add --no-cache tzdata
ENV TZ=Europe/Zurich
```

```python
USE_TZ = True
TIME_ZONE = "Europe/Zurich"  # for localized display; data stored in UTC
```

```sql
SHOW TIME ZONE;
-- per-session:
SET TIME ZONE 'Europe/Zurich';
```

---

**User**

i'm on docker compose, see @docker-compose.yml . i'll keep the server on UTC then

---

**Cursor**

Great—keeping the host and containers on UTC is a solid choice.

- Set UTC explicitly in Docker Compose (optional but makes intent clear):
```yaml
services:
  web:
    environment:
      - TZ=UTC
  db:
    environment:
      - TZ=UTC
  proxy:
    environment:
      - TZ=UTC
  scala_interpreter:
    environment:
      - TZ=UTC
  certbot:
    environment:
      - TZ=UTC
  newrelic_infra:
    environment:
      - TZ=UTC
```
Most images already run in UTC; this just avoids surprises. You don’t need tzdata for UTC.

- Django settings (recommended):
```python
USE_TZ = True
TIME_ZONE = "UTC"
```

- PostgreSQL sanity check:
```bash
docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SHOW TIME ZONE;"
```

- Verify container clocks:
```bash
docker compose exec web date +"%F %T %Z %z"
```

- Show local time to users on the frontend (keep data in UTC, convert at render):
```ts
new Date(isoString).toLocaleString(undefined, { timeZoneName: 'short' })
```

That gives you consistent storage/logs in UTC while users see times in their local zone.

```yaml
services:
  web:
    environment:
      - TZ=UTC
  db:
    environment:
      - TZ=UTC
  proxy:
    environment:
      - TZ=UTC
  scala_interpreter:
    environment:
      - TZ=UTC
  certbot:
    environment:
      - TZ=UTC
  newrelic_infra:
    environment:
      - TZ=UTC
```

```python
USE_TZ = True
TIME_ZONE = "UTC"
```

```shellscript
docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SHOW TIME ZONE;"
```

```shellscript
docker compose exec web date +"%F %T %Z %z"
```

```typescript
new Date(isoString).toLocaleString(undefined, { timeZoneName: 'short' })
```

