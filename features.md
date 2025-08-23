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

## Phase 4: Smart Trade Verification System ✅
*Completed*

### Model Updates
- **TradeWatch**: Added `expires_at` field to track auction expiry times
- **PlayerPriceHistory**: Already has `trade_id` and `is_verified` fields
- **AuctionInfo**: Removed duplicate `time_remaining` field, using only `expires`

### Enhanced Scraping with Pagination
- **Smart Pagination**: Scrapes up to 5 pages per player search
- **Centralized Scan Windows**: Configured in `core.constants.TIER_SCAN_WINDOWS`
  - HOT: 5 min, TRENDING: 10 min, ACTIVE: 20 min
  - NORMAL: 45 min, COLD: 2 hours
- **Comprehensive Trade Collection**: Tracks ALL auctions expiring before next scan (not just cheapest)
- **Efficient API Usage**: Stops pagination when no relevant auctions found

### Improved Trade Verification
- **Expiry-Based Verification**: Checks trades after `expires_at` timestamp
- **Batch Processing**: Verifies up to 60 trades per run (20 per API call)
- **Simple Price Tracking**: Current price = last verified sold price
- **Verified Price History**: Records all sold trades with `is_verified=True`
- **Enhanced Logging**: Detailed [TRADE_VERIFY] logs for debugging and monitoring
- **Error Handling**: Graceful handling of session errors and database save failures

### API Efficiency Improvements
- **Paginated Search**: Collects more market data per player
- **Batch Trade Status**: Checks up to 20 trades in single API call
- **Time-based Filtering**: Only tracks relevant auctions
- **Human-like Delays**: Between pages and requests
- **Cleaner Variable Naming**: `buyable_auctions` instead of misleading `cheapest_auctions`

### Task Schedule Optimization
- All tier scraping tasks run at appropriate intervals
- Trade verification runs every 5 minutes
- Cleanup runs every 6 hours
- Fully automated workflow

## Phase 5: Monitoring & Observability ✅
*Completed*

### Prometheus Metrics Collection
- **Performance Metrics**: Request counts, response times, active tasks
- **Risk Metrics**: Rate limits, session expirations, errors, circuit breakers
- **Data Quality Metrics**: Price freshness, verified trades ratio, stale prices
- **System Health Metrics**: Active sessions, queue depth, worker utilization
- **Custom Registry**: Dedicated Prometheus metrics registry for scraper

### Grafana Dashboards
- **Real-time Monitoring**: Request rates, response time P95, error rates
- **Risk Indicators**: Rate limit hits, circuit breaker status
- **Data Quality**: Price freshness gauges, verification ratios
- **System Health**: Queue depths, active scrapers, worker status
- **Auto-provisioning**: Pre-configured dashboards and datasources

### Adaptive Throttling
- **Dynamic Delay Adjustment**: Based on risk score and performance metrics
  - High risk (>70): 1.5x delays
  - Medium risk (>50): 1.2x delays  
  - Low risk (<20): 0.95x delays
- **Adaptive Batch Sizes**: Reduces batches under throttling
- **Cooldown Manager**: Dynamic cooldowns based on session health
- **Redis-based History**: Tracks adjustment factors over time

### Structured Logging
- **JSON Formatting**: Python JSON logger for structured logs
- **Rotating Files**: Separate logs for general and errors
- **Error Categorization**: Automatic error type classification
- **Context Tracking**: Session IDs, tiers, player IDs in logs

### Enhanced Celery Tasks
- **Monitored Task Base**: Automatic metrics recording
- **Request Timing**: Records duration of each scrape
- **Error Tracking**: Categorizes and records all errors
- **Active Task Counting**: Tracks concurrent tasks per tier
- **Metrics Integration**: All tasks report to Prometheus

### Docker Compose Setup
- **Prometheus**: Time-series metrics storage (port 9090)
- **Grafana**: Visualization and alerting (port 8040)
- **Network Integration**: Shares fut25_network with main app
- **Data Persistence**: Volumes for metrics and dashboards

### Alert Rules
- **High Error Rate**: >10% errors for 5 minutes
- **Rate Limit Exceeded**: >10 hits per session per hour
- **Low Success Rate**: <80% success for 10 minutes
- **High Response Time**: P99 >5 seconds
- **Circuit Breaker Open**: Immediate alert
- **Stale Prices**: >2 hours old

### Monitoring Features
- **Metrics Endpoint**: `/metrics/` for Prometheus scraping
- **Periodic Metrics Update**: Every minute via Celery beat
- **Environment Configuration**: Adaptive throttle settings
- **Start Script**: `start_monitoring.sh` for easy deployment

### Integrated Circuit Breaker
- **Metrics-Based Decisions**: Uses real-time Prometheus metrics instead of local counters
- **Global Coordination**: All instances share circuit state via Redis
- **Configurable Thresholds**: 
  - Error rate > 50% opens circuit
  - Rate limit hits > 10/hour opens circuit
  - Success rate < 70% opens circuit
  - Response time > 5s opens circuit
- **CIRCUIT_BREAKER_ENABLED**: Environment flag to enable/disable feature
- **Manual Controls**: Force open/close circuits via manager
- **Health Reporting**: Circuit status visible in monitoring dashboards

## Phase 6: Task Deduplication System ✅
*Completed*

### Celery Task Deduplication
- **DeduplicatedTask Base Class**: Custom Celery task class for automatic deduplication
- **Queue Deduplication**: Only keeps latest instance of each task type in queue
- **Running Task Cancellation**: Automatically revokes running tasks when new instance is queued
- **Tier-Aware Deduplication**: Different dedup keys for tier-based tasks (e.g., HOT vs TRENDING)
- **Redis-Based Locks**: Uses cache for distributed lock management with 2-hour TTL

### Deduplication Features
- **Before Start Hook**: Checks if task should run or be skipped
- **After Return Hook**: Cleans up locks after task completion
- **Apply Async Override**: Manages queue deduplication on task submission
- **Automatic Revocation**: Uses Celery control commands to cancel tasks
- **Detailed Logging**: Tracks all deduplication decisions

### Applied to All Tasks
- `scrape_market_prices`: Full market scan deduplication
- `scrape_tier_prices`: Per-tier deduplication (HOT, TRENDING, etc.)
- `verify_pending_trades`: Single instance verification
- `recalculate_player_tiers`: Prevents duplicate recalculations
- `cleanup_expired_trades`: Single cleanup task
- `update_metrics`: Prevents metric update overlap

### Benefits
- **Prevents Queue Buildup**: Keeps only latest task when backpressure occurs
- **Stops Redundant Work**: Cancels old tasks still retrying on expired sessions
- **Efficient Resource Usage**: No duplicate processing of same data
- **Maintains Fresh Data**: Always runs latest task with most recent parameters

---

*Last Updated: Phase 6 - Task Deduplication System*