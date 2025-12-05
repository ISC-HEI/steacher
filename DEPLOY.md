# Redeploy on prod

```bash
ssh into vm

# backup, at the second près
TS=$(date +%F_%H-%M-%S)
docker compose exec -T db pg_dump -U steacher_admin steacher_prod > ~/dev/manual_backup_db/db_$TS.sql
wormhole send ~/dev/manual_backup_db/db_$TS.sql

# backup app, OPTIONAL
zip -r        ~/dev/manual_backup_db/app_$TS.zip .
wormhole send ~/dev/manual_backup_db/app_$TS.zip

# 1) Get latest code
git pull

# 2) toggle maintenance mode (from project root)
touch nginx/maintenance/maintenance_on
docker compose exec -T proxy nginx -s reload # zero-downtime reload so Nginx picks up the flag


# 3) Build the web image (so collectstatic runs against the new code)
docker compose build web

# 4) Collect static into STATIC_ROOT and write manifest
docker compose run --rm --no-deps --entrypoint "" web python manage.py collectstatic --noinput 
# optionally --clear 

# 5) Recreate/start the app with the new image
docker compose up -d --no-deps web

# 6) Apply DB migrations if models changed
docker compose exec web python manage.py migrate

# 7) somehow needed
docker compose restart web proxy

# 8) remove maintenance mode and reload proxy
rm nginx/maintenance/maintenance_on
docker compose exec -T proxy nginx -s reload



# If Website down (Nginx 502), there might be a docker-compose cache issue. In that case, try:
docker compose down
docker compose up -d




# Only restart other services when they change:

# Nginx config or certs changed:
docker compose up -d --no-deps proxy
# or?
docker compose  up -d --build --no-deps proxy

# Scala interpreter code changed:
docker compose  up -d --build --no-deps scala_interpreter

# Post-checks:
docker compose ps
docker compose logs -n 100 web | cat
docker compose logs -n 100 proxy | cat
```

Start local django

```bash
DJANGO_DEBUG=True uvicorn exam_project.asgi:application --host 127.0.0.1 --port 8000 --reload

DJANGO_DEBUG=True uvicorn exam_project.asgi:application --host 127.0.0.1 --port 8000 --reload --reload-dir exercises --reload-dir templates --reload-dir frontend
```

------


# VM Installation in Infomaniak's OpenStack

## Create instance

Horizon (openstack)

1. create keypair, copy/paste from my local key from `cat ~/.ssh/id_rsa.pub`
2. launch instance, select Ubuntu 24LTS, 2cpu 4gb ram, 20gb disk, network ivp4-something


---

1 additional security update can be applied with ESM Apps.
Learn more about enabling ESM Apps service at https://ubuntu.com/esm



---

## Install Docker (official repo)

1. **Update and install prerequisites**

   ```bash
   sudo apt update
   sudo apt install -y ca-certificates curl gnupg
   ```

2. **Add Docker’s official GPG key**

   ```bash
   sudo install -m 0755 -d /etc/apt/keyrings
   curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
   sudo chmod a+r /etc/apt/keyrings/docker.gpg
   ```

3. **Set up Docker’s apt repository**

   ```bash
   echo \
     "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
     $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
     sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
   ```

4. **Install Docker Engine and CLI**

   ```bash
   sudo apt update
   sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
   ```

---

### ⚙️ Enable and start Docker automatically

```bash
sudo systemctl enable docker
sudo systemctl start docker
```

Check status:

```bash
systemctl status docker
```

---

### ▶️ Install Docker Compose (plugin form)

Since you installed `docker-compose-plugin`, you now use:

```bash
docker compose version
```

(note: **space**, not a dash → no more `docker-compose`).

---

### 🙌 Post-install (optional but recommended)

* Run Docker as non-root user:

  ```bash
  sudo usermod -aG docker $USER
  newgrp docker
  ```

  Then you can do `docker ps` without `sudo`.

---

✅ After this, you have:

* **Docker Engine** (daemon + CLI).
* **Docker Compose plugin** (`docker compose` command).
* It auto-starts on reboot.

---





## Add Rules to Your Security Group

You need to do this in your OpenStack Horizon dashboard (the web interface where you created the instance).

1.  **Log in to Horizon (OpenStack dashboard).**

2.  **Navigate to Security Groups:**
    *   On the left-hand menu, go to **Network** -> **Security Groups**.

