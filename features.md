# EA FC 25 Market Price Scraper - Implemented Features

## Phase 1: Core Infrastructure ✅
*Completed: Week 1*

### Timing Variance Utilities
- `human_delay()` function adds ±15% variance to base delays
- `human_sleep()` wrapper for time.sleep with variance
- Random micro-pauses between requests (0.5-2s)

### Multi-tier Celery Queues
- Separate queues for each tier (tier_hot, tier_trending, tier_active, tier_normal, tier_cold)
- Verification queue for trade verification
- Maintenance queue for housekeeping tasks
- Queue routing configured in settings

### Database Models
- `TradeWatch` model for tracking trade listings
- `PlayerTier` model for storing player hotness scores and tier assignments
- `SessionUsage` model for managing multiple EA sessions
- `PlayerPriceHistory` with `is_verified` flag for trade verification

### Session Pool Manager
- Multi-session support for load distribution
- Session health monitoring
- Automatic cooldown periods
- Random session selection

## Phase 2: Priority System ✅
*Completed: Week 1-2*

### Trade Status Verification System
*Updated: Improved API efficiency*

- **Batch Trade Status API**: Check up to 20 trades in single API call
- **Proper endpoint usage**: `/trade/status/lite?tradeIds=id1,id2,id3`
- **Market Service**: Separated market/trading logic from auth domain
- **Efficient verification**: One API call instead of searching for each trade
- **Accurate status detection**: Properly identifies sold, expired, and active trades

### Hotness Calculator Service
Calculates player "hotness" scores based on four weighted factors:
- **Volatility (30%)**: Price standard deviation over 24 hours
- **Volume (30%)**: Number of completed trades  
- **Trend (20%)**: Sharp price increases/decreases
- **Event Relevance (20%)**: Rating, card type, league/nation popularity

#### Tier Assignment
| Tier | Hotness Score | Scrape Interval | Batch Size |
|------|--------------|-----------------|------------|
| HOT | 80-100 | 5 min | 10-15 |
| TRENDING | 60-79 | 10 min | 20-30 |
| ACTIVE | 40-59 | 20 min | 30-40 |
| NORMAL | 20-39 | 45 min | 40-50 |
| COLD | 0-19 | 2 hours | 50-60 |

### Dynamic Tier Assignment
- Automatic tier recalculation every hour
- Players promoted/demoted based on market activity
- Inactive players automatically set to COLD tier
- Special event detection for immediate recalculation

### Tier-Specific Celery Tasks

#### `scrape_tier_prices`
- Scrapes market prices for specific tier
- Human-like delays between requests
- Random batch size variations
- Creates trade watches for price verification
- Stores prices in PlayerPrice and history

#### `verify_pending_trades`
- Checks trades older than 5 minutes
- Verifies if trades completed (sold) or expired
- Updates verified prices in database
- Marks price history entries as verified

#### `recalculate_player_tiers`
- Runs hourly to update all player tiers
- Processes players with recent price activity
- Batch processing for performance

#### `cleanup_expired_trades`
- Removes old trade watch records
- Runs every 6 hours
- Keeps database clean

### Priority Queue Management
- `TierBasedPriorityQueue` service manages tier-based scraping
- Smart player selection based on last scraped time
- Randomized batch ordering to avoid patterns
- Configurable intervals and batch sizes per tier
- Automatic scrape timing based on tier intervals

### Management Commands
- `initialize_tiers`: Set up initial tier assignments
- `--recalculate` flag: Force recalculation of all tiers

## Anti-Detection Features

### Request Pattern Variations
- Randomized player search order within batches
- Variable batch sizes (e.g., 45-55 instead of fixed 50)
- Random micro-pauses between requests
- Occasional batch skipping with return later

### Human Behavior Simulation
- Base delay with ±15-20% variance
- Exponential backoff with jitter for retries
- Random session selection from pool
- Natural request timing patterns

## Data Quality Features

### Two-Phase Price Verification
1. **Phase 1**: Collect trade listings with IDs
   - Store top 5 cheapest listings
   - Track trade IDs for later verification
   
2. **Phase 2**: Verify completed trades
   - Check if trades still active after 5 minutes
   - Mark sold trades as verified prices
   - Update confidence based on verification

