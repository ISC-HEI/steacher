# Automatic Periodic Cleanup for Expired Images

**Status:** 📋 Todo  
**Priority:** Low  
**Related Spec:** `specs/done/251116_image_upload_for_exercises.md`

## Overview

Implement an automatic periodic cleanup system to run the existing `cleanup_expired_images` Django management command. This will maintain database hygiene by automatically removing orphaned `TraceImage` upload tokens without requiring manual maintenance.

## Problem Statement

### Current Situation
- The `cleanup_expired_images` management command exists and works correctly
- It removes expired upload tokens (from TraceImage) that were never linked to a trace
- Currently requires manual execution via `python manage.py cleanup_expired_images`
- No automatic scheduling mechanism in place

### Requirements
- Automatic execution of cleanup command at regular intervals
- Minimal infrastructure overhead (avoid adding Celery if not already present)
- Configurable cleanup schedule
- Logging of cleanup operations for monitoring
- Graceful handling of failures
- Production-ready solution

## Current Command Analysis

**Location:** `steacher_app/exercises/management/commands/cleanup_expired_images.py`

**Functionality:**
- Deletes `TraceImage` records where:
  - `token_expires_at < now()` (token has expired)
  - `trace__isnull=True` (never linked to an actual trace)
- Supports `--dry-run` flag for testing
- Provides detailed output of what will be/was deleted
- Shows count and sample of orphaned tokens

**Token Expiry:** 10 minutes (from upload token generation)

## Proposed Solutions

### Option 1: Django-APScheduler (Recommended)

**Rationale:**
- Lightweight, Django-native solution
- No additional infrastructure (Redis/RabbitMQ) required
- Easy to configure and monitor
- Stores job state in Django database
- Good for periodic tasks without complex dependencies

**Implementation:**

1. **Dependencies:**
   ```
   django-apscheduler==0.6.2
   ```

2. **Configuration:**
   - Add `django_apscheduler` to `INSTALLED_APPS`
   - Create scheduler configuration in settings
   - Define schedule interval (e.g., every 6 hours, daily at 3 AM)

3. **Code Structure:**
   ```
   steacher_app/exercises/
   ├── management/
   │   └── commands/
   │       ├── cleanup_expired_images.py  (existing)
   │       └── start_scheduler.py         (new)
   └── scheduler.py                       (new - job definitions)
   ```

4. **Job Definition:**
   - Create `scheduler.py` to define the cleanup job
   - Use `call_command('cleanup_expired_images')` to invoke existing command
   - Add error handling and logging
   - Configure retry logic if needed

5. **Deployment:**
   - Run scheduler as a separate process: `python manage.py start_scheduler`
   - Update docker-compose.yml to add scheduler service
   - Or integrate into existing application startup (less recommended)

**Pros:**
- Simple to implement and maintain
- No new infrastructure components
- Job history stored in database
- Web UI available for monitoring (django-apscheduler admin)

**Cons:**
- Requires running separate process
- Less robust than dedicated task queue for high-scale systems
- Limited distributed task capabilities

### Option 2: Celery Beat

**Rationale:**
- Industry-standard solution for periodic tasks
- More robust for complex scheduling needs
- Better for systems that may need more background tasks later

**Implementation:**

1. **Dependencies:**
   ```
   celery==5.3.4
   celery[redis]==5.3.4  (or celery[rabbitmq])
   django-celery-beat==2.5.0
   ```

2. **Infrastructure:**
   - Redis already present (used by Channels)
   - Can reuse existing Redis for Celery broker
   - Requires Celery worker process
   - Requires Celery beat process

3. **Configuration:**
   - Add Celery configuration to settings
   - Create `celery.py` in project root
   - Define periodic task schedule
   - Create Celery task wrapper for cleanup command

4. **Code Structure:**
   ```
   steacher_app/
   ├── exam_project/
   │   ├── celery.py              (new - Celery app config)
   │   └── settings.py            (update - Celery settings)
   └── exercises/
       └── tasks.py               (new - Celery tasks)
   ```