3.  **Find and Manage Rules for Your Instance:**
    *   You will see a list of security groups. Find the one that is associated with your VM (it's often named `default` if you didn't create a new one).
    *   Click the **Manage Rules** button for that group.

4.  **Add a Rule for HTTP (Port 80):**
    *   Click the **Add Rule** button.
    *   In the form that appears, use these settings:
        *   **Rule:** `Custom TCP Rule`
        *   **Direction:** `Ingress` (this means incoming traffic)
        *   **Open Port:** `Port`
        *   **Port:** `80`
        *   **Remote:** `CIDR`
        *   **CIDR:** `0.0.0.0/0` (this means "allow traffic from any IP address")
    *   Click **Add**.

5.  **Add a Rule for HTTPS (Port 443):**
    *   Click **Add Rule** again.
    *   Use the same settings as above, but change the port:
        *   **Rule:** `Custom TCP Rule`
        *   **Direction:** `Ingress`
        *   **Open Port:** `Port`
        *   **Port:** `443`
        *   **Remote:** `CIDR`
        *   **CIDR:** `0.0.0.0/0`
    *   Click **Add**.

You should now have two new rules in your security group list. The changes are applied almost instantly.

**Now, try accessing `http://37.156.44.113` in your browser again.** It should now connect to your Nginx proxy and show you your Django application.










# setting the DNS


## 1️⃣ Decide what you want to point

For your LMS, you probably want at least:

* `steacher.org` → main site (Django app behind your proxy)
* `www.steacher.org` → optionally redirect to main site

---

## 2️⃣ Access Infomaniak DNS Management

1. Go to **Infomaniak Admin Panel → Domains → steacher.org → DNS Settings**.
2. You’ll see your current records (A, AAAA, CNAME, etc.).

---

## 3️⃣ Add an **A record**

* **Type:** A
* **Host/Name:** leave empty for root domain (`steacher.org`)
* **Value / Points to:** your **public IPv4** of the OpenStack instance (from Horizon, e.g., `37.156.44.128`)
* **TTL:** default is fine (3600s or 1h)

Optional:

* Add **CNAME** for `www`:

  * **Host/Name:** `www`
  * **Type:** CNAME
  * **Value / Points to:** `steacher.org`

---

## 4️⃣ Add AAAA record (IPv6, optional)

* If you want IPv6 support:

  * **Type:** AAAA
  * **Host/Name:** empty or `www`
  * **Value:** IPv6 of your OpenStack instance (eg `2001:1600:16:10::5bb`)

---

## 5️⃣ Wait for propagation

