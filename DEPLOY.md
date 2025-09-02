


ssh into vm

git pull

docker compose --env-file .env.production up -d --build

docker compose exec web python manage.py collectstatic --noinput


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


