### Django Project Review and Remediation Plan

#### Verdict
Not yet aligned with standard Django best practices. Primary issues: inconsistent async usage, API/router/service contract drift, schema mismatches, duplicate models, and tests that validate fixtures instead of live code paths.

---

### What’s in the repo (at a glance)
- Django 5.x, ASGI enabled, Ninja mounted at `/api/` via `fut_market/api/__init__.py`.
- Apps: `auth_api`, `market`, `club`, `players`, `core`.
- HTTP client/service: `auth_api/services.py::FutClient` (async `httpx`), plus `players/services.py` (sync `requests`).
- Schemas with Pydantic in each app; dataclasses in `core/fut_models/*`.

---

### Key Findings
- Async/sync mixing
  - `players/api.py` uses Django ORM directly inside `async def` handlers and uses `transaction.atomic()` inside async context.
  - `players/services.py` uses `requests` and `time.sleep` (sync) in a project otherwise trending async.

- API/router/service contract drift
  - `market/api.py` calls `FutClient.search_market`, `buy_now(trade_id, price)`, `get_trade_status(trade_ids)` which do not exist (or have different signatures). `FutClient` exposes `search_players(params)`, `buy_now(trade_id)`, `get_trade_status()` (no args).
  - `club/api.py` calls `get_credits()` and then accesses fields that don’t exist (`credits.total`, `credits.untradeable`). Service returns `CreditsResponse(credits, unopened_packs, total_points)`.
  - `club/api.py` calls nonexistent client methods (`get_club_players()`, `get_squads()`; actual methods are `get_player_list()`, `get_squad_list()`). Also mismatched names like `send_to_tradepile` vs `send_to_trade_pile`, `quick_sell` vs `quick_sell_item`.
  - Routers sometimes do `item.model_dump()` on plain `dataclass` objects or on dicts.

- Data model duplication and drift
  - Duplicate `PlayerSearchParameters`: in `core/fut_models/auction.py` and `core/fut_models/search.py`. `FutClient` uses the one in `search.py`.
  - Multiple schema shapes for similar concepts (e.g., market `AuctionInfo` vs dataclass `AuctionInfo`) without mapping functions.

- Bugs
  - `players/api.py:get_players_summary` does not call the manager method (missing `()`).

- Tests
  - Current tests validate Pydantic schemas against static fixtures only; they do not exercise routers/services integration.

- Dependencies and settings
  - `djangorestframework` installed but unused.
  - Both `httpx` and `requests` installed; should standardize on `httpx`.
  - Ruff ignores `ASYNC` rule, allowing bad async patterns to slip.
  - `CORS_ALLOW_ALL_ORIGINS=True` (OK for dev; ensure production override).

---

### Target Architecture (concise)
- Keep Django Ninja with `async def` handlers.
- All external I/O async via `httpx.AsyncClient`.
- All Django ORM access inside async handlers wrapped with `asgiref.sync.sync_to_async` or moved to sync helpers.
- Single source of truth for domain dataclasses (`core/fut_models/*`) and explicit mapping functions to Pydantic schemas.
- `FutClient` methods are the canonical contract. Routers adapt to schemas.

---

### Phase-wise Remediation Plan

#### Phase 1 — Contract and schema alignment (routers ↔ services)
1) Align `market/api.py` with `FutClient`
   - Use `search_players` instead of `search_market` and map results properly.
   - Use `buy_now(trade_id)` (no price arg) and derive `success/bid_amount` from result.
   - Replace `get_trade_status(data.trade_ids)` with a helper wrapper (see Phase 3) or fetch+filter.

   Edits (snippets):
   ```python
   # market/api.py
   from dataclasses import asdict

   # search_market
   result = await client.search_players(fut_criteria)
   page_size = len(result.auctions)
   total_pages = (result.total_results + page_size - 1) // page_size if page_size else 0
   return SearchResult(
       total_pages=total_pages,
       total_results=result.total_results,
       page=result.page,
       page_size=page_size,
       items=[asdict(a) for a in result.auctions],
   )

   # buy_now
   res = await client.buy_now(trade_id)
   credits = await client.get_credits()
   return BidResponse(
       success=res.success,
       message="Purchase successful" if res.success else "Purchase failed",
       trade_id=trade_id,
       bid_amount=res.current_bid,
       credits=credits.credits,
   )

   # get_trade_status
   status = await client.get_trade_status()  # Phase 3 will add an optional filter helper
   # map to TradeStatusResponse schema or adjust schema in Phase 2/4
   ```

