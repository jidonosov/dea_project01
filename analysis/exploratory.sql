-- Exploratory Athena queries over the curated zone (Tier 1 — autonomous).
-- DEA-C01: D1/D2/D3. Cost note: Athena bills per TB scanned — always filter on partitions
-- (year/month/day) so you scan one partition, not the whole table.

-- Row count by category for one day (partition-pruned, cheap).
SELECT category, COUNT(*) AS n, ROUND(SUM(amount), 2) AS total
FROM dea_c01_lakehouse.curated
WHERE year = 2026 AND month = 6 AND day = 25
GROUP BY category
ORDER BY total DESC;

-- Confirm partitions are registered (run MSCK REPAIR or a crawler if new ones are missing).
SHOW PARTITIONS dea_c01_lakehouse.curated;
