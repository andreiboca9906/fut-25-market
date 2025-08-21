## Rules

1. Do not add bs comments everywhere. Use it very very very strictly when required
2. Respect the code style. We use snake_case here, do not use other cases even when http responses are in that format
3. Make updates with as minimal changes as possible
4. Use `uv run ...` to run all commands. DO NOT USE `python` directly!
5. When working with Django ORM in async contexts, ALWAYS use `sync_to_async` from `asgiref.sync`. Django ORM operations are synchronous and must be wrapped:
   - WRONG: `player = Player.objects.first()`
   - CORRECT: `player = await sync_to_async(Player.objects.first)()`
   - For chained operations: `await sync_to_async(lambda: Model.objects.filter(...).first())()`
6. Update `features.md` after implementing any new feature, fix, or significant change. Keep it current with all implemented functionality. Always keep it lean tho - no fluff or bs!
7. Update `plan.md` when any changes or fixes affect the planned architecture or implementation strategy. This ensures future phases follow the updated approach. Always keep it lean tho - no fluff or bs!
8. Keep functions in their proper domains:
   - Auth services: Authentication, login, session management
   - Market services: Trading, auctions, trade status, market operations  
   - Player services: Player data, pricing, tiers, hotness calculations