2) Align `club/api.py` with `FutClient`
   - Fix method names: `get_player_list()`, `get_squad_list()`, `quick_sell_item()`, `send_to_trade_pile()`.
   - Fix credits mapping to use fields `credits`, `unopened_packs` (update schema, see Phase 2).

   Edits (snippets):
   ```python
   # club/api.py
   credits = await client.get_credits()
   return CreditsResponse(credits=credits.credits, unopened_packs=credits.unopened_packs, total_points=credits.total_points)

   # get players
   players_resp = await client.get_player_list()
   # map players_resp.players to your PlayerItem schema

   # quick sell
   result = await client.quick_sell_item(item_id)

   # send to trade pile
   success = await client.send_to_trade_pile(item_id)
   ```

3) Align `auth_api/api.py` with `FutClient.login` output
   - Update Pydantic `LoginResponse` schema to what the client returns (session/nucleus/persona, optional dob/email/country).
   - Return only available fields.

   Edits (snippets):
   ```python
   # auth_api/schemas.py
   class LoginResponse(BaseModel):
       session_id: str
       nucleus_id: str
       persona_id: str
       dob: str | None = None
       email: str | None = None
       country: str | None = None
   ```

4) Remove duplicate model
   - Delete `PlayerSearchParameters` from `core/fut_models/auction.py` and import from `core/fut_models/search.py` everywhere.

   Edits (snippets):
   ```python
   # core/fut_models/auction.py
   # remove the duplicate PlayerSearchParameters class entirely
   ```

Deliverable: all routers call existing `FutClient` methods; schemas reflect actual data; no `.model_dump()` on dataclasses.

---

#### Phase 2 — Async correctness and ORM boundaries
1) Wrap ORM calls inside async handlers with `sync_to_async`
   - `players/api.py`: `bulk_upsert`, `filter(...).update(...)`, list/queryset access, summary stats, history creation.

   Edits (snippets):
   ```python
   from asgiref.sync import sync_to_async

   success = await sync_to_async(Player.objects.bulk_upsert)(players_data.get("items", []))

   updated = await sync_to_async(Player.objects.filter(asset_id=asset_id).update)(
       first_name=first_name, last_name=last_name
   )

   players = await sync_to_async(list)(
       Player.objects.filter(rating__gt=80).order_by("-rating")[:limit].values(
           "id", "asset_id", "rating", "preferred_position", "first_name", "last_name"
       )
   )

   summary = await sync_to_async(Player.objects.get_summary_stats)()

   @router.post("/price/update")
   async def update_player_price(...):
       @transaction.atomic
       def _do_update():
           PlayerPrice.objects.update_price(player_id, platform, price, currency)
           PlayerPriceHistory.objects.create(player_id=player_id, platform=platform, price=price, currency=currency)
       await sync_to_async(_do_update)()
   ```

2) Convert `players/services.py` to async
   - Replace `requests` with `httpx.AsyncClient`, `time.sleep` with `asyncio.sleep`.
   - Wrap DB upserts with `sync_to_async`.

   Edits (snippets):
   ```python
   import asyncio, httpx
   from asgiref.sync import sync_to_async

   async def _rate_limit(...):
       ...
       await asyncio.sleep(60 - elapsed + 1)

   async def fetch_players_batch(...):
       async with httpx.AsyncClient(headers=self.headers, timeout=30) as client:
           r = await client.get(self.FUT_API_URL, params=params)
           r.raise_for_status()
           return r.json().get("itemData")

   async def fetch_all_players(...):
       ...
       if len(batch_for_db) >= 500:
           ok = await sync_to_async(Player.objects.bulk_upsert)(batch_for_db)
   ```

3) Fix bug in `players/api.py:get_players_summary`
   - Call the function: `Player.objects.get_summary_stats()` (wrapped with `sync_to_async` as above).

Deliverable: no `SynchronousOnlyOperation` under ASGI; external calls are non-blocking.

---

#### Phase 3 — Service client cohesion and small helpers
1) Add thin wrappers to `FutClient` to smooth router needs (optional but keeps routers simple)
   - `search_market(params)` → call `search_players(params)`.
   - `get_trade_status_by_ids(trade_ids: list[int])` → call `get_trade_status()` then filter.

   Edits (snippets):
   ```python
   # auth_api/services.py (inside FutClient)
   async def search_market(self, params):
       return await self.search_players(params)

   async def get_trade_status_by_ids(self, trade_ids: list[int]):
       full = await self.get_trade_status()
       full.trades = [t for t in full.trades if t.trade_id in trade_ids]
       return full
   ```

