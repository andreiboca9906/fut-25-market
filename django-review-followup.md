### Django Review — Follow-up (post-fix audit)

Your fixes significantly improved async correctness and router ↔ service alignment. Below are the remaining concrete issues and cleanups, with exact edits. Also included is a duplicate/unnecessary endpoints pass (players-first rule).

---

### Remaining Issues (with precise edits)

1) Auth enum conversion bug (runtime AttributeError)
- `LoginDetails` expects `Platform` and `AppVersion` enums, but strings are passed from request.

```python
# auth_api/api.py (imports)
from core.constants import Platform, AppVersion

# inside login() and login_with_2fa(), where LoginDetails is constructed
login_details = LoginDetails(
    email=data.email,
    password=data.password,
    platform=Platform(data.platform),
    app_version=AppVersion(data.app_version),
    secret_answer=data.secret_answer,
)
```

Also normalize the request default to match the enum value:

```python
# auth_api/schemas.py
class LoginRequest(BaseModel):
    ...
    app_version: str = "25.1.0"

class LoginWith2FARequest(BaseModel):
    ...
    app_version: str = "25.1.0"
```

2) Wrong field used in quick sell response
- Service returns `QuickSellResult.coins_earned` but router reads `credits_earned`.

```python
# club/api.py (quick_sell_item)
return QuickSellResponse(
    success=result.success,
    credits_earned=result.coins_earned,  # fix
    total_credits=credits.credits,
    message="Item sold successfully" if result.success else "Quick sell failed",
)
```

3) Incorrect API endpoint for club items
- `core.constants.API_ENDPOINTS["club_items"]` points to `/club/tradepile` (wrong). Should be `/club`.

```python
# core/constants.py
API_ENDPOINTS = {
    ...
    "club_items": "/club",  # fix from "/club/tradepile"
}
```

4) Market search page default can produce negative offset
- `SearchCriteria.page` defaults to `0`, but service computes `start=(page-1)*50`.

```python
# market/schemas.py
class SearchCriteria(BaseModel):
    ...
    page: int = 1  # fix default

# market/api.py (before building PlayerSearchParameters)
page = max(1, criteria.page)
fut_criteria = PlayerSearchParameters(
    page=page,
    ...
)
```

5) Watchlist/tradepile item_data mapping mismatch
- EA payload keys are camelCase (e.g., `assetId`, `resourceId`, `discardValue`), but `ItemData` schema expects snake_case. Passing the dict directly will mis-parse.

Add a tiny mapper and use it in both endpoints:

```python
# market/api.py (top-level helper)
def _map_item_data(d: dict) -> ItemData:
    return ItemData(
        id=d.get("id", 0),
        timestamp=d.get("timestamp", 0),
        formation=d.get("formation", ""),
        untradeable=d.get("untradeable", False),
        asset_id=d.get("assetId", 0),
        rating=d.get("rating", 0),
        item_type=d.get("itemType", ""),
        resource_id=d.get("resourceId", 0),
        owners=d.get("owners", 0),
        discard_value=d.get("discardValue", 0),
        item_state=d.get("itemState", ""),
        card_subtype_id=d.get("cardsubtypeid", d.get("cardSubTypeId", 0)),
        rare_flag=d.get("rareflag", 0),
    )

# get_watchlist()
item_data=_map_item_data(item.item_data if isinstance(item.item_data, dict) else asdict(item.item_data))

# get_tradepile()
item_data=_map_item_data(item.item_data if isinstance(item.item_data, dict) else asdict(item.item_data))
```

6) Remove unused DRF app from settings
- DRF was removed from dependencies, but `rest_framework` is still in `INSTALLED_APPS`.

```python
# fut_market/settings.py
INSTALLED_APPS = [
    ...
    # "rest_framework",  # remove
    "ninja",
    ...
]
```

7) Trade status schema shape inconsistency (cleanup)
- Router returns `trades` but fills other fields with placeholders. Simplify the schema to the actual shape you return, or fully map to the EA response.

Option A (simplify Pydantic model):
```python
# market/schemas.py
class TradeStatusResponse(BaseModel):
    trades: List[TradeStatus]
```

Option B (fully populate all fields): map real values from service/API instead of zeros/empties.

8) Optional: remove alias in service
- `FutClient.search_market()` is now just an alias; since routers use `search_players`, consider removing the alias to avoid API bloat.

```python
# auth_api/services.py
# remove search_market; keep search_players only
```

9) Optional: validate `players` batch endpoint usefulness
- `/players/fetch-batch` passes `page/page_size` to EA `players.json`; if that endpoint ignores params, remove this API to prevent confusion. Keep `/players/fetch-all` as the canonical import.

---

### Duplicates/Unnecessary Endpoints (players-first rule)
- No strict duplicates found across apps. Concepts overlap but serve different domains:
  - `players/*` → DB-backed player catalog and pricing endpoints.
  - `club/*` → account-scoped club inventory, squads, credits.
  - `market/*` → market-facing actions/watchlists/tradepile.

Actions:
- Keep `players/*` as canonical for player entities and pricing.
- To avoid confusion, consider renaming `GET /club/players` to `GET /club/player-items` (these are “club items of type player”, not the global players table).
- Remove `FutClient.search_market` alias as noted.
- If `/players/fetch-batch` is not truly supported upstream, remove it.

---

### Quick QA checklist after applying edits
- Auth login works with enum conversion; no `AttributeError` on `.value`.
- Club quick sell returns `credits_earned` properly.
- Club items endpoint returns data (not empty) after correcting `/club` path.
- Market search honors `page>=1`.
- Watchlist/tradepile endpoints successfully validate `ItemData` with mapped keys.
- Server runs without DRF installed; no import errors.


