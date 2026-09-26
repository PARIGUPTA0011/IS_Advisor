from neo4j import GraphDatabase
from dotenv import load_dotenv
import pandas as pd
import os

# Load environment variables
load_dotenv()

URI = os.getenv("NEO4J_URI")
USERNAME = os.getenv("NEO4J_USERNAME")
PASSWORD = os.getenv("NEO4J_PASSWORD")

# Clause 2 (Normative References) of each standard, exported by
# Semantic_Analysis/08_export_normative_refs.py. See
# Semantic_Analysis/data/NORMATIVE_REFS.md for how it was built.
CSV_FILE = os.path.join("Semantic_Analysis", "data", "normative_refs_edges.csv")

driver = GraphDatabase.driver(
    URI,
    auth=(USERNAME, PASSWORD)
)


def create_normative_relationships(tx, rows):

    # A separate relationship type rather than more REFERENCES edges: these
    # are stated by the standard itself, so queries can trust them without
    # the same_dept / confirmed_both_sides weighting the scraped edges need.
    query = """
    UNWIND $rows AS row

    MATCH (citing:Standard {kys_id: row.citing_id})
    MATCH (cited:Standard {kys_id: row.cited_id})

    MERGE (citing)-[r:NORMATIVELY_REFERENCES]->(cited)
    SET r.cited_as = row.cited_as,
        r.in_edges_csv = row.in_edges_csv
    """

    tx.run(query, rows=rows)


def main():

    df = pd.read_csv(CSV_FILE)

    print(f"Loaded {len(df)} normative reference records.")

    rows = []

    for _, row in df.iterrows():

        # Unresolved references (a family that only exists as parts, a
        # number not in the dataset) have no cited_id and are skipped.
        if pd.isna(row["citing_id"]) or pd.isna(row["cited_id"]):
            continue

        rows.append({
            "citing_id": int(row["citing_id"]),
            "cited_id": int(row["cited_id"]),
            "cited_as": row["cited_as"],
            "in_edges_csv": bool(row["in_edges_csv"]) if not pd.isna(row["in_edges_csv"]) else False,
        })

    print(f"Preparing {len(rows)} NORMATIVELY_REFERENCES relationships...")

    batch_size = 1000

    with driver.session() as session:

        for i in range(0, len(rows), batch_size):

            batch = rows[i:i + batch_size]

            session.execute_write(
                create_normative_relationships,
                batch
            )

            print(
                f"Processed {min(i + batch_size, len(rows))}/{len(rows)}"
            )

    print("NORMATIVELY_REFERENCES relationships created successfully!")


if __name__ == "__main__":

    try:
        main()

    finally:
        driver.close()
