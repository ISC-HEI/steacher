# Scala Interpreter Service - Design Specification

**Created:** September 4, 2025  
**Status:** Implemented  
**Type:** Infrastructure / Backend Service

## Overview

The Scala Interpreter Service is a containerized REST API that enables students to execute Scala code exercises with sub-second response times. This service provides a secure, isolated environment for running untrusted student code while maintaining system safety through multiple layers of protection.

## Rationale

### Problem Statement

To support Scala programming exercises in the Steacher platform, we need a system that:
1. **Responds rapidly** (target: under 1 second) to feel reactive and maintain student engagement
2. **Executes untrusted code safely** without compromising the host system or other users
3. **Handles concurrent student requests** efficiently during class sessions
4. **Provides meaningful error feedback** to guide students through compilation and runtime issues

### Why Not Client-Side Execution?

Unlike Python (Pyodide) and SQL (PGlite), which run entirely in the browser using WASM, Scala currently lacks a WASM browser-based runtime. The Scala WASM story is still evolving, making a server-side solution necessary for now.

## Design Alternatives Considered

### 1. Scastie (https://scastie.scala-lang.org/, an interactive playground for Scala with support for sbt configuration.)
- **Pros:** Purpose-built for scripting
- **Cons:** Limited adoption, uncertain maintenance, compatibility concerns

### 2. Ammonite REPL
- **Pros:** Popular, feature-rich, good for interactive sessions
- **Cons:** Heavier runtime overhead, more complex than needed for our use case. Was making trouble in terms of securing the Docker container, because it's downloading a lot of dependencies and I didn't know how to make it secure.

### 3. Scala Toolbox (Selected Solution)
- **Pros:** Official Scala runtime, direct compiler access, lightweight, fast compilation/execution
- **Cons:** Requires careful isolation and resource management. **Has to execute untrusted code.**
- **Decision:** Chosen for its simplicity, speed, and official support

## Architecture

### System Design

```
┌─────────────┐         ┌──────────────┐         ┌─────────────────────┐
│   Student   │────────>│  Django Web  │────────>│ Scala Interpreter   │
│   Browser   │         │   Backend    │         │   (Docker)          │
└─────────────┘         └──────────────┘         └─────────────────────┘
                              │                            │
                              │                            │
                        Rate Limiting               Internal Network
                        (Session-based)             (compute network)
```

### Implementation Details

#### Core Service (`RestServer.scala`)

The service is a minimal REST API built with:
- **Framework:** Spark Java (lightweight HTTP server)
- **Compiler:** Scala Toolbox (`scala-reflect`, `scala-compiler`)
- **Scala Version:** 2.13.16, in sync with our class at ISC.
- **Architecture:** Worker pool with persistent toolboxes

#### Worker Pool Architecture

```scala
class WorkerPool(size: Int = 4) {
    private val workers: Array[InterpreterWorker]
    // Round-robin worker selection
    // Each worker maintains:
    // - Dedicated classloader (isolation)
    // - Persistent Scala compiler instance
    // - Persistent toolbox (prewarmed)
    // - Single-threaded executor (timeout control)
}
```

**Key Design Choices:**

1. **Persistent Toolboxes:** Each worker maintains a prewarmed toolbox to avoid cold-start overhead (~100ms savings per request)
2. **Worker Isolation:** Separate classloaders prevent cross-contamination of compiled artifacts
3. **Timeout Control:** Each worker runs in its own executor thread with configurable timeout (default: 2000ms)
4. **Output Truncation:** Results capped at 4000 characters to prevent memory/bandwidth abuse

#### Code Safety Features

1. **Static Pattern Detection** (super basic):
   ```scala
   val dangerousPatterns = List(
     "Runtime.getRuntime()",
     "sys.process",
     "new ProcessBuilder",
     "Files.delete",
     ".delete()"
   )
   ```

