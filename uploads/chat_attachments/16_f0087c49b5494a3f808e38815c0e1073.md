# PostgreSQL Database Inspection Report

**Database:** 101.37.209.117-pg  
**Datasource ID:** 1  
**Trigger:** cpu_usage=93.40 > 80 for 75s  
**Report Generated:** 2026-03-14 22:46:51 UTC

---

## 1. Executive Summary

| Metric | Value | Status |
|--------|-------|--------|
| **CPU Usage** | 93.4% | ⚠️ **CRITICAL** |
| **Active Connections** | 61 / 100 | ⚠️ **HIGH** |
| **Cache Hit Ratio** | 96.81% | ✅ **GOOD** |
| **Deadlocks** | 0 | ✅ **NORMAL** |
| **Load Average (1min)** | 12.70 | ⚠️ **HIGH** |
| **Database Size** | ~3.0 GB | ✅ **NORMAL** |

**Overall Health Status:** ⚠️ **DEGRADED** - High CPU utilization and connection pressure detected

---

## 2. Database Status Metrics

### Connection Overview
| Metric | Value |
|--------|-------|
| Active Connections | 61 |
| Total Connections | 100 |
| Idle Connections | ~39 |
| Connections Utilization | 61% |

### Transaction Statistics
| Metric | Value |
|--------|-------|
| Transactions Committed | 2,686,110 |
| Transactions Rolled Back | 12,427 |
| Rollback Rate | 0.46% |
| Deadlocks | 0 |
| Conflicts | 0 |

### Performance Indicators
| Metric | Value |
|--------|-------|
| Cache Hit Ratio | 96.81% |
| Blocks Read | 27,528,051 |
| Blocks Hit | 834,917,426 |
| Tuples Returned | 2,406,536,821 |
| Tuples Fetched | 1,009,404,083 |

---

## 3. OS-Level Metrics

### CPU & Load
| Metric | Value |
|--------|-------|
| Load Average (1min) | 12.70 |
| Load Average (5min) | 4.43 |
| Load Average (15min) | 4.17 |
| CPU Cores | 4 |
| **CPU Utilization** | **93.4%** ⚠️ |

### Memory Usage
| Metric | Value |
|--------|-------|
| Total Memory | 31,188 MB |
| Used Memory | 2,456 MB |
| Free Memory | 14,801 MB |
| Buff/Cache | 13,930 MB |
| Available | 28,121 MB |
| Memory Utilization | 7.9% ✅ |

### Disk Usage
| Filesystem | Size | Used | Avail | Use% |
|------------|------|------|-------|------|
| /dev/vda3 | 40G | 8.8G | 29G | 24% |
| /dev/nvme0n1 | 879G | 5.1G | 830G | 1% |

---

## 4. Active Sessions Analysis

### Connection State Distribution
| State | Count | Percentage |
|-------|-------|------------|
| Active | ~35 | 57% |
| Idle | ~15 | 25% |
| Idle in Transaction | ~8 | 13% |
| Other | ~3 | 5% |

### Wait Events Detected
| Wait Event Type | Count | Impact |
|-----------------|-------|--------|
| Lock (transactionid) | ~20 | 🔴 **HIGH** |
| Lock (tuple) | ~8 | 🟡 **MEDIUM** |
| LWLock (BufferMapping, ProcArray, WALWrite) | ~5 | 🟡 **MEDIUM** |
| IO (DataFileWrite, WalWrite) | ~3 | 🟡 **MEDIUM** |
| ClientRead | ~10 | 🟢 **LOW** |

### Top Blocking Queries
```sql
-- Multiple sessions waiting on:
UPDATE warehouse SET w_ytd = w_ytd + $1 WHERE w_id = $2
UPDATE district SET d_ytd = d_ytd + $1 WHERE d_w_id = $2 AND d_id = $3
SELECT d_tax, d_next_o_id FROM district WHERE d_w_id = $1 AND d_id = $2 FOR UPDATE
SELECT no_o_id FROM new_order WHERE no_w_id = $1 AND no_d_id = $2 ORDER BY no_o_id ASC
```

---

## 5. Slow Query Analysis

### Top 10 Slow Queries by Total Time

| Rank | Query Pattern | Calls | Total Time (s) | Mean Time (ms) | Max Time (ms) | Cache Hit % |
|------|--------------|-------|----------------|----------------|---------------|-------------|
| 1 | `UPDATE warehouse SET w_ytd = w_ytd + $1 WHERE w_id = $2` | 1,181,576 | 40,755.82 | 34.49 | 518.35 | 99.90% |
| 2 | `SELECT d_tax, d_next_o_id FROM district WHERE d_w_id = $1 AND d_id = $2 FOR UPDATE` | 1,237,014 | 32,743.87 | 26.47 | 492.92 | 99.99% |
| 3 | `UPDATE district SET d_ytd = d_ytd + $1 WHERE d_w_id = $2 AND d_id = $3` | 1,181,567 | 20,943.95 | 17.73 | 449.55 | 99.88% |
| 4 | `SELECT no_o_id FROM new_order WHERE no_w_id = $1 AND no_d_id = $2 ORDER BY no_o_id ASC` | 477,432 | 6,977.33 | 14.61 | 1,633.06 | 98.48% |
| 5 | `SELECT COUNT(DISTINCT s_i_id) FROM stock, order_line WHERE...` | 109,297 | 740.43 | 6.77 | 212.65 | 99.89% |
| 6 | `UPDATE order_line SET ol_delivery_d = $1 WHERE ol_w_id = $2...` | 128,742 | 82.47 | 0.64 | 187.06 | 99.84% |

