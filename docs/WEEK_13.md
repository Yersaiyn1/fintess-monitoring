# Week 13 improvements

## Device readings

1. In **Activity → Device readings**, add a device if needed and select **Enter reading**.
2. Select your device, fill in the measurements, and select **Save reading**. **Cancel** clears the draft and closes the form.
3. Open **View saved readings** or go to **History → Device readings**. The section includes manual readings and readings from synced or imported devices. It starts with the newest 10 readings. Select **Show more readings** to see older entries.
4. Select **Delete reading**, then **Confirm delete** to remove a saved entry. **Cancel** closes the confirmation. Dashboard and Goals recalculate step and calorie totals when they next fetch activity data, according to their existing aggregation rules.

The **Workouts** filters apply to workout sessions. Device readings have their own list.

## API

| Method and path | Behavior |
| --- | --- |
| `POST /api/v1/sync/reading` | Saves a reading for a device owned by the signed-in patient. |
| `GET /api/v1/sync/readings?limit=10&offset=0` | Returns `items` and `has_more`. Each item contains its ID, device model, timestamp, and nullable measurements. Readings are ordered by timestamp and then ID, both descending. The limit is 1–100. |
| `DELETE /api/v1/sync/readings/{reading_id}` | Returns `204` after deletion or `404` when the reading is missing or belongs to another patient. |

Both new endpoints require patient authentication and use the existing devices and readings tables. No database migration is required.

## UI verification

- In dark mode, check the Profile avatar and Save changes button, Add Device fields, the Dashboard import button, and manually typed and autofilled login credentials.
- In Goals, check seven date labels and compare a day with zero steps and a day with recorded steps. The plot uses a fixed-height grid area so percentage-based bars have a height to resolve against.
- In Goals, open **Adjust your targets** and check that **Save targets** and the expand/collapse icon are readable in both themes.
- At phone widths, check that the Profile avatar stays circular, workout timestamps wrap within their rows, and both date filters can open a native date picker and display a selected value.
- Enter a reading and cancel, then open the form again and verify the measurements are cleared. Save a new reading and verify it appears in History. Cancel deletion, then confirm it and verify the entry disappears and remains absent after reload.
