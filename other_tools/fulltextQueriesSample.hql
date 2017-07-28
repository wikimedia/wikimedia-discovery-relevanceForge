-- Random fulltext queries sample
--
-- Useful to extract a sample query set of fulltext queries.
--
-- We use query sets that include a near_match, which are likely run
-- when the user hit enter on the top right search box on the desktop
-- site. If the near_match query set includes a full_text query then
-- it's probable that the user is redirected to a search results page.
-- Query sets that do not include a full_text are likely "I feel lucky"
-- because they should have matched to the near_match, the user is then
-- redirected to the target page without seeing search results page.
--
-- We can't really use full_text directly since the WikipediaApp (and others)
-- sends partial queries with partial words (search type ahead) which are
-- completely useless for measuring fulltext queries performances.
--
-- Poor man bot exclusion:
-- To avoid including too many automata queries we accept only one query
-- per ip-day. IPs that generate more than 30 queries per day are excluded
-- (mostly web crawlers like yahoo, microsoft, google and baidu). Not using
-- useragent here because some highrates bots do not provide meaningful ua.
-- Drawback is that we will exclude queries from users behind proxies used
-- by mobile browsers (Opera Mini w/ spreadtrum, Blackberry...)
-- cf: http://www.operasoftware.com/press/releases/mobile/opera-to-supply-its-mobile-browser-solution-to-spreadtrum
--
-- Random sample of 1000 queries that return more than 500 results
-- on enwiki over one week and where the user is presented a search
-- results page.
--
-- Usage:
--     hive -f fulltextQueriesSample.hql

USE wmf_raw;

-- TODO: find a more convenient way to deal with time period...
SET year_min=2016;
SET year_max=2016;
SET month_min=1;
SET month_max=1;
SET day_min=25;
SET day_max=31;

SET min_res=500;
SET wiki='enwiki';
SET index='enwiki_content';
SET multi_word_regex='\\S\\s+\\S';
SET single_word_regex='^\\S+$';
SET query_regex=${hiveconf:multi_word_regex};

SELECT q FROM (
    SELECT
        -- keep only one query at random per ip/day
        FIRST_VALUE(areq.query) OVER (
            PARTITION BY csr.ip, csr.day
            ORDER BY RAND()
        ) AS q,
        csr.ip AS ip,
        -- count the number of queries per day for one IP
        COUNT(csr.ip) OVER (
            PARTITION BY csr.ip, csr.day
        ) AS q_by_day
    FROM
        CirrusSearchRequestSet csr
        -- Explode the requests array so we can extract the
        -- last full_text query
        LATERAL VIEW EXPLODE(requests) req AS areq
    WHERE
        year >= ${hiveconf:year_min} AND year <= ${hiveconf:year_max}
        AND month >= ${hiveconf:month_min} AND month <= ${hiveconf:month_max}
        AND day >= ${hiveconf:day_min} and day <= ${hiveconf:day_max}

        -- When the user hit enter it generates a near_match query first.
        AND csr.requests[0].queryType = 'near_match'

        -- Filter the full_text query with more than 500 results
        AND areq.queryType = 'full_text'
        AND areq.hitstotal > ${hiveconf:min_res}

        -- Make sure we extract only enwiki_content
        AND SIZE(areq.indices) == 1
        AND areq.indices[0] = ${hiveconf:index}
        AND wikiid=${hiveconf:wiki}

        AND areq.query RLIKE ${hiveconf:query_regex}

        -- TODO: make sure we don't get a did you mean
        -- rewritten query.
) queries
WHERE
    queries.q_by_day < 30
-- Various stuff stolen from https://www.joefkelley.com/?p=736
DISTRIBUTE BY RAND()
SORT BY RAND()
LIMIT 1000;
