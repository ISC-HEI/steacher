


ssh into vm

git pull

docker compose --env-file .env.production up -d --build

docker compose exec web python manage.py collectstatic --noinput




docker compose logs web

------

# Installation

## Create instance

Horizon (openstack)

1. create keypair, copy/paste from my local key from `cat ~/.ssh/id_rsa.pub`
2. launch instance, select Ubuntu 24LTS, 2cpu 4gb ram, 20gb disk, network ivp4-something


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
