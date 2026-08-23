from neo4j import GraphDatabase

from research_assistant.models import Triple


class Neo4jGraphStore:
    def __init__(self, uri: str, user: str, password: str) -> None:
        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def clear(self) -> None:
        with self._driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")

    def add_triple(self, subject: str, relation: str, object: str, source_url: str) -> None:
        with self._driver.session() as session:
            session.run(
                "MERGE (a:Entity {name: $subject}) "
                "MERGE (b:Entity {name: $object}) "
                "MERGE (a)-[r:RELATION {type: $relation}]->(b) "
                "SET r.source_url = $source_url",
                subject=subject, object=object, relation=relation, source_url=source_url,
            )

    def get_all_facts(self) -> list[Triple]:
        with self._driver.session() as session:
            result = session.run(
                "MATCH (a:Entity)-[r:RELATION]->(b:Entity) "
                "RETURN a.name AS subject, r.type AS relation, "
                "b.name AS object, r.source_url AS source_url"
            )
            return [Triple(**record.data()) for record in result]

    def close(self) -> None:
        self._driver.close()
