-- Simple query to count keyword usage
--
-- Parameters:
--     year                -- year
--     month               -- month
--     day                 -- day
--
-- Usage:
--     hive -f count_keyword_usage.hql \
--         -d year=2017 \
--         -d month=01 \
--         -d day=08

SELECT
    csr.source AS `source`,
    asyn AS `keyword`,
    COUNT(1) AS searches
FROM
    wmf_raw.CirrusSearchRequestSet csr
    LATERAL VIEW EXPLODE(requests) req AS areq
    LATERAL VIEW EXPLODE(split(areq.payload["syntax"], ",")) syn AS asyn
WHERE
    year = ${year} AND month = ${month} AND day = ${day}
    AND areq.queryType = 'full_text'
GROUP BY csr.source, asyn
ORDER BY `keyword`, `source`
LIMIT 500;
