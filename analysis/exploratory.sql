-- Exploratory Athena queries over the curated zone (Tier 1 — autonomous).
-- DEA-C01: D1/D2/D3. Cost note: Athena bills per TB scanned — always filter on partitions
-- (year/month/day) so you scan one partition, not the whole table.
--
-- Table name: the curated crawler (catalog_glue_stack.py) names the table after the curated
-- bucket, so it is NOT literally "curated". Run `SHOW TABLES IN dea_c01_lakehouse;` and swap the
-- real name in below. (As dea-c01-analyst, `amount` is column-masked and won't appear/aggregate.)

-- Revenue by product category for one day (partition-pruned, cheap).
SELECT category, COUNT(*) AS orders, ROUND(SUM(amount), 2) AS revenue
FROM dea_c01_lakehouse.curated
WHERE year = 2026 AND month = 6 AND day = 25
GROUP BY category
ORDER BY revenue DESC;

-- Enriched-schema example: order volume by country for one day.
SELECT country, COUNT(*) AS orders, ROUND(AVG(quantity), 2) AS avg_items
FROM dea_c01_lakehouse.curated
WHERE year = 2026 AND month = 6 AND day = 25
GROUP BY country
ORDER BY orders DESC;

-- Confirm partitions are registered (run MSCK REPAIR or a crawler if new ones are missing).
SHOW PARTITIONS dea_c01_lakehouse.curated;