### Query Performance Issues Identified
- **High-frequency UPDATE operations** on `warehouse` and `district` tables causing lock contention
- **FOR UPDATE locks** on `district` table creating transaction bottlenecks
- **ORDER BY operations** on `new_order` table with high execution times
- **Complex JOIN queries** between `stock` and `order_line` tables

---

## 6. Table Statistics

### Top Tables by Size
| Schema | Table | Total Size | Table Size | Index Size | Rows | Dead Tuples |
|--------|-------|------------|------------|------------|------|-------------|
| public | order_line | 1,970 MB | 1,459 MB | 511 MB | 15,356,207 | 1,288,769 |
| public | stock | 425 MB | 403 MB | 21 MB | 1,000,000 | 12,355,408 |
| public | customer | 231 MB | 206 MB | 25 MB | 300,000 | 1,310,141 |
| public | oorder | 203 MB | 92 MB | 112 MB | 1,536,824 | 128,739 |
| public | history | 131 MB | 131 MB | 0 bytes | 1,481,402 | 0 |
| public | new_order | 87 MB | 51 MB | 36 MB | 1,326,824 | 0 |

### Table Activity (Last Hour)
| Table | Inserts | Updates | Deletes | Live Tuples |
|-------|---------|---------|---------|-------------|
| order_line | 12,887,69 | 0 | 0 | 15,144,912 |
| stock | 12,355,408 | 0 | 0 | 999,631 |
| customer | 1,310,141 | 0 | 0 | 300,003 |
| oorder | 128,739 | 0 | 0 | 1,524,448 |

---

## 7. Index Usage Statistics

### Most Used Indexes
| Schema | Table | Index Name | Scans | Tuples Read | Tuples Fetched | Size | Status |
|--------|-------|------------|-------|-------------|----------------|------|--------|
| public | stock | stock_pkey | 46,562,810 | 47,336,582 | 46,562,810 | 21 MB | ACTIVE |
| public | item | item_pkey | 12,369,344 | 12,356,920 | 12,356,920 | 2,208 kB | ACTIVE |
| public | new_order | new_order_pkey | 606,151 | 2,281,608,777 | 490,017,935 | 36 MB | ACTIVE |
| public | order_line | order_line_pkey | 476,407 | 25,535,069 | 25,523,093 | 511 MB | ACTIVE |
| public | customer | idx_customer_name | 774,896 | 2,417,027 | 2,328,787 | 16 MB | ACTIVE |

### Index Efficiency
- All indexes showing **ACTIVE** status
- No unused indexes detected
- Primary key indexes receiving highest scan counts
- `new_order_pkey` showing high tuple read-to-fetch ratio (indicating potential optimization opportunity)

---

## 8. Vacuum & Maintenance Status

### Tables Requiring Maintenance
| Schema | Table | Live Tuples | Dead Tuples | Dead % | Priority | Last Vacuum | Last Autovacuum |
|--------|-------|-------------|-------------|--------|----------|-------------|-----------------|
| public | customer | 300,003 | 37,921 | **12.64%** | 🔴 HIGH | - | 2026-03-14 14:24:03 |
| public | stock | 999,631 | 70,953 | **7.10%** | 🟡 MEDIUM | - | 2026-03-14 14:46:05 |
| public | district | 100 | 1,689 | **1,689.00%** | 🟡 MEDIUM | - | 2026-03-14 14:46:51 |
| public | warehouse | 10 | 973 | **9,730.00%** | 🟢 LOW | - | 2026-03-14 14:46:46 |
| public | order_line | 15,147,294 | 7,443 | 0.05% | 🟡 MEDIUM | - | 2026-03-14 14:21:08 |

### Maintenance Recommendations
- ⚠️ **customer** table: 12.64% dead tuples - Schedule VACUUM ANALYZE
- ⚠️ **stock** table: 7.10% dead tuples - Monitor closely
- ℹ️ **district/warehouse**: High dead tuple % but low absolute counts (small tables)

---

## 9. Historical Trend Analysis (Last 20 Snapshots)

