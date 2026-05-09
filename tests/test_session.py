from app.session import SessionStore


def test_create_session():
    store = SessionStore(secret_key="test-secret")
    session_id = store.create()
    assert session_id is not None
    assert len(session_id) > 0


def test_get_session():
    store = SessionStore(secret_key="test-secret")
    session_id = store.create()
    session = store.get(session_id)
    assert session == {}


def test_set_and_get_value():
    store = SessionStore(secret_key="test-secret")
    session_id = store.create()
    store.set(session_id, "access_token", "abc123")
    session = store.get(session_id)
    assert session["access_token"] == "abc123"


def test_get_nonexistent_session():
    store = SessionStore(secret_key="test-secret")
    session = store.get("nonexistent")
    assert session is None


def test_delete_session():
    store = SessionStore(secret_key="test-secret")
    session_id = store.create()
    store.delete(session_id)
    assert store.get(session_id) is None
