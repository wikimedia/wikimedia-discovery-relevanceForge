
select distinct tss.event_searchSessionId, tss.event_articleId, tss.event_query
  from log.TestSearchSatisfaction2_14098806 tss
  join (select event_searchSessionId
          from log.TestSearchSatisfaction2_14098806
         where timestamp between {date_start} and {date_end}
           and wiki = '{wiki}'
           and event_action = 'visitPage'
         group by event_searchSessionId
         order by rand()
         limit {limit}
       ) sessions
    on sessions.event_searchSessionId = tss.event_searchSessionId
 where tss.timestamp between {date_start} and {date_end}
   and (tss.event_action in ('visitPage', 'searchResultPage'));