### CPU Usage Trend
| Time Range | Min CPU | Max CPU | Avg CPU | Trend |
|------------|---------|---------|---------|-------|
| Last 5 min | 0.0% | 98.5% | 47.2% | 📈 **Increasing** |
| Last 15 min | 0.0% | 100.0% | 52.8% | 📈 **Volatile** |
| Last 30 min | 0.0% | 100.0% | 48.5% | 📈 **Spiking** |

### Connection Count Trend
| Time Range | Min | Max | Avg | Trend |
|------------|-----|-----|-----|-------|
| Last 5 min | 40 | 61 | 48 | 📈 **Increasing** |
| Last 15 min | 1 | 61 | 35 | 📈 **Volatile** |

### Throughput Metrics
| Metric | Min | Max | Avg | Current |
|--------|-----|-----|-----|---------|
| QPS | 22 | 1,487,592 | 523,847 | 1,278,833 |
| TPS | 0.27 | 1,119.93 | 623.45 | 929.39 |

### Key Observations from History
1. **CPU spikes correlate with connection surges** - Pattern shows CPU jumping from ~0% to 90%+ when connections increase from 1 to 40+
2. **Load test pattern detected** - Regular cycles of low activity (1 connection, ~22 QPS) followed by high activity (40-61 connections, 1M+ QPS)
3. **Sustained high CPU** - Current 93.4% CPU has been sustained for 75+ seconds based on trigger
4. **Memory stable** - Memory usage remains consistent at ~7.5-8.0% throughout all load patterns

---

## 10. Critical Findings & Recommendations

### 🔴 Critical Issues

| Priority | Issue | Impact | Recommendation |
|----------|-------|--------|----------------|
| **P1** | CPU at 93.4% for 75+ seconds | Performance degradation, potential timeouts | Investigate top queries causing CPU spike; consider query optimization or scaling |
| **P1** | High lock contention on warehouse/district tables | Transaction blocking, increased latency | Review application transaction isolation levels; consider partitioning hot tables |
| **P2** | 61 active connections (61% utilization) | Connection pool exhaustion risk | Increase max_connections or implement connection pooling (PgBouncer) |
| **P2** | customer table at 12.64% dead tuples | Table bloat, slower queries | Schedule immediate VACUUM ANALYZE on customer table |

### 🟡 Warnings

| Issue | Impact | Recommendation |
|-------|--------|----------------|
| Load average 12.70 (3.2x CPU cores) | System overload | Monitor for sustained high load; consider horizontal scaling |
| Multiple idle-in-transaction connections | Resource waste, potential locks | Review application connection handling; implement statement timeouts |
| High-frequency UPDATE operations | Lock contention | Consider batch updates or optimistic locking patterns |

### 🟢 Positive Observations

- ✅ Cache hit ratio excellent at 96.81%
- ✅ No deadlocks detected
- ✅ No transaction conflicts
- ✅ All indexes active and being used
- ✅ Disk usage low (24% on data volume)
- ✅ Memory utilization healthy at 7.9%

---

## 11. Action Items

### Immediate Actions (Next 1-2 hours)
1. [ ] **Analyze top 3 slow queries** - Review execution plans for warehouse/district UPDATE statements
2. [ ] **Check application connection pool settings** - Verify proper connection release
3. [ ] **Run VACUUM ANALYZE on customer table** - Address 12.64% dead tuple ratio
4. [ ] **Monitor lock wait events** - Set up alerts for lock wait times > 1 second

### Short-term Actions (Next 24-48 hours)
1. [ ] **Review TPC-C benchmark configuration** - Pattern suggests load testing; optimize if production
2. [ ] **Consider connection pooling** - Implement PgBouncer if not already in use
3. [ ] **Analyze index efficiency on new_order** - High tuple read-to-fetch ratio
4. [ ] **Set up CPU alerting thresholds** - Alert at 80% for 60 seconds

### Long-term Actions (Next 1-2 weeks)
1. [ ] **Evaluate horizontal scaling options** - Read replicas for SELECT-heavy workload
2. [ ] **Review table partitioning strategy** - Consider partitioning order_line and stock tables
3. [ ] **Implement query performance monitoring** - Deploy pg_stat_statements analysis dashboard
4. [ ] **Capacity planning review** - Based on 1M+ QPS peaks, evaluate infrastructure needs

---

## 12. Appendix: System Configuration

### Database Configuration
- **PostgreSQL Version:** Not specified in metrics
- **max_connections:** 100 (inferred from metrics)
- **shared_buffers:** Not specified
- **work_mem:** Not specified

### Host Configuration
- **CPU Cores:** 4
- **Total Memory:** 31,188 MB (~31 GB)
- **OS:** Linux (inferred from metrics format)
- **Uptime:** 1 day, 12:49

### Storage Configuration
- **Data Directory:** /dev/nvme0n1 (879 GB, 1% used)
- **System Directory:** /dev/vda3 (40 GB, 24% used)
- **Docker Overlay:** Multiple overlay filesystems detected

---

**Report End**  
*Generated by DBGuard AI Inspection System*