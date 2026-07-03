SELECT *
FROM data
MATCH_RECOGNIZE (

            ORDER BY seq_id
            MEASURES
                FIRST(A.seq_id) AS start_row,
                LAST(B.seq_id) AS end_row,
                COUNT(*) AS match_length,
                COUNT(A.seq_id) AS a_count,
                COUNT(B.seq_id) AS b_count
            ONE ROW PER MATCH
            PATTERN (A+ B+)
            DEFINE
                A AS category = 'A',
                B AS category = 'B'
        
)
