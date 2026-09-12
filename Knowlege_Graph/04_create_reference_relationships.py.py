from neo4j import GraphDatabase
from dotenv import load_dotenv
import pandas as pd
import os

load_dotenv()

URI = os.getenv("NEO4J_URI")
USERNAME = os.getenv("NEO4J_USERNAME")
PASSWORD = os.getenv("NEO4J_PASSWORD")

CSV_FILE = "IS_Standards_Data\edges.csv"

driver = GraphDatabase.driver(
    URI,
    auth=(USERNAME, PASSWORD)
)


def create_reference_relationships(tx, rows):

    query = """
    UNWIND $rows AS row

    MATCH (citing:Standard {kys_id: row.citing_id})
    MATCH (cited:Standard {kys_id: row.cited_id})

    MERGE (citing)-[:REFERENCES]->(cited)
    """

    tx.run(query, rows=rows)


def main():

    df = pd.read_csv(CSV_FILE)

    print(f"Loaded {len(df)} reference records.")

    rows = []

    for _, row in df.iterrows():

        if pd.isna(row["citing_id"]) or pd.isna(row["cited_id"]):
            continue

        rows.append({
            "citing_id": int(row["citing_id"]),
            "cited_id": int(row["cited_id"])
        })

    print(f"Preparing {len(rows)} reference relationships...")

    batch_size = 1000

    with driver.session() as session:

        for i in range(0, len(rows), batch_size):

            batch = rows[i:i + batch_size]

            session.execute_write(
                create_reference_relationships,
                batch
            )

            print(
                f"Processed {min(i + batch_size, len(rows))}/{len(rows)}"
            )

    print("REFERENCES relationships created successfully!")


if __name__ == "__main__":

    try:
        main()

    finally:
        driver.close()