* DNS changes can take a few minutes to 1 hour.
* Test with:

  ```bash
  ping steacher.org
  ping www.steacher.org
  ```

  or use online tools like **[https://dnschecker.org](https://dnschecker.org)**

---

## 6️⃣ Configure your proxy for the domain

* In nginx or Traefik, make sure the **host matches** `steacher.org` and `www.steacher.org`.
* Enable SSL/Let’s Encrypt for HTTPS. Traefik can do this automatically if it sees the domain pointing to your instance.




----

# Let's Encrypt SSL certificate

We can use a script to automate the initial setup. I've just updated your `docker-compose.yml` to use a local directory (`./certbot_data`) to store the certificates, which is necessary for the script to work.

Now, I will create a script called `init-letsencrypt.sh` that will:
1.  Create a temporary dummy certificate to allow Nginx to start.
2.  Start all the services.
3.  Request a real certificate from Let's Encrypt.
4.  Reload Nginx to use the new certificate.

This script will only need to be run once. After that, we'll set up automatic renewals.

Here is how to proceed:

1.  **Make the script executable:**
    Open a terminal in the project root and run:
    ```bash
    chmod +x init-letsencrypt.sh
    ```

2.  **Run the script:**
    This will perform all the necessary steps to get your first certificate.
    ```bash
    ./init-letsencrypt.sh
    ```
    Follow any on-screen prompts. After the script finishes, `https://steacher.org` will be live.

### Automatic Renewal

Let's Encrypt certificates expire every 90 days. To avoid having to renew them manually, you can set up a cron job on your server to run the renewal command automatically.

**Prerequisites:**
- The certbot service in `docker-compose.yml` must have a `/tmp` tmpfs mount (required for certbot to create temporary files in read-only container)
- The `./certbot_data/etc` directory must be writable by root (certbot runs as root inside container)

**Fix permissions if needed:**
```bash
cd ~/dev/steacher_app
sudo chown -R root:root certbot_data/etc
sudo chmod -R 755 certbot_data/etc
```

**Manual renewal (for testing):**
```bash
cd ~/dev/steacher_app
docker compose run --rm certbot renew
docker compose restart proxy
```

**Set up automatic renewal:**

1.  **Open your crontab editor:**
    ```bash
    crontab -e
    ```

2.  **Add the following line:**
    This will run the renewal command every day at 3:30 AM. Certbot will only renew the certificate if it's close to expiration.

    ```
    30 3 * * * cd /home/ubuntu/dev/steacher_app && /usr/bin/docker compose run --rm certbot renew --quiet && /usr/bin/docker compose restart proxy >> /home/ubuntu/certbot-renew.log 2>&1
    ```

    **Important:**
    *   Replace `/home/ubuntu/dev/steacher_app` with the absolute path to your project directory (where `docker-compose.yml` is located).
    *   Note: Use `docker compose` (with space), not `docker-compose` (with dash) - this is the Docker Compose plugin syntax.

**Check certificate expiry:**
```bash
docker compose run --rm certbot certificates
```

This setup automates both the initial certificate acquisition and the renewal process, making it much easier to manage HTTPS for your site.

------------

# refresh nginx

    docker compose stop proxy
    docker compose rm -f proxy
    docker compose up -d --no-deps proxy
    docker compose exec proxy nginx -t | cat
    docker compose exec proxy sh -lc "grep -n 'mjs' /etc/nginx/nginx.conf | cat"
    curl -I -k https://steacher.org/static/dompurify/dist/purify.es.mjs | grep -i content-type





----------------

# Backups



* **`pg_dump` → fully automatable** (cron job, runs inside your VM).
* **OpenStack volume snapshots → not automatable directly from Horizon**, but you *can* script it with the **OpenStack CLI** or API if you want (I’ll explain).

---

# 1️⃣ Automating `pg_dump` (inside your VM)

Create a folder for backups:

```bash
sudo mkdir -p /var/backups/postgres
sudo chown $USER:$USER /var/backups/postgres
```

Test a manual dump (replace values):

```bash
docker compose exec -T db pg_dump -U steacher_admin steacher_prod > /var/backups/postgres/db_$(date +%F).sql
```

👉 If that works, add a **cron job** for daily dumps:

```bash
crontab -e
```

Add:

```
0 2 * * * docker compose exec -T db pg_dump -U lms_user lms_db > /var/backups/postgres/db_$(date +\%F).sql
```

This runs every night at **2:00 AM**, creating a new `.sql` dump.




# Volume Snapshots in OpenStack

* From Horizon: you can click **Create Backup** for your volume → manual snapshots only.
* Automation: yes, but only if you install the **OpenStack CLI** on your VM (or locally).

Example (with CLI configured):

```bash
openstack volume backup create --name db-backup-$(date +%F) your-volume-id
```

👉 This can also be put in a cron job if you really want automatic snapshots.
But in many setups, people trigger snapshots **weekly or before upgrades** (semi-manual, as a second safety net).

---

# ✅ Recommended combo for you

* **Nightly `pg_dump`** → clean, consistent DB backups.
* **Weekly tar of media volume** → covers student uploads.
* **Monthly OpenStack volume snapshot** → full “bare-metal” copy for disaster recovery.

This way, you get both **application-level consistency** and **infrastructure-level safety**.

---

Do you want me to write you a **ready-to-use cron backup plan** (with all commands and schedules), so you can just drop it into your server?


# Emails

https://mailtrap.io/blog/django-send-email/



# Redis for Django Channels

Redis is used as the channel layer backend for Django Channels to enable WebSocket support and async communication.

Configuration:
- **Connection URL**: `redis://redis:6379/0` (hardcoded in Django settings)
- **Memory limit**: 512MB with LRU eviction policy
- **Persistence**: AOF (append-only file) enabled for data durability
- **Data volume**: `redis_data` for persistent storage

Health checks and monitoring:
```bash
# Check Redis health
docker compose exec redis redis-cli ping

# Monitor Redis info
docker compose exec redis redis-cli info

# Check memory usage
docker compose exec redis redis-cli info memory
```

Redis runs on the default port 6379 and is isolated on the backend network alongside the database and web services. No additional environment configuration needed.

Starting Redis (if needed separately):
```bash
docker compose up -d redis
```
Note: Redis starts automatically when starting the web service due to the `depends_on` configuration.

**Local Development Redis**:

For local Django development (when not running Django in Docker), start a separate Redis container:

```bash
# Start Redis for local development
docker run -d --name redis-dev -p 127.0.0.1:6379:6379 redis:7-alpine

# Stop and remove when done
docker stop redis-dev && docker rm redis-dev

# Or use with auto-removal
docker run --rm -d --name redis-dev -p 127.0.0.1:6379:6379 redis:7-alpine
```

**Configuration**:
- **Production Redis**: Isolated on backend network, no external access, full security hardening
- **Local development**: Separate Redis container with host port access
- **Django in Docker**: Connects via `redis://redis:6379/0`
- **Django locally**: Connects via `redis://127.0.0.1:6379/0`

# Gunicorn WSGI + gthread (production)

Gunicorn is configured to run Django via WSGI with `gthread` workers for high concurrency during long LLM calls. See Dockerfile for more details.

Environment knobs (set in compose or `.env.production`):

```bash
WEB_CONCURRENCY=5   # number of Gunicorn worker processes
WEB_THREADS=20      # threads per worker (gthread)
WEB_TIMEOUT=180     # seconds; match Nginx proxy timeouts
```

Sizing notes (4 vCPU / 8 GB RAM VM):
- Start with `WEB_CONCURRENCY=5`, `WEB_THREADS=20` → ~100 in-flight requests.
- If queueing under load, try `WEB_CONCURRENCY=6`. Monitor RSS and CPU.
- Memory budget: ~200–250 MB per worker plus app baseline. Still well within 8 GB.

Long running LLM calls have longer Nginx timeouts (set in `nginx/nginx.conf`):


# Redeploy

# 1) SSH and go to project
ssh
git pull

1.2) Start/refresh the proxy

    docker compose up -d proxy
    docker compose ps

    # Validate nginx config and check logs
    docker compose exec proxy nginx -t | cat
    docker compose logs -n 200 proxy | cat