2) Fix naming consistency in `club/api.py`
   - Use `send_to_trade_pile`, `quick_sell_item` as per service.

Deliverable: routers read cleanly and call coherent client APIs.

---

#### Phase 4 — Schema and model consolidation
1) Consolidate search parameters
   - Remove duplicate `PlayerSearchParameters` from `core/fut_models/auction.py`.
   - Ensure all imports use `core/fut_models/search.py`.

2) Normalize market schemas
   - Either (A) adapt Pydantic schemas to reflect dataclasses from `core/fut_models/*`, or (B) add explicit mapping functions per endpoint.
   - Recommendation: keep Pydantic schemas minimal and map from dataclasses via `asdict`.

3) Update `club/schemas.py::CreditsResponse`
   - Reflect actual fields: `credits: int`, `unopened_packs: int`, `total_points: int | None`.

Deliverable: one set of domain models; schemas match runtime data.

---

#### Phase 5 — Dependencies, settings, and linting
1) Dependencies (in `pyproject.toml`)
   - Remove `djangorestframework` if unused.
   - Remove `requests` after Phase 2.

2) Ruff
   - Remove `"ASYNC"` from ignore list to catch bad async usage.

3) Settings
   - Keep `CORS_ALLOW_ALL_ORIGINS=True` for dev; add production override.
   - Ensure `ALLOWED_HOSTS` populated in env.

Deliverable: lean deps, async issues caught during CI.

---

#### Phase 6 — Tests and CI
1) Add router-service integration tests using Django test client (ASGI)
   - Mock `httpx.AsyncClient` with `respx`.
   - Exercise endpoints end-to-end.

2) Update existing schema tests to new shapes where changed (e.g., credits).

3) Add tests that would fail on:
   - Dataclass `.model_dump()` misuse.
   - Calling nonexistent service methods.
   - Async ORM usage without `sync_to_async`.

Deliverable: tests validate the real code paths, not only fixtures.

---

#### Phase 7 — Operational polish (optional but recommended)
1) Session persistence
   - Replace in-memory `SessionManager` with DB or cache-backed storage (Redis via Django cache).

2) Background jobs
   - Offload long-running crawls (player fetch, price history) to Celery/Huey; trigger via Ninja endpoints.

3) Exception handling
   - Add centralized exception handlers for `FutError` subclasses to consistent HTTP responses.

Deliverable: production-friendly behavior under load and multi-worker setups.

---

### File-by-file Quick Checklist
- `market/api.py`
  - Replace `search_market` call with `search_players` and map output via `asdict`.
  - Use `buy_now(trade_id)` (no price arg).
  - Replace `get_trade_status(trade_ids)` with `get_trade_status()` or new helper.

- `club/api.py`
  - Fix credits mapping and method names: `get_player_list`, `get_squad_list`, `quick_sell_item`, `send_to_trade_pile`.

- `auth_api/schemas.py`
  - Update `LoginResponse` fields to what `FutClient.login` returns.

- `players/api.py`
  - Wrap all ORM calls with `sync_to_async`; fix `get_players_summary()` call; wrap `transaction.atomic` work.

- `players/services.py`
  - Convert to async `httpx`, replace `time.sleep` with `asyncio.sleep`, wrap upserts.

- `core/fut_models/auction.py`
  - Remove duplicate `PlayerSearchParameters`.

- `pyproject.toml`
  - Remove `djangorestframework`, `requests` after Phase 2; un-ignore Ruff `ASYNC`.

---

### Notes on TimescaleDB doc (`migrate_to_django.md`)
- Replace “Use drizzle” with Django migrations using `RunSQL` for `CREATE EXTENSION timescaledb;` and `create_hypertable(...)`.
- Provide Django migration examples instead of raw operational SQL in docs, so `manage.py migrate` sets up the DB.

---

### Done Criteria per Phase
- Phase 1: All routers import valid client methods; schemas compile; server boots; OpenAPI docs load.
- Phase 2: No sync-in-async errors under load; endpoints fast; no `time.sleep`/`requests` in request path.
- Phase 3: Router logic simplified; small helpers in client pass unit tests.
- Phase 4: No duplicated models; one set of search params; credits schema reflects service.
- Phase 5: `uv sync` produces lean env; Ruff flags async issues in CI.
- Phase 6: Integration tests green; schema tests updated.
- Phase 7: Sessions survive multi-worker runs; long jobs offloaded; consistent error responses.