5. **Deployment:**
   - Run Celery worker: `celery -A exam_project worker -l info`
   - Run Celery beat: `celery -A exam_project beat -l info`
   - Update docker-compose.yml for both services

**Pros:**
- Production-proven, robust solution
- Better for scaling to multiple periodic tasks
- Advanced features (retries, rate limiting, task chaining)
- Excellent monitoring tools available

**Cons:**
- More complex setup and maintenance
- Requires running two additional processes
- Overkill if only one periodic task is needed
- Steeper learning curve

### Option 3: System Cron Job

**Rationale:**
- Unix/Linux native scheduling
- Simplest approach with no Python dependencies
- Well-understood by system administrators

**Implementation:**

1. **Cron Configuration:**
   ```bash
   # Run cleanup daily at 3 AM
   0 3 * * * cd /path/to/steacher_app && /path/to/venv/bin/python manage.py cleanup_expired_images >> /var/log/cleanup_images.log 2>&1
   ```

2. **Docker Integration:**
   - Install cron in Docker container
   - Add crontab configuration to container
   - Ensure cron daemon runs in container

3. **Deployment:**
   - Update Dockerfile to install cron
   - Add crontab file to repository
   - Configure logging to Docker volumes

**Pros:**
- Zero Python dependencies
- Simple and reliable
- Standard approach for periodic system tasks

**Cons:**
- Less portable across different environments
- Harder to manage in containerized environments
- No built-in monitoring or error handling
- Cannot easily modify schedule without deployment

## Recommended Approach

**Use Option 1: Django-APScheduler**

### Reasoning:
1. **Simplicity:** Minimal code changes, no new infrastructure
2. **Integration:** Works seamlessly with existing Django setup
3. **Maintenance:** Easy to configure, monitor, and debug
4. **Scalability:** Sufficient for current needs (single periodic task)
5. **Future-proof:** Can migrate to Celery later if more complex task needs arise

### Cleanup Schedule Recommendation:
- **Frequency:** Every 6 hours (4 times daily)
- **Rationale:** 
  - Tokens expire after 10 minutes
  - Running cleanup more frequently than hourly is unnecessary
  - 6-hour interval provides good balance between database cleanliness and system overhead
  - Runs at: 00:00, 06:00, 12:00, 18:00 UTC

## Implementation Plan

### Phase 1: Setup Django-APScheduler

1. **Add dependency:**
   - Update `requirements.txt` to add `django-apscheduler==0.6.2`
   - Run `pip install django-apscheduler`

2. **Update settings:**
   - Add `'django_apscheduler'` to `INSTALLED_APPS` in `exam_project/settings.py`
   - Run migrations: `python manage.py migrate`

### Phase 2: Create Scheduler Job

3. **Create scheduler configuration file:**
   - File: `steacher_app/exercises/scheduler.py`
   - Define `cleanup_expired_images_job()` function
   - Use `call_command('cleanup_expired_images')` internally
   - Add logging (using Python logging or Django logging)
   - Add error handling with try/except

4. **Create management command:**
   - File: `steacher_app/exercises/management/commands/start_scheduler.py`
   - Initialize APScheduler
   - Register the cleanup job
   - Configure schedule (CronTrigger or IntervalTrigger)
   - Keep scheduler running

### Phase 3: Testing

5. **Local testing:**
   - Test dry-run mode
   - Create test orphaned tokens
   - Verify cleanup executes at scheduled time
   - Check logging output

6. **Integration testing:**
   - Test scheduler startup/shutdown
   - Verify job history in database
   - Test error scenarios (database unavailable, etc.)

### Phase 4: Deployment

7. **Update docker-compose.yml:**
   ```yaml
   scheduler:
     build: ./steacher_app
     command: python manage.py start_scheduler
     depends_on:
       - db
       - redis
     environment:
       - DATABASE_URL=...
       - REDIS_URL=...
     restart: unless-stopped
   ```

