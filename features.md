# EA FC 25 Market Price Scraper - Features

## Rate Limits & Timeouts Configuration

### Base Configuration
- **EA API limit**: 50 requests/minute per session (BASE_RATE_LIMIT)
- **All limits are cross-related** - change BASE_RATE_LIMIT in `utils/rate_limit_config.py` and all adjust automatically

### HTTP Request Timeouts
- **Current**: 30 seconds timeout (httpx)
- **Recommended**: 10-15 seconds with separate connect/read timeouts

### Session Rate Limits  
- **Hourly limit**: 500 requests/hour (10x base rate - allows bursts while staying safe)
- **Consecutive limit**: 100 requests (2x base rate - ~2 minutes of continuous requests)
- **Cooldown**: 15 minutes when limits reached (mimics human breaks, prevents detection)
- **Why consecutive limit?**: Real users don't make 100+ requests without breaks; prevents bot detection

### Tier-Based Rate Limits (% of Base Rate)
| Tier | Requests/min | % of Base | Scan Window | Batch Size | Base Delay | Why This Rate |
|------|-------------|-----------|-------------|------------|------------|---------------|
| HOT | 20 | 40% | 5 min | 10-15 | 1.5s | Most valuable cards, aggressive but safe |
| TRENDING | 15 | 30% | 10 min | 20-30 | 2.0s | Rising cards, balanced approach |
| ACTIVE | 10 | 20% | 20 min | 30-40 | 3.0s | Moderate activity, conservative |
| NORMAL | 8 | 16% | 45 min | 40-50 | 3.75s | Low activity, minimal resources |
| COLD | 5 | 10% | 2 hours | 50-60 | 6.0s | Inactive cards, lowest priority |

### Circuit Breaker Thresholds
- **Failure threshold**: 3 consecutive failures
- **Timeout threshold**: 5 consecutive timeouts
- **Rate limit threshold**: 10 hits/hour (20% of base rate)
- **Recovery times**:
  - Default: 5 minutes
  - 3+ rate limits: 5 minutes
  - 5+ rate limits: 10 minutes
  - CAPTCHA: 1 hour

### Task Timeouts (Auto-calculated)
Based on batch size × base delay × 5x safety margin:
- **HOT**: ~90s (15 players × 1.5s × 5)
- **TRENDING**: ~180s (30 players × 2s × 5)
- **ACTIVE**: ~240s (40 players × 3s × 5)
- **NORMAL**: ~300s (50 players × 3.75s × 5)
- **COLD**: ~360s (60 players × 6s × 5)

---

## Core Features

### Player Tier System
Automatically categorizes players into 5 tiers based on market activity:
- **Hotness Score Calculation**: Volatility (30%), Volume (30%), Trend (20%), Event Relevance (20%)
- **Dynamic Assignment**: Hourly recalculation based on market data
- **Tier-Specific Scheduling**: Different scan intervals and batch sizes per tier

### Smart Price Verification
- **Two-Phase System**: Collect trade IDs → Verify after expiry
- **Batch API Calls**: Check up to 20 trades per request
- **Verified Pricing**: Only confirmed sold trades update current prices
- **Trade ID Optimization**: Skip processing if trade IDs already exist in database
- **Last Trade Check**: Check last trade ID first to skip entire pages efficiently

### Anti-Detection System
- **Request Randomization**: Variable delays, batch sizes, and ordering
- **Circuit Breaker**: Automatic backoff on errors/rate limits
- **Session Pool**: Multiple EA accounts with health monitoring
- **Adaptive Throttling**: Dynamic delay adjustments based on performance

### Task Deduplication
- **Queue Management**: Only keeps latest instance of each task
- **Running Task Cancellation**: Revokes outdated tasks automatically
- **Tier-Aware**: Separate deduplication for each player tier

### Monitoring & Observability
- **Prometheus Metrics**: Performance, risk, data quality, system health
- **Grafana Dashboards**: Real-time visualization and alerts
- **Structured Logging**: JSON formatted with error categorization
- **Alert Rules**: Error rates, rate limits, response times, stale prices

### Database Models
- **Player**: Core player data with ratings and attributes
- **PlayerTier**: Hotness scores and tier assignments
- **PlayerPrice**: Current market prices
- **PlayerPriceHistory**: Historical prices with verification status
- **TradeWatch**: Active trade tracking for verification
- **SessionUsage**: Multi-session management (external table)

### Celery Task Queue
- **Tier-based queues**: Separate priority queues per tier
- **Scheduled tasks**:
  - Price scraping (per tier schedule)
  - Trade verification (every 5 sec)
  - Tier recalculation (hourly)
  - Cleanup (every 6 hours)
  - Metrics update (every minute)

### API Integration
- **EA FUT API**: Player search with optimized single-page pagination
- **Trade Status API**: Batch trade verification
- **Session Management**: Automatic rotation and health checks
- **Pagination Optimization**: Reduced from 5 pages to 1 page with trade ID deduplication

### Session Resilience
- **Automatic Session Refresh**: Tasks automatically retry with fresh session on expiry
- **Max Retry Attempts**: Up to 3 attempts to get new session before failing
- **Session Isolation**: Each task gets fresh session from DB on retry
- **Circuit Breaker Integration**: New sessions update circuit breaker state

---

*Last Updated: After session refresh implementation*