from tests.test_workouts import register


async def test_reading_history_and_deletion_are_scoped_to_device_owner(client):
    owner = await register(client)
    other = await register(client, "other@example.com")
    base = "/api/v1/sync"
    device = await client.post(
        f"{base}/devices", headers=owner, json={"model": "Watch", "serial_number": "123"}
    )
    device_id = device.json()["device_id"]
    reading_ids = []
    for day in (1, 2):
        saved = await client.post(
            f"{base}/reading", headers=owner,
            json={"device_id": device_id, "date_time": f"2026-11-0{day}T10:00:00Z", "steps": 0},
        )
        assert saved.status_code == 201
        reading_ids.append(saved.json()["reading_id"])

    listing = f"{base}/readings"
    assert (await client.get(listing)).status_code == 401
    assert (await client.get(listing, headers=other)).json() == {"items": [], "has_more": False}
    page = (await client.get(listing, headers=owner, params={"limit": 1})).json()
    assert page["has_more"]
    assert page["items"][0]["reading_id"] == reading_ids[1]
    assert page["items"][0]["device_model"] == "Watch"
    assert page["items"][0]["steps"] == 0
    next_page = (await client.get(listing, headers=owner, params={"limit": 1, "offset": 1})).json()
    assert not next_page["has_more"]
    assert next_page["items"][0]["reading_id"] == reading_ids[0]

    target = f"{listing}/{reading_ids[1]}"
    assert (await client.delete(target)).status_code == 401
    assert (await client.delete(target, headers=other)).status_code == 404
    assert (await client.delete(target, headers=owner)).status_code == 204
    assert (await client.delete(target, headers=owner)).status_code == 404
    remaining = (await client.get(listing, headers=owner)).json()
    assert [item["reading_id"] for item in remaining["items"]] == reading_ids[:1]
