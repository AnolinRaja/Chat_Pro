# Phase 5.5.4: Quick Reference Guide

## What Was Added

### 1. Connection Metadata Tracking
Every WebSocket connection now tracks:
- `conversation_id`: Which conversation this connection belongs to
- `user_id`: Which user opened this connection (from JWT)
- `connected_at`: When the connection was established
- `last_activity`: When the most recent message was received

**Accessed via**: `connection_manager._metadata[websocket]`

### 2. Health Statistics
Check connection health for any conversation:
```python
from app.services.connection_manager import connection_manager

stats = connection_manager.get_conversation_stats(conversation_id)
# Returns: {"total_connections": 2, "healthy_connections": 1, "idle_connections": 1}
```

### 3. Activity Tracking
Automatically updated when a message is received. No manual action needed.

### 4. Configuration
Set idle detection threshold via environment variable:
```bash
export WEBSOCKET_IDLE_THRESHOLD_SECONDS=600  # 10 minutes (default: 300 = 5 min)
python -m uvicorn app.main:app --reload
```

### 5. Lifecycle Logging
Connection events are logged with conversation_id and user_id:
```
WebSocket connection established for conversation_id=conv_123 user_id=user_456
WebSocket connection removed for conversation_id=conv_123 user_id=user_456
```

## Key Implementation Points

**Idle Detection Logic**:
- A connection is **idle** if: `(now - last_activity).total_seconds() >= THRESHOLD`
- Default threshold: 300 seconds (5 minutes)
- Status: Classification only (NO automatic closure in Phase 5.5.4)

**Data Safety**:
- ✅ Logs: conversation_id, user_id, lifecycle events only
- ❌ Never logged: JWT tokens, HTTP headers, message contents, passwords

**Backward Compatibility**:
- Old code: `connection_manager.add_connection(conv_id, ws)` ✅ Still works
- New code: `connection_manager.add_connection(conv_id, ws, user_id)` ✅ Also works

## Common Tasks

### Check if a connection is idle
```python
from datetime import datetime, timezone
from app.config import settings

metadata = connection_manager._metadata.get(websocket)
if metadata:
    idle_seconds = (datetime.now(timezone.utc) - metadata["last_activity"]).total_seconds()
    is_idle = idle_seconds >= settings.WEBSOCKET_IDLE_THRESHOLD_SECONDS
    print(f"Connection idle for {idle_seconds}s (idle={is_idle})")
```

### Get all conversation statistics
```python
stats = connection_manager.get_conversation_stats(conversation_id)
print(f"Total: {stats['total_connections']}, Healthy: {stats['healthy_connections']}, Idle: {stats['idle_connections']}")
```

### Update activity manually (rarely needed)
```python
# Normally done automatically in routes/conversations.py
connection_manager.update_activity(websocket)
```

### Get connection metadata
```python
metadata = connection_manager._metadata.get(websocket)
print(f"User {metadata['user_id']} in conversation {metadata['conversation_id']}")
print(f"Connected: {metadata['connected_at']}, Last active: {metadata['last_activity']}")
```

## Testing Phase 5.5.4

Run Phase 5.5.4 tests only:
```bash
pytest -v backend/tests/test_phase_5_5_4_health_tracking.py
# Result: 15 passed
```

Run WebSocket tests (existing + Phase 5.5.4):
```bash
pytest -v backend/tests/test_websocket_conversations.py
# Result: 26 passed (unchanged from Phases 5.3-5.5.3)
```

Run all tests:
```bash
pytest backend/tests -q
# Result: 91 passed
```

## Files to Know

| File | Purpose | Key Methods |
|------|---------|-------------|
| `app/config.py` | Configuration | `settings.WEBSOCKET_IDLE_THRESHOLD_SECONDS` |
| `app/services/connection_manager.py` | Connection management | `add_connection()`, `update_activity()`, `get_conversation_stats()` |
| `app/routes/conversations.py` | WebSocket handler | Calls `add_connection()`, `update_activity()`, lifecycle logging |
| `tests/test_phase_5_5_4_health_tracking.py` | Test suite | 15 test functions covering all Phase 5.5.4 features |

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `WEBSOCKET_IDLE_THRESHOLD_SECONDS` | `300` | Idle detection threshold in seconds (5 minutes) |

## Important Notes

1. **Idle connections are NOT closed automatically** in Phase 5.5.4
   - Idle classification is for observability/monitoring only
   - Future phases may add optional automatic closure

2. **Metadata is NOT persisted to database**
   - Only kept in memory during connection lifetime
   - Cleaned up on disconnect

3. **Activity tracking is automatic**
   - No code changes needed in application code
   - Happens immediately after message receive

4. **Logging is safe from data leaks**
   - Only conversation_id and user_id logged
   - Never: JWT tokens, message content, passwords
   - Verified by unit tests

## Troubleshooting

**Q: Why is my connection showing as idle?**
A: The connection hasn't received a message in the last `WEBSOCKET_IDLE_THRESHOLD_SECONDS` (default 300 seconds). This is normal for silent conversations.

**Q: Can I change the idle threshold?**
A: Yes! Set `WEBSOCKET_IDLE_THRESHOLD_SECONDS` environment variable before starting the app.

**Q: Will idle connections be closed?**
A: Not in Phase 5.5.4. Idle detection is observational only. Check back in Phase 5.5.5 for enforcement options.

**Q: How do I check connection health in production?**
A: Use `get_conversation_stats(conversation_id)` to get real-time connection counts.

---

**Phase 5.5.4 Status**: ✅ Complete - 91/91 tests passing - Production Ready
