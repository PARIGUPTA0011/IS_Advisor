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


def create_relationships(tx, rows):

    query = """
    UNWIND $rows AS row

    MATCH (s:Standard {kys_id: row.kys_id})

    MERGE (d:Department {code: row.dept_code})

    MERGE (c:Committee {code: row.committee_code})
    SET c.name = row.committee

    MERGE (s)-[:BELONGS_TO]->(d)

    MERGE (s)-[:MAINTAINED_BY]->(c)
    """

    tx.run(query, rows=rows)


def main():

    df = pd.read_csv(CSV_FILE)

    rows = []

    for _, row in df.iterrows():

        if pd.isna(row["kys_id"]):
            continue

        # We need department and committee information
        if pd.isna(row["dept_code"]) or pd.isna(row["committee_code"]):
            continue

        rows.append({
            "kys_id": int(row["kys_id"]),
            "dept_code": str(row["dept_code"]).strip(),
            "committee_code": str(row["committee_code"]).strip(),
            "committee": str(row["committee"]).strip()
        })

    print(f"Preparing {len(rows)} relationships...")

    batch_size = 1000

    with driver.session() as session:

        for i in range(0, len(rows), batch_size):

            batch = rows[i:i + batch_size]

            session.execute_write(
                create_relationships,
                batch
            )

            print(
                f"Processed {min(i + batch_size, len(rows))}/{len(rows)}"
            )

    print("Department and Committee relationships created successfully!")


if __name__ == "__main__":

    try:
        main()

    finally:
        driver.close()