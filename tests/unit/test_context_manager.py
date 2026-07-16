from app.pipeline.context import RequestContext
from app.pipeline.manager import RequestContextManager


def test_context_manager_tracks_and_reaps_stale_requests() -> None:
    now = 100.0
    manager = RequestContextManager(stale_max_age=10, clock=lambda: now)
    context = RequestContext(original_model="m", original_payload={})
    context.created_at = now
    manager.register(context)
    assert manager.active_count == 1
    now = 111.0
    stale = manager.reap_stale()
    assert stale == [context]
    assert manager.active_count == 0