# 2) Rebuild and restart only app containers (rebuilds if code/deps changed)

    docker compose  up -d --build web 
    # add scala_interpreter at end if needed

# 3) Run migrations (use exec or override entrypoint)
    docker compose exec web python manage.py migrate
# or if web isn't up yet:
docker compose run --rm --entrypoint "" web python manage.py migrate

check migration stat:
    docker compose exec web python manage.py showmigrations exercises

# 4) Collect static (served by nginx from the volume)
docker compose exec web python manage.py collectstatic --noinput

# 5) Verify
docker compose logs -n 200 web | tail -n +1 | cat


Only app code changed (keep db/proxy untouched):

    docker compose up -d --build --no-deps web
    docker compose exec web python manage.py migrate
    docker compose exec web python manage.py collectstatic --noinput


# Copy data over


    python manage.py dumpdata exercises.Course exercises.Module exercises.Exercise exercises.ExerciseAsset --indent 2 > fixtures/courses_modules_exercises.json
    docker compose cp fixtures/courses_modules_exercises.json web:/tmp/cme.json
    docker compose exec -T web python /app/manage.py loaddata /tmp/cme.json


# New Relic

New Relic agent runs inside the `web` container via `newrelic-admin run-program` and reads `/app/steacher_app/newrelic.ini`.

Setup:

1) Add to `.env.production`:

```bash
NEW_RELIC_LICENSE_KEY=REDACTED
```

2) Deploy/restart `web`:

```bash
docker compose  up -d --build web
```

3) Verify agent startup in logs:

```bash
docker compose logs -n 200 web | cat
```

You should see lines similar to:

```text
New Relic Python Agent (X.Y.Z)
INFO - New Relic agent initialized
Connected to collector.*newrelic.com
```

Troubleshooting:
- Ensure `NEW_RELIC_LICENSE_KEY` is set and non-empty
- Check `NEW_RELIC_CONFIG_FILE` path (defaults to `/app/steacher_app/newrelic.ini`)
- Make sure `newrelic` is in `requirements.txt`


----

# Clean up Docker safely (keeps databases/volumes)


```bash
# Remove stopped containers, dangling images, unused networks (safe)
docker system prune -f

# Also remove ALL unused images (not just dangling)
docker system prune -a -f

# Remove builder cache (often several GB)
docker builder prune -a -f
```


----

# update ubuntu

