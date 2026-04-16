"""
google_services/firestore_client.py
-------------------------------------
Firestore integration (mock-ready).

Swap the mock body with real firebase_admin calls when going to production.
The rest of the codebase never needs to change.

Optimization vs original:
  - _MOCK_STORE is now an OrderedDict with a hard cap of _MAX_MOCK_DOCS entries.
    Navigation records (one per user_id) are inherently bounded.
    Crowd snapshot records (one per timestamp) were unbounded; the cap prevents
    memory growth during long-running local sessions.
"""

import logging
from collections import OrderedDict
from typing import Dict, Any, Optional
from app.config import settings

logger = logging.getLogger(__name__)

# Hard cap on the number of documents held in the in-memory mock store.
# Nav records: O(unique users) — stays small.
# Crowd snapshots: O(requests × time) — this cap prevents runaway growth.
_MAX_MOCK_DOCS: int = 512

# ---------------------------------------------------------------------------
# Setup Firestore Client (Optional)
# ---------------------------------------------------------------------------
db = None
if getattr(settings, "firestore_enabled", False):
    try:
        from google.cloud import firestore
        # Uses Application Default Credentials (ADC)
        db = firestore.Client(project=settings.gcp_project_id if settings.gcp_project_id else None)
        logger.info("Firestore client initialized.")
    except Exception as e:
        logger.warning(f"Failed to initialize Firestore (falling back to mock): {e}")

# ---------------------------------------------------------------------------
# Mock store — OrderedDict so we can evict oldest entries when over the cap
# ---------------------------------------------------------------------------
_MOCK_STORE: OrderedDict = OrderedDict()


def _set_doc(collection: str, document_id: str, data: Dict, mock_key: str) -> None:
    """Helper to safely write to Firestore or fallback to the mock store."""
    if db is not None:
        try:
            db.collection(collection).document(document_id).set(data)
            logger.debug("Firestore saved %s/%s", collection, document_id)
            return
        except Exception as e:
            logger.error("Firestore error on %s/%s: %s. Falling back to mock.", collection, document_id, e)

    # Move-to-end keeps frequently updated keys (e.g. nav/{user_id}) from being evicted
    _MOCK_STORE[mock_key] = data
    _MOCK_STORE.move_to_end(mock_key)

    # Evict oldest entry if over cap
    while len(_MOCK_STORE) > _MAX_MOCK_DOCS:
        _MOCK_STORE.popitem(last=False)

    logger.debug("Firestore [MOCK] saved %s", mock_key)


def save_navigation_request(user_id: str, data: Dict) -> None:
    """Persists a navigation request for a user."""
    _set_doc("navigation_requests", user_id, data, mock_key=f"nav/{user_id}")


def get_user_history(user_id: str) -> Optional[Dict]:
    """Retrieves the most recent navigation request for a user."""
    if db is not None:
        try:
            doc = db.collection("navigation_requests").document(user_id).get()
            if doc.exists:
                return doc.to_dict()
            return None
        except Exception as e:
            logger.error("Firestore read failed for %s: %s. Falling back to mock.", user_id, e)

    return _MOCK_STORE.get(f"nav/{user_id}")


def save_crowd_snapshot(snapshot: Dict) -> None:
    """Persists a crowd density snapshot (for historical analytics)."""
    key = str(snapshot.get('timestamp', 'unknown'))
    _set_doc("crowd_snapshots", key, snapshot, mock_key=f"crowd/{key}")


def update_dismissed_route(user_id: str, dismissed_fingerprint: str, dismissed_at: str) -> None:
    """Records that the user dismissed a reroute suggestion.

    Stores the route fingerprint and timestamp so the alerts endpoint can
    suppress the same suggestion for a cooldown period.
    """
    existing = get_user_history(user_id) or {}
    existing["dismissed_fingerprint"] = dismissed_fingerprint
    existing["dismissed_at"] = dismissed_at
    _set_doc("navigation_requests", user_id, existing, mock_key=f"nav/{user_id}")


def update_accepted_route(user_id: str, new_route_data: Dict) -> None:
    """Persists an accepted reroute as the user's active navigation state.

    Replaces the stored route, resets dismissed state, and sets
    current_zone_index back to 0 (start of the new route).
    """
    new_route_data["current_zone_index"] = 0
    new_route_data["dismissed_fingerprint"] = ""
    new_route_data["dismissed_at"] = ""
    _set_doc("navigation_requests", user_id, new_route_data, mock_key=f"nav/{user_id}")
