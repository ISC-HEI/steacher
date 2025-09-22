# Redeploy on prod

```bash
ssh into vm

# backup
docker compose exec -T db pg_dump -U steacher_admin steacher_prod > ~/dev/manual_backup_db/db_$(date +%F).sql

# 1) Get latest code
git pull

# 2) toggle maintenance mode
touch nginx/maintenance/maintenance_on
# restart proxy
docker compose restart proxy


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

# 8) remove maintenance mode and restart proxy
rm nginx/maintenance/maintenance_on
docker compose restart proxy



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

1.  **Open your crontab editor:**
    ```bash
    crontab -e
    ```

2.  **Add the following line:**
    This will run the renewal command every day at 3:30 AM. Certbot will only renew the certificate if it's close to expiration.

    ```
    30 3 * * * /usr/bin/docker-compose -f /path/to/your/project/docker-compose.yml run --rm certbot renew --quiet && /usr/bin/docker-compose -f /path/to/your/project/docker-compose.yml restart proxy
    ```

    **Important:**
    *   Replace `/path/to/your/project/` with the absolute path to your project directory (where `docker-compose.yml` is located).
    *   Make sure the path to `docker-compose` is correct for your system (you can find it with `which docker-compose`).

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
