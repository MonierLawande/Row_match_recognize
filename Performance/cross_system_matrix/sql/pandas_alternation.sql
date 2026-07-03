SELECT *
FROM data
MATCH_RECOGNIZE (

            ORDER BY seq_id
            MEASURES
                FIRST(A.seq_id) AS start_row,
                LAST(D.seq_id) AS end_row,
                COUNT(*) AS match_length
            ONE ROW PER MATCH
            PATTERN (A (B|C)+ D)
            DEFINE
                A AS category = 'A',
                B AS category = 'B',
                C AS category = 'C',
                D AS category = 'D'
        
)
