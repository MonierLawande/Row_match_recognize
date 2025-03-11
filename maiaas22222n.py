"""
Main Application (main.py):
Coordinates all the steps:

Reads the SQL query (as a string),
Parses it to a parse tree,
Transforms the MATCH_RECOGNIZE clause to a canonical representation,
Loads a sample input DataFrame,
Calls the engine's match_recognize function, and
Outputs the resulting DataFrame. Example:

"""


from utils.parser_utils import parse_input
from transformations.match_recognize_transformer import MatchRecognizeTransformer
from engine.match_recognize import match_recognize
import pandas as pd

def main():
    # Example SQL query with MATCH_RECOGNIZE clause
    sql_query = """SELECT * FROM orders
    MATCH_RECOGNIZE (
        PARTITION BY custkey
        ORDER BY orderdate
        MEASURES
            A.totalprice AS starting_price,
            LAST(B.totalprice) AS bottom_price,
            LAST(U.totalprice) AS top_price
        ONE ROW PER MATCH
        AFTER MATCH SKIP PAST LAST ROW
        PATTERN (PERMUTE(A, B, C) D+)
        SUBSET U = (B, C)
        DEFINE
            A AS totalprice > 10,
            B AS totalprice < PREV(totalprice),
            C AS totalprice = PREV(totalprice),
            D AS totalprice > PREV(totalprice)
    );"""

    # Parse the query
    tree, parser = parse_input(sql_query)

    # Transform the MATCH_RECOGNIZE clause
    transformer = MatchRecognizeTransformer()
    transformer.visit(tree)
    canonical_query = transformer.get_canonical()

    print("Canonical MATCH_RECOGNIZE Representation:")
    print(canonical_query)

    # Load or create your input DataFrame (for example purposes)
    df = pd.read_csv("orders_sample.csv")  # Your input DataFrame

    # Apply MATCH_RECOGNIZE on the DataFrame
    output_df = match_recognize(df, canonical_query)
    print("Output DataFrame:")
    print(output_df)

if __name__ == "__main__":
    main()
