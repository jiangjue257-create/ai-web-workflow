from app.task_store import TaskStore


def test_create_returns_pending_task_with_defaults():
    store = TaskStore()

    task = store.create(kind="video", prompt="a neon city")

    assert task["id"]
    assert task["kind"] == "video"
    assert task["prompt"] == "a neon city"
    assert task["status"] == "pending"
    assert task["message"] == "等待开始"
    assert task["error"] == ""
    assert task["file_url"] == ""
    assert task["file_name"] == ""
    assert task["raw"] is None
    assert task["created_at"]
    assert task["updated_at"] == task["created_at"]


def test_update_merges_fields_and_preserves_existing_values():
    store = TaskStore()
    task = store.create(kind="image", prompt="a neon city")

    updated = store.update(
        task["id"],
        status="completed",
        file_url="/api/files/x.png",
    )

    assert updated["id"] == task["id"]
    assert updated["kind"] == "image"
    assert updated["prompt"] == "a neon city"
    assert updated["status"] == "completed"
    assert updated["file_url"] == "/api/files/x.png"


def test_get_missing_returns_none():
    store = TaskStore()

    task = store.get("missing")

    assert task is None


def test_returned_tasks_are_copies():
    store = TaskStore()
    task = store.create(kind="image", prompt="cat")

    task["status"] = "completed"
    task["raw"] = {"changed": True}

    stored = store.get(task["id"])

    assert stored["status"] == "pending"
    assert stored["raw"] is None
