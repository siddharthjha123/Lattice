from control_plane.database.models import Box, ResourceReservation


def test_box_reservations_and_soft_delete(client, context, online):
    online("worker-1")
    online("worker-2")
    payload = {
        "name": "Failover Box",
        "ram_limit_gb": 2,
        "cpu_limit_cores": 2,
        "storage_limit_gb": 4,
        "eligible_worker_ids": ["worker-1", "worker-2"],
        "failover_enabled": True,
    }
    res = client.post("/api/boxes", json=payload)
    assert res.status_code == 201, res.text
    box = res.json()
    assert box["primary_worker_id"] != box["standby_worker_id"]
    with context.db.session() as session:
        assert session.query(ResourceReservation).count() == 2
    assert (
        client.post("/api/boxes", json=payload | {"cpu_limit_cores": 3}).status_code
        == 400
    )
    assert client.delete("/api/boxes/" + box["box_id"]).status_code == 200
    with context.db.session() as session:
        assert session.query(ResourceReservation).count() == 0
        assert session.query(Box).one().deleted_at is not None
    assert client.get("/api/boxes/" + box["box_id"]).status_code == 404


def test_offline_worker_cannot_back_box(client, provision):
    provision()
    res = client.post(
        "/api/boxes",
        json={
            "name": "Offline",
            "ram_limit_gb": 1,
            "cpu_limit_cores": 1,
            "storage_limit_gb": 1,
            "eligible_worker_ids": ["worker-1"],
            "failover_enabled": False,
        },
    )
    assert res.status_code == 400
