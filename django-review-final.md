### Django Review — Final sweep (post second wave)

Most core issues look resolved: async correctness, router↔client alignment, schema updates, and dependency cleanup are in good shape. Below are small remaining cleanups and optional refinements.

---

### Must-do cleanups

1) Update club tests to new schema fields
- We renamed `QuickSellResponse.credits_earned` → `coins_earned`.
- Adjust assertions in `club/tests/test_schemas.py`.

```python
# club/tests/test_schemas.py
self.assertIsNotNone(response.coins_earned)  # replace credits_earned
```

2) Consider renaming `GET /api/club/players` → `GET /api/club/player-items`
- Reduces confusion with global `players/*` endpoints. Implementation can stay the same; only route path and docs change.

```python
# club/api.py
@router.get("/player-items", response=PlayerListResponse)
async def get_club_player_items(request):
    ...  # same body as get_club_players
```

3) Docs drift
- README endpoint docs likely drifted (trade-status schema simplified to `trades`, credits fields, quick-sell response field rename). Update examples to match current responses.

---

### Nice-to-have refinements

1) Consistent item name handling in club player mapping
- `name="Player"` is a placeholder. If you want names when available, try stitching with `players` table (by `asset_id`) and fall back to placeholder.

2) Headers polish
- `core.constants.get_base_headers` uses `referrer` key; many servers check `referer`. Consider adding both or switching to `referer`.

```python
headers["referer"] = headers.pop("referrer", "https://www.ea.com/")
```

3) Thin helpers in client (only if useful)
- You already added `get_trade_status_by_ids`. If it proves unused, remove later to keep surface minimal.

4) Endpoint naming consistency
- `send-to-tradepile` vs `tradepile` usage is consistent now; keep this capitalization/hyphenation convention across routes for clarity.

---

### Quick verification checklist
- Club quick sell returns `coins_earned` and tests updated accordingly.
- Market trade-status returns `{ trades: [...] }` and README reflects it.
- No DRF remnants in settings or deps (confirmed).
- No `requests`/`time.sleep` on request path (confirmed).


