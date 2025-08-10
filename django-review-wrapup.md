### Django Review — Wrap-up (post third wave)

Final small deltas found. Edits below are minimal and targeted.

---

### 1) players fetch-all hits the wrong source/shape
- `players/api.py` calls EA `players.json` and pushes `items` into `bulk_upsert`, but `players.json` doesn’t expose the FUT `itemData` shape expected by the upsert. Use the FUT `defid` flow via `PlayerDataService` with X-UT-SID.

Edits:
```python
# players/api.py (imports)
from auth_api.services import FutClient  # if you want to validate SID presence

@router.post("/fetch-all")
async def fetch_all_players(request):
    try:
        sid = request.headers.get("x-ut-sid")
        if not sid:
            raise HttpError(400, "Missing X-UT-SID header")

        service = PlayerDataService(sid)
        result = await service.fetch_all_players()

        return {
            "success": True,
            "message": f"Fetched {result['total_players']} players",
            "meta": {"last_offset": result["last_offset"], "fetch_date": result["fetch_date"]},
        }
    except Exception as e:
        logger.error(f"Error fetching players: {e}")
        raise HttpError(500, f"An error occurred: {str(e)}")
```

Optionally remove the EA `players.json` fetch from this endpoint. Keep name updates via `PlayerDataService.update_player_names()` in a separate route/task.

---

### 2) Tests need sync with new schemas
- `club/tests/test_schemas.py` still asserts old keys.

Edits:
```python
# club/tests/test_schemas.py
# credits test → use new fields
response = CreditsResponse(**data)
self.assertIsNotNone(response.credits)
self.assertIsNotNone(response.unopened_packs)

# quick sell test → coins_earned
response = QuickSellResponse(**data)
self.assertIsNotNone(response.coins_earned)
self.assertIsNotNone(response.total_credits)

# also update fixtures as needed
# club/tests/fixtures/quick_sell_item.json
{
  "success": true,
  "coins_earned": 350,
  "total_credits": 123456,
  "message": "Item sold successfully"
}
```

- `market/tests/test_schemas.py` trade status expects old fields. Update to the simplified schema.

```python
# market/tests/test_schemas.py
response = TradeStatusResponse(**data)
self.assertTrue(hasattr(response, "trades"))
```

---

### 3) Optional minor polish
- `core.constants.get_base_headers` uses `referrer`; the HTTP header is historically `referer`. Consider including both or switching to `referer`.

```python
h = get_base_headers(...)
h["referer"] = h.pop("referrer", "https://www.ea.com/")
```

- Consider renaming `GET /api/club/players` → `GET /api/club/player-items` to avoid confusion with global `players/*` endpoints.

---

### Done criteria after this wrap-up
- `players/fetch-all` ingests real FUT `defid` data with `X-UT-SID`.
- Club/Market schema tests pass with updated fields/fixtures.
- Optional polish applied or tracked.