2. **Compilation Check:** Two-phase execution:
   - Fast path: Direct [Scala Toolbox](https://docs.scala-lang.org/overviews/reflection/environment-universes-mirrors.html) evaluation
   - On error: Detailed compilation check with line/column error reporting

3. **ANSI Stripping:** Color codes removed for clean error messages. Kinda hacky, but works.

4. **Concise Error Formatting:** Extracts code line, caret indicator, and message only

## Security Model

Security is achieved through **defense in depth** with multiple layers:

### Layer 1: Network Isolation

**Docker Network Configuration:**
```yaml
networks:
  compute:
    driver: bridge
    internal: true  # No outbound egress
```

- Service runs on internal `compute` network
- No external internet access
- Only accessible to `web` service container
- No ports exposed to host machine

### Layer 2: Container Hardening

**Dockerfile Security:**
```dockerfile
USER 10001:10001  # Non-root execution
```

**Docker Compose Security:**
```yaml
security_opt:
  - no-new-privileges:true
cap_drop:
  - ALL  # Remove all Linux capabilities
read_only: true
tmpfs:
  - /tmp  # Only writable location
```

### Layer 3: Resource Limits

```yaml
mem_limit: 1g           # Hard memory cap
cpus: "1"               # Single CPU core
pids_limit: 256         # Prevents fork bombs
ulimits:
  nproc: 512
  nofile: 4096
JAVA_TOOL_OPTIONS: -Xms128m -Xmx512m  # JVM heap limits
```

### Layer 4: Application-Level Throttling

**Rate Limiting (`exercises/authz.py`):**
```python
@rate_limit(user_limit=20, user_burst=10, ip_limit=60, ip_burst=20, name='scala_execute')
def scala_execute(request):
    # Session-backed rate limiting
    # Window: 60 seconds
    # Returns: 429 with Retry-After header
```

**Throttle Parameters:**
- **Per User:** 20 requests/minute + 10 burst capacity
- **Per IP:** 60 requests/minute + 20 burst capacity
- **Window:** 60 seconds sliding window
- **Storage:** Django session (no external infrastructure needed)
- **Response:** HTTP 429 with `Retry-After` header

**Throttle Logging:**
```python
logger.info("Rate limit hit (user) for %s uid=%s ip=%s", 
            name, uid, client_ip)

# NewRelic custom event for alerting
nr.record_custom_event('RateLimitExceeded', {
    'limit_type': 'user',
    'endpoint': name,
    'user_id': uid,
    'ip_address': client_ip,
    'limit': user_limit,
    'burst': user_burst,
    'window_seconds': WINDOW_SECONDS,
})
```

Logs to `steacher.log` at INFO level and creates NewRelic custom events for monitoring.

## API Specification

### Endpoint: `POST /execute`

**Request:**
```json
{
  "code": "val x = 5 * 10\nprintln(s\"Result: $x\")",
  "timeoutMs": 2000
}
```

**Success Response:**
```json
{
  "success": true,
  "workerId": 2,
  "output": "Result: 50\n",
  "error": ""
}
```

**Compilation Error Response:**
```json
{
  "success": false,
  "workerId": 0,
  "error": "println(undefinedVar)\n        ^\nnot found: value undefinedVar",
  "output": ""
}
```

**Timeout Response:**
```json
{
  "success": false,
  "workerId": 1,
  "error": "Timeout after 2000ms"
}
```

**Dangerous Code Response:**
```json
{
  "success": false,
  "error": "Dangerous code detected"
}
```

## Integration with Steacher

### Django Integration

**Settings (`exam_project/settings.py`):**
```python
SCALA_INTERPRETER_URL = os.getenv('SCALA_INTERPRETER_URL', 
                                   'http://scala_interpreter:8642')
```

**View Handler (`exercises/views_students.py`):**
```python
@login_required
@require_POST
@rate_limit(user_limit=20, user_burst=10, ip_limit=60, ip_burst=20, 
            name='scala_execute')
def scala_execute(request):
    # Proxy to scala_interpreter service
    # Normalizes response format
    # Tracks execution duration
```

**Unit Testing (`exercises/unit_testing.py`):**
```python
def run_unit_tests_scala(student_code: str, unit_tests_data: dict) -> dict:
    # Wraps student code with test harness
    # Executes via scala_interpreter service
    # Returns pass/fail results with detailed feedback
```

### Frontend Integration

Student code editor (`frontend/scala.ts`) sends POST requests to Django endpoint, which proxies to the interpreter service with rate limiting applied.

## Testing

### Test Suite (`test_server.py`)

**Expected Performance:**
- Average request latency: ~50-150ms (after warmup)
- First request: ~200-300ms (toolbox initialization)

## Operations & Monitoring

### Healthcheck

The container includes a healthcheck that performs real Scala computation:

```dockerfile
HEALTHCHECK --interval=30s --timeout=8s --retries=3 --start-period=15s \
  CMD sh -c "res=$(curl -sf -X POST -H 'Content-Type: application/json' \
             -d '{\"code\":\"println(1+1)\"}' http://localhost:8642/execute); \
             echo \"$res\" | grep -q '\"success\":true' && \
             echo \"$res\" | grep -q '\"output\":\"2' || exit 1"
```

### Logging

**Service Logs:**
- Request timeouts logged with `timeoutMs` value
- Console output redirected to Docker logs

**Throttle Logging:**
- Rate limit hits logged to `steacher.log` with user ID and IP
- Format: `Rate limit hit (user) for scala_execute uid=123 ip=192.168.1.1`

**Current Gap:** No structured incident reporting for throttle events

### Deployment

Service is deployed via `docker-compose.yml` as part of the Steacher stack:


## Limitations & Known Issues

1. **No Scala Standard Library Extensions:** Service runs with minimal classpath
2. **Pattern-Based Security:** Dangerous code detection can be bypassed with reflection/dynamic code
3. **Session-Based Throttling:** Rate limits reset if session is cleared
4. **No Persistent State:** Each request is isolated; no REPL-style context preservation
5. **Output Truncation:** Long outputs (>4000 chars) are truncated

## Future Directions

### Priority 1: Enhanced Monitoring ✅ IMPLEMENTED

**NewRelic Incident Reporting for Throttling**

Throttle events now create NewRelic custom events (`RateLimitExceeded`) that can trigger alerts and be queried for analysis.

**Implementation:** `exercises/authz.py` in the `rate_limit` decorator records custom events at both user and IP throttle points.

**Setting Up NewRelic Alerts:**

1. **Navigate to:** NewRelic One → Alerts & AI → Alert Conditions → New alert condition

2. **Create NRQL Alert Condition:**
   ```sql
   SELECT count(*) 
   FROM RateLimitExceeded 
   WHERE endpoint = 'scala_execute' 
   FACET user_id, ip_address
   ```

3. **Configure Thresholds:**
   - **Warning:** > 3 events in 5 minutes (single user repeatedly hitting limits)
   - **Critical:** > 10 events in 5 minutes (potential abuse or bug)

4. **Additional Useful Queries:**
   ```sql
   -- All rate limit events grouped by endpoint
   SELECT count(*) FROM RateLimitExceeded 
   FACET endpoint, limit_type SINCE 1 hour ago
   
   -- Top throttled users
   SELECT count(*) FROM RateLimitExceeded 
   WHERE user_id IS NOT NULL 
   FACET user_id SINCE 1 day ago LIMIT 20
   
   -- Throttle events by IP (potential DDoS)
   SELECT count(*) FROM RateLimitExceeded 
   WHERE limit_type = 'ip' 
   FACET ip_address SINCE 1 hour ago
   ```

**Event Attributes:**
- `limit_type`: 'user' or 'ip'
- `endpoint`: View function name (e.g., 'scala_execute')
- `user_id`: User ID (if authenticated)
- `ip_address`: Client IP address
- `limit`: Rate limit threshold
- `burst`: Burst capacity
- `window_seconds`: Time window (60s)

**Benefits:**
- ✅ Real-time alerts for potential abuse
- ✅ Dashboard metrics for throttle frequency
- ✅ User behavior patterns for capacity planning
- ✅ Historical analysis of service pressure

### Priority 2: WASM-Based Client-Side Execution

**Long-term Vision:** Package Scala as a WebAssembly library for browser-based execution, similar to Pyodide (Python) and PGlite (SQL).
Professor Dimi has expressed interest in exploring this direction.

**Benefits:**
- Zero server load for code execution
- Instant feedback (no network latency)
- Unlimited student throughput
- No security concerns (browser sandbox)

## References

### Internal Documentation
- `scala_interpreter/README.md` - Setup and usage guide
- `scala_interpreter/src/main/scala/RestServer.scala` - Service implementation
- `steacher_app/exercises/views_students.py` - Django integration
- `steacher_app/exercises/unit_testing.py` - Test harness
