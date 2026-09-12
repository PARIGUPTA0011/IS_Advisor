from neo4j import GraphDatabase
from dotenv import load_dotenv
import os

load_dotenv()

URI = os.getenv("NEO4J_URI")
USERNAME = os.getenv("NEO4J_USERNAME")
PASSWORD = os.getenv("NEO4J_PASSWORD")

driver = GraphDatabase.driver(
    URI,
    auth=(USERNAME, PASSWORD)
)


def create_certification_relationships(tx):

    query = """
    MERGE (c:Certification {name: "Mandatory Certification"})
    WITH c

    MATCH (s:Standard)
    WHERE s.mandatory_cert = true

    MERGE (s)-[:REQUIRES_CERTIFICATION]->(c)

    RETURN count(s) AS connected_standards
    """

    result = tx.run(query)

    return result.single()["connected_standards"]


def main():

    with driver.session() as session:

        count = session.execute_write(
            create_certification_relationships
        )

        print(
            f"Connected {count} standards to Mandatory Certification."
        )

    print("Certification relationships created successfully!")


if __name__ == "__main__":

    try:
        main()

    finally:
        driver.close()