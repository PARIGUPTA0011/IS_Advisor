# Knowledge Graph — IS-Advisor

## Overview

The Knowledge Graph is the **relationship and validation layer** of IS-Advisor. It uses **Neo4j** to represent Indian Standards and their relationships.

The graph helps IS-Advisor determine:

* Which standards reference other standards
* Which standards have been replaced
* Whether a standard is current or withdrawn
* Which department and committee maintain a standard
* Whether a standard requires mandatory certification

Semantic similarity/recommendation will be handled separately using embeddings. The Knowledge Graph is used for **relationship-based reasoning and validation**.

---

## Data Used

### `cleaned_standards.csv`

Contains information about individual Indian Standards.

Important columns:

| Column            | Description                        |
| ----------------- | ---------------------------------- |
| `kys_id`          | Unique ID of the standard          |
| `is_number`       | Indian Standard number             |
| `status`          | Current/withdrawn status           |
| `title`           | Standard title                     |
| `aspect`          | Standard aspect/category           |
| `language`        | Language of the standard           |
| `revisions`       | Number of revisions                |
| `amendments_n`    | Number of amendments               |
| `reaffirmed_year` | Reaffirmation year                 |
| `replaced_by_id`  | ID of replacement standard         |
| `replaced_by_is`  | Replacement standard number        |
| `dept_code`       | Department code                    |
| `committee_code`  | Committee code                     |
| `committee`       | Committee name                     |
| `mandatory_cert`  | Whether certification is mandatory |
| `certification`   | Certification information          |
| `qco_status`      | QCO status                         |
| `qco_date`        | QCO date                           |
| `hs_codes`        | Associated HS codes                |
| `ministries`      | Associated ministries              |

There are **35,524 standards** in the dataset.

### `cleaned_edges.csv`

Contains relationships between standards.

Important columns:

| Column                 | Description                                            |
| ---------------------- | ------------------------------------------------------ |
| `citing_id`            | ID of the standard making the reference                |
| `citing_is`            | Standard making the reference                          |
| `cited_id`             | ID of the referenced standard                          |
| `cited_is`             | Referenced standard                                    |
| `cited_title`          | Title of referenced standard                           |
| `cited_status`         | Status of referenced standard                          |
| `cited_replaced_by_id` | Replacement ID                                         |
| `cited_replaced_by_is` | Replacement standard                                   |
| `same_dept`            | Whether both belong to the same department             |
| `confirmed_both_sides` | Whether the relationship was confirmed from both sides |

---

## Graph Structure

The MVP contains four types of nodes:

```text
Standard
Department
Committee
Certification
```

Relationships:

```text
(Standard)-[:REFERENCES]->(Standard)

(Standard)-[:REPLACED_BY]->(Standard)

(Standard)-[:BELONGS_TO]->(Department)

(Standard)-[:MAINTAINED_BY]->(Committee)

(Standard)-[:REQUIRES_CERTIFICATION]->(Certification)
```

Example:

```text
IS 6893 (Part 7):1990
        |
        | REFERENCES
        v
IS 2324 (Part 2):1985
        |
        | REPLACED_BY
        v
Replacement Standard
```

Standard information such as `status`, `year`, `language`, `amendments_n`, etc. is stored as **properties of the Standard node**, rather than separate nodes.

---

## Files

### `01_test_connection.py`

Tests the connection between Python and the Neo4j database using credentials stored in `.env`.

Run:

```bash
python knowledge_graph/01_test_connection.py
```

---

### `02_create_graph.py`

Reads `cleaned_standards.csv` and creates all `Standard` nodes in Neo4j along with their properties.

Creates:

```text
(:Standard)
```

---

### `03_create_relationships.py`

Creates `Department` and `Committee` nodes and connects them to standards.

Creates:

```text
(Standard)-[:BELONGS_TO]->(Department)

(Standard)-[:MAINTAINED_BY]->(Committee)
```

---

### `04_create_reference_relationships.py`

Reads `cleaned_edges.csv` and creates relationships between standards using `citing_id` and `cited_id`.

Creates:

```text
(Standard)-[:REFERENCES]->(Standard)
```

---

### `05_create_replacement_relationships.py`

Uses `replaced_by_id` from `cleaned_standards.csv` to connect withdrawn/older standards to their replacement standards.

Creates:

```text
(Standard)-[:REPLACED_BY]->(Standard)
```

---

### `06_create_certification_relationships.py`

Creates the `Mandatory Certification` node and connects standards where `mandatory_cert = true`.

Creates:

```text
(Standard)-[:REQUIRES_CERTIFICATION]->(Certification)
```

Currently, **725 standards** are connected to mandatory certification.

---

## Environment

Neo4j credentials are stored in `.env`:

```text
NEO4J_URI=your_neo4j_uri
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password
```

Install dependencies:

```bash
pip install neo4j pandas python-dotenv
```

---

## Basic Verification

Count all standards:

```cypher
MATCH (s:Standard)
RETURN count(s);
```

View the relationships of a particular standard:

```cypher
MATCH (s:Standard)
WHERE s.is_number = "IS 6893 (Part 7):1990"
OPTIONAL MATCH (s)-[r]->(connected)
RETURN s, r, connected;
```

Example multi-hop query for procurement validation:

```cypher
MATCH (a:Standard)-[:REFERENCES]->(b:Standard)-[:REPLACED_BY]->(c:Standard)
WHERE b.status = "withdrawn"
RETURN a.is_number, b.is_number, c.is_number
LIMIT 20;
```

This allows IS-Advisor to identify cases where a standard references a **withdrawn standard and trace its replacement**.