```bash
sudo apt update
sudo apt upgrade
sudo apt autoremove
sudo apt clean
```

----

# test scala interpreter

Kind of for small tests to check if parallelism is working.

```bash
docker exec scala-interpreter-container sh -lc 'seq 1 50 | xargs -I{} -P 20 sh -lc "curl -s -X POST -H \"Content-Type: application/json\" -d '\''{\"code\":\"Thread.sleep(300); println(\\\"hi\\\")\"}'\'' http://localhost:8642/execute; echo"'
```

on VM:

```bash
docker exec steacher_app-scala_interpreter-1 sh -lc 'seq 1 50 | xargs -I{} -P 20 sh -lc "curl -s -X POST -H \"Content-Type: application/json\" -d '\''{\"code\":\"println(\\\"hi\\\")\",\"timeoutMs\":8000}'\'' http://localhost:8642/execute; echo"'
```



----

# Force maintenance mode

```bash
# Recreate proxy to pick up the /var/www mount
docker compose up -d --no-deps --force-recreate proxy

# Sanity checks
docker compose exec -T proxy sh -lc 'ls -la /var/www | cat'     # should list maintenance_on
docker compose exec -T proxy nginx -T | grep -n maintenance_on | cat

# Now toggle (if not already on, create; otherwise just reload)
touch nginx/maintenance/maintenance_on
docker compose exec -T proxy nginx -s reload

# Verify returns 503
curl -I https://steacher.org/ | head -n 1
```


# Force normal mode

```bash
rm nginx/maintenance/maintenance_on
docker compose exec -T proxy nginx -s reload

# Verify returns 200
curl -I https://steacher.org/ | head -n 1
```



# Invite students


1) create cohort, copy id
2) create csv with a column called email
3)
```bash
docker cp ../2025_year2_students.csv steacher_app-web-1:/tmp/invites.csv
# set right cohort id
docker exec steacher_app-web-1 python manage.py create_user_invites /tmp/invites.csv 11111
```


# Find size of db tables

```bash
docker compose exec -T db psql -U steacher_admin steacher_prod -c "SELECT schemaname || '.' || relname AS table, pg_size_pretty(pg_total_relation_size(relid)) AS total, pg_size_pretty(pg_relation_size(relid)) AS data, pg_size_pretty(pg_total_relation_size(relid) - pg_relation_size(relid)) AS idx_toast FROM pg_catalog.pg_statio_user_tables ORDER BY pg_total_relation_size(relid) DESC LIMIT 20;"

docker compose exec -T db psql -U steacher_admin steacher_prod -c  "
  SELECT
    s.attname AS column_name,
    pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
    pg_size_pretty(
      ((1 - COALESCE(s.null_frac, 0)) *
       COALESCE(s.avg_width, 0) *
       (SELECT reltuples::bigint FROM pg_class WHERE oid = 'exercises_trace'::regclass)
      )::bigint
    ) AS estimated_size
  FROM pg_attribute a
  JOIN pg_stats s ON a.attname = s.attname
    AND s.schemaname = 'public'
    AND s.tablename = 'exercises_trace'
  LEFT JOIN pg_class c ON a.attrelid = c.oid
  WHERE a.attrelid = 'exercises_trace'::regclass
    AND a.attnum > 0
    AND NOT a.attisdropped
  ORDER BY estimated_size DESC;
  "
```


# Replay db backup locally

CONTAINER=my-local-postgres
DB=steacher
DB_USER=postgres
PROD_BACKUP=/Users/ren/switchdrive/backup/dev/AI_x_teaching/pi_learning/backup/db_2025-10-12_13-38-54.sql


docker exec -i my-local-postgres psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS steacher;"

docker exec -i my-local-postgres psql -U postgres -d postgres -c "CREATE DATABASE steacher;"

# Create required roles
docker exec -i my-local-postgres psql -U postgres -d postgres -v ON_ERROR_STOP=1 \
  -c "DO \$\$BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='steacher_admin') THEN
          CREATE ROLE steacher_admin LOGIN;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='newrelic') THEN
          CREATE ROLE newrelic LOGIN;
        END IF;
      END\$\$;"

docker run --rm -i --network container:my-local-postgres   -e PGPASSWORD="myverysecretpassword" postgres:17   psql -h 127.0.0.1 -U postgres -d steacher -v ON_ERROR_STOP=1 < "$PROD_BACKUP"
