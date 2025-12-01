# Specification: Redis-Backed Rate Limiting

## 1. Problem Definition
The current rate limiting implementation (`authz.rate_limit`) stores request counters in the user's Django Session. 
- **Vulnerability**: An attacker can bypass IP-based rate limits (`ip_limit`) simply by clearing their cookies or not sending them, as this generates a fresh session with an empty bucket for each request.
- **Impact**: Critical endpoints like `mobile_auth_send_link` (email sending) and `scala_execute` (code execution) are vulnerable to automation and DoS.

## 2. Proposed Solution
Migrate the storage backend for rate limit buckets from `request.session` to **Redis**. Redis provides a fast, shared, and persistent store that is independent of client-side state (cookies).

### dependencies
The project already uses `channels-redis` and `redis` (per `requirements.txt`), so no new dependencies are needed. We can use the existing `REDIS_URL` setting.

## 3. Technical Design

### Algorithm: Sliding Window Log
We will use a **Sliding Window Log** algorithm implemented with Redis Sorted Sets (`ZSET`). This allows for precise time-based windows (e.g., "exact 60 seconds from now") rather than fixed windows (e.g., "reset at top of minute"), matching the current logic but secure.

### Redis Key Schema
Keys will beNamespaced to avoid collisions.
Format: `rl:{view_name}:{limit_type}:{identifier}:{window_size}`

- `view_name`: The name of the protected view (e.g., `mobile_upload_submit`).
- `limit_type`: `ip` or `user`.
- `identifier`: The IP address or User ID.
- `window_size`: The window duration in seconds (e.g., `60`).

**Example**: `rl:mobile_upload_submit:ip:192.168.1.50:60`

### Logic Flow (Per Request)

For a rate limit of **N** requests per **W** seconds:

1.  **Calculate Times**:
    - `now_ts`: Current timestamp in milliseconds.
    - `window_start_ts`: `now_ts - (W * 1000)`.

2.  **Redis Transaction (Pipeline)**:
    Execute the following operations atomically:
    - `ZREMRANGEBYSCORE key 0 window_start_ts`: Remove entries older than the window.
    - `ZADD key {now_ts:member_id} now_ts`: Add current request. `member_id` should be unique (e.g. random suffix) to allow multiple requests in the same millisecond.
    - `ZCARD key`: Count valid requests in the window.
    - `EXPIRE key W+1`: Set key to expire slightly after the window (auto-cleanup).

3.  **Decision**:
    - Fetch the result of `ZCARD`.
    - If `count > N`: **Block Request** (Return 429).
    - If `count <= N`: **Allow Request**.

## 4. Implementation Steps (in `exercises/authz.py`)

1.  **Setup Redis Client**:
    Initialize a global `redis_client` using `django.conf.settings.REDIS_URL`.

2.  **Refactor `rate_limit` Decorator**:
    - Remove session-based logic (`request.session.get`).
    - Implement the Redis pipeline logic described above.
    - Ensure `limit_type='ip'` uses `request.META.get('REMOTE_ADDR')` (or forwarded headers).
    - Ensure `limit_type='user'` uses `request.user.id`.

3.  **Failure Handling**:
    - Wrap Redis operations in a `try/except` block.
    - **Fail Open**: If Redis is down, log the error but allow the request to proceed. This prevents the rate limiter from becoming a single point of failure for the app.

## 5. Security Considerations
- **IP Spoofing**: Continue using the existing `_client_ip` helper to resolve `HTTP_X_FORWARDED_FOR` securely.
- **Resource Exhaustion**: The `EXPIRE` command ensures keys don't accumulate indefinitely in Redis.

