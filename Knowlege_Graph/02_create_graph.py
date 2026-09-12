from neo4j import GraphDatabase
from dotenv import load_dotenv
import pandas as pd
import os

# Load environment variables
load_dotenv()

URI = os.getenv("NEO4J_URI")
USERNAME = os.getenv("NEO4J_USERNAME")
PASSWORD = os.getenv("NEO4J_PASSWORD")

# Path to cleaned standards data
CSV_FILE = "IS_Standards_Data\standards.csv"


# Connect to Neo4j
driver = GraphDatabase.driver(
    URI,
    auth=(USERNAME, PASSWORD)
)


def create_standard_nodes(tx, rows):

    query = """
    UNWIND $rows AS row

    MERGE (s:Standard {kys_id: row.kys_id})

    SET s.is_number = row.is_number,
        s.status = row.status,
        s.title_clean = row.title_clean,
        s.title = row.title,
        s.common_title = row.common_title,
        s.aspect = row.aspect,
        s.equivalence = row.equivalence,
        s.intl_equivalent = row.intl_equivalent,
        s.bilingual = row.bilingual,
        s.language = row.language,
        s.revisions = row.revisions,
        s.amendments_n = row.amendments_n,
        s.reaffirmed_year = row.reaffirmed_year,
        s.last_confirmed_year = row.last_confirmed_year,
        s.replaced_by_id = row.replaced_by_id,
        s.replaced_by_is = row.replaced_by_is,
        s.replacement_source = row.replacement_source,
        s.dept_code = row.dept_code,
        s.committee_code = row.committee_code,
        s.committee = row.committee,
        s.group = row.group,
        s.sub_group = row.sub_group,
        s.sub_sub_group = row.sub_sub_group,
        s.mandatory_cert = row.mandatory_cert,
        s.certification = row.certification,
        s.qco_status = row.qco_status,
        s.qco_date = row.qco_date,
        s.hs_codes = row.hs_codes,
        s.ministries = row.ministries,
        s.n_license = row.n_license,
        s.n_laboratory = row.n_laboratory,
        s.n_refers_to = row.n_refers_to,
        s.n_referred_by = row.n_referred_by
    """

    tx.run(query, rows=rows)


def main():

    # Read cleaned CSV
    df = pd.read_csv(CSV_FILE)

    print(f"Loaded {len(df)} standards from CSV.")

    rows = []

    for _, row in df.iterrows():

        if pd.isna(row["kys_id"]):
            continue

        data = {}

        for column in df.columns:

            value = row[column]

            # Convert pandas NaN to None
            if pd.isna(value):
                value = None

            data[column] = value

        # kys_id should be an integer
        data["kys_id"] = int(row["kys_id"])

        rows.append(data)

    # Send data to Neo4j in batches
    batch_size = 1000

    with driver.session() as session:

        for i in range(0, len(rows), batch_size):

            batch = rows[i:i + batch_size]

            session.execute_write(
                create_standard_nodes,
                batch
            )

            print(
                f"Loaded {min(i + batch_size, len(rows))}/{len(rows)} standards"
            )

    print("Standard nodes created successfully!")


if __name__ == "__main__":

    try:
        main()

    finally:
        driver.close()