### Price Tracking
- Current price always reflects latest market data
- Historical prices stored with verification status
- Trade ID tracking for audit trail

## Monitoring & Observability

### Metrics Tracked
- Requests per minute/hour per session
- Success/failure rates
- Rate limit hits
- Price freshness
- Verified vs unverified prices
- Tier distribution

### Adaptive Behavior
- Automatic throttling on rate limit detection
- Session rotation on errors
- Circuit breaker pattern implementation
- Dynamic delay adjustments

## Technical Improvements

### Async/Await Pattern
- Proper Django ORM async handling with `sync_to_async`
- Concurrent task execution where possible
- Efficient database queries

### Code Organization
- Services layer for business logic
- Separate task modules for Celery
- Clean model separation
- Reusable utility functions
- Proper test structure with unit tests
- Utility scripts in `scripts/` folder

## Configuration

### Environment Variables
- Configurable rate limits per tier
- Adjustable delays and variance
- Session management parameters
- Circuit breaker thresholds

### Celery Beat Schedule
- Automated tier-based scraping
- Trade verification every 5 minutes
- Hourly tier recalculation
- Regular cleanup tasks

## Database Optimizations

### Indexes
- Player tier and hotness score indexing
- Trade watch status indexing
- Session health indexing
- Price history date indexing

### Query Optimization
- Batch operations for bulk updates
- Efficient aggregations for statistics
- Proper join strategies

## Phase 3: Anti-Detection System ✅
*Completed: Week 2*

### Request Pattern Randomization
- **RequestPatternRandomizer** class in `utils/timing.py`
- Variable batch sizes with ±20% variance
- Random micro-pauses between requests (0.5-2s)
- 5% chance to skip batches and return later
- Shuffle with locality groups (mimics human browsing)
- Burst pattern generation for human-like work sessions
- Multi-layered delay randomness (occasional distractions, breaks)

### Circuit Breaker Pattern
- **EACircuitBreaker** class in `utils/circuit_breaker.py`
- Three states: CLOSED (normal), OPEN (blocking), HALF_OPEN (testing)
- Automatic detection of:
  - Rate limit errors (429)
  - Timeout errors
  - CAPTCHA challenges
  - Session expiration
- Dynamic backoff based on error type:
  - CAPTCHA: 1 hour
  - Multiple rate limits: 10 minutes
  - Few rate limits: 5 minutes
- Circuit breaker manager for multiple endpoints
- Manual trip/reset capabilities

### Token Bucket Rate Limiter
- **DistributedTokenBucket** class in `utils/rate_limiter.py`
- Redis-based for distributed rate limiting
- Per-tier rate limits:
  - HOT: 20 req/min
  - TRENDING: 15 req/min
  - ACTIVE: 10 req/min
  - NORMAL: 8 req/min
  - COLD: 5 req/min
- Token refill based on elapsed time
- Async acquire/wait functionality
- Local cache fallback for Redis failures

### Adaptive Rate Limiting
- **AdaptiveRateLimiter** class adjusts limits dynamically
- Monitors success rates and rate limit hits
- Automatic throttling:
  - Decreases by 20% on high rate limit hits
  - Increases by 5% on sustained high success rates
- Metrics tracking per tier/session
- 5-minute adjustment intervals

### Enhanced Session Rotation
- **SessionPool** improvements in `utils/session_pool.py`
- Priority-based session allocation:
  - HIGH priority: Dedicated sessions for HOT tier
  - MEDIUM priority: Weighted random selection
  - LOW priority: Round-robin with randomness
- Session health monitoring and reporting
- Automatic load balancing across sessions
- Cooldown management:
  - Hourly rate limits (500 req/hour)
  - Consecutive request limits (100 req)
  - 15-minute cooldowns
- Force rotation capabilities
- Detailed health reports with metrics

### Session Management Features
- Dedicated sessions for high-priority (HOT) players
- Automatic session redistribution
- Session usage tracking with Redis cache
- Async session operations with Django ORM
- Configurable limits via environment variables

---

*Last Updated: Phase 3 Completion*
*Next: Phase 4 - Trade Verification Implementation*