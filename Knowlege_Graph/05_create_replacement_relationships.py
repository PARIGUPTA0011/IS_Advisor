from neo4j import GraphDatabase
from dotenv import load_dotenv
import pandas as pd
import os

load_dotenv()

URI = os.getenv("NEO4J_URI")
USERNAME = os.getenv("NEO4J_USERNAME")
PASSWORD = os.getenv("NEO4J_PASSWORD")

CSV_FILE = "IS_Standards_Data\standards.csv"

driver = GraphDatabase.driver(
    URI,
    auth=(USERNAME, PASSWORD)
)


def create_replacement_relationships(tx, rows):

    query = """
    UNWIND $rows AS row

    MATCH (old:Standard {kys_id: row.old_id})
    MATCH (new:Standard {kys_id: row.new_id})

    MERGE (old)-[:REPLACED_BY]->(new)
    """

    tx.run(query, rows=rows)


def main():

    df = pd.read_csv(CSV_FILE)

    rows = []

    for _, row in df.iterrows():

        # We need both old and replacement IDs
        if pd.isna(row["kys_id"]) or pd.isna(row["replaced_by_id"]):
            continue

        try:
            old_id = int(row["kys_id"])
            new_id = int(row["replaced_by_id"])
        except (ValueError, TypeError):
            continue

        rows.append({
            "old_id": old_id,
            "new_id": new_id
        })

    print(f"Found {len(rows)} replacement records.")

    batch_size = 1000

    with driver.session() as session:

        for i in range(0, len(rows), batch_size):

            batch = rows[i:i + batch_size]

            session.execute_write(
                create_replacement_relationships,
                batch
            )

            print(
                f"Processed {min(i + batch_size, len(rows))}/{len(rows)}"
            )

    print("REPLACED_BY relationships created successfully!")


if __name__ == "__main__":

    try:
        main()

    finally:
        driver.close()