8. **Update documentation:**
   - Add scheduler setup to README
   - Document how to monitor cleanup jobs
   - Add troubleshooting section

9. **Monitoring setup:**
   - Configure alerts for scheduler failures (optional)
   - Set up log aggregation for cleanup events
   - Document how to check APScheduler job history in Django admin

## Configuration Options

### Scheduler Settings (in settings.py)

```python
# APScheduler Configuration
APSCHEDULER_DATETIME_FORMAT = "N j, Y, f:s a"
APSCHEDULER_RUN_NOW_TIMEOUT = 25  # Seconds

# Cleanup Job Configuration
CLEANUP_IMAGES_SCHEDULE = {
    'interval': 6,  # hours
    'unit': 'hours',
}

# Or use cron-style scheduling:
CLEANUP_IMAGES_CRON = {
    'hour': '*/6',  # Every 6 hours
    'minute': '0',
}
```

## Monitoring and Maintenance

### Job History
- APScheduler stores job execution history in database
- Available via Django admin interface
- Can query `DjangoJobExecution` model programmatically

### Logging
- Log each cleanup execution (start time, records deleted, errors)
- Use Django logging framework
- Configure log level and destination in settings

### Health Checks
- Monitor scheduler process uptime
- Alert if scheduler hasn't run in expected interval
- Check database for failed job executions

### Manual Execution
- Original command still available: `python manage.py cleanup_expired_images`
- Useful for debugging or one-off cleanups
- Use `--dry-run` for testing

## Security Considerations

1. **Database Access:**
   - Scheduler runs with same database permissions as Django app
   - No additional security concerns

2. **Process Isolation:**
   - Consider running scheduler in separate container
   - Reduces impact if scheduler crashes

3. **Error Handling:**
   - Ensure failed cleanup doesn't crash scheduler
   - Log errors but continue scheduling next runs

## Rollback Plan

If issues arise:
1. Stop scheduler process
2. Remove `django_apscheduler` from INSTALLED_APPS
3. Run database migration rollback if needed
4. Return to manual cleanup execution

## Future Enhancements

1. **Additional Cleanup Tasks:**
   - Old session data
   - Expired quiz attempts
   - Temporary file cleanup
   - Old log entries

2. **Advanced Scheduling:**
   - Different frequencies for different environments (dev vs prod)
   - Time-of-day scheduling (run during low-traffic periods)
   - Conditional execution based on database size

3. **Monitoring Integration:**
   - NewRelic custom events for cleanup operations
   - Slack/email notifications for failures
   - Dashboard for cleanup statistics

4. **Optimization:**
   - Batch processing for large cleanup operations
   - Rate limiting to avoid database load spikes

## Testing Checklist

- [ ] Scheduler starts successfully
- [ ] Cleanup job executes at scheduled time
- [ ] Expired tokens are deleted correctly
- [ ] Non-expired tokens are preserved
- [ ] Linked tokens (with traces) are not deleted
- [ ] Logging works correctly
- [ ] Error handling works (simulated failures)
- [ ] Scheduler survives app restart
- [ ] Docker deployment works
- [ ] Job history visible in Django admin
- [ ] Manual command still works independently

## Success Metrics

- **Database Size:** Track `TraceImage` table size over time
- **Orphaned Records:** Should remain low (< 100 at any time)
- **Cleanup Frequency:** 4 executions per day
- **Execution Time:** Cleanup should complete in < 1 minute
- **Uptime:** Scheduler process 99%+ uptime
- **Zero Manual Intervention:** No manual cleanup runs needed

## References

- Django-APScheduler Documentation: https://github.com/jcass77/django-apscheduler
- APScheduler Documentation: https://apscheduler.readthedocs.io/
- Existing Command: `exercises/management/commands/cleanup_expired_images.py`
- Image Upload Spec: `specs/done/251116_image_upload_for_exercises.md`
