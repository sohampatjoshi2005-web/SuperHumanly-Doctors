import networkx as nx
from typing import Dict, List, Any, Tuple
from sqlalchemy import select
from app.db import get_session
from app.db_models import Encounter, Customer
import json
import logging

logger = logging.getLogger(__name__)

class ClinicalGraphService:
    @staticmethod
    def build_clinic_graph(clinic_id: str) -> Dict[str, Any]:
        """
        Builds a co-occurrence graph of clinical entities for a specific clinic.
        """
        G = nx.Graph()
        
        with get_session() as session:
            # Get all encounters for patients in this clinic
            statement = select(Encounter).join(Customer).where(Customer.clinic_id == clinic_id)
            encounters = session.exec(statement).all()
            
            for encounter in encounters:
                entities = []
                
                # 1. Add Diagnosis as a node
                if encounter.diagnosis:
                    entities.append(("diagnosis", encounter.diagnosis))
                
                # 2. Add Medicines as nodes
                if encounter.prescription:
                    # We assume prescription is stored as a list of dicts in JSON format in the DB
                    # or it's a string that we might need to parse.
                    # Based on previous work, it's likely a JSON-serialized list.
                    try:
                        rx_list = encounter.prescription
                        if isinstance(rx_list, str):
                            rx_list = json.loads(rx_list)
                        
                        if isinstance(rx_list, list):
                            for rx in rx_list:
                                if isinstance(rx, dict) and "name" in rx:
                                    entities.append(("medicine", rx["name"]))
                    except:
                        pass
                
                # 3. Add Risk Indicators
                if encounter.risk_indicators:
                    try:
                        risks = encounter.risk_indicators
                        if isinstance(risks, str):
                            risks = json.loads(risks)
                        
                        if isinstance(risks, list):
                            for risk in risks:
                                if isinstance(risk, dict) and "indicator" in risk:
                                    entities.append(("risk", risk["indicator"]))
                    except:
                        pass

                # Add nodes and edges (fully connected clique for each encounter)
                for i in range(len(entities)):
                    type_i, name_i = entities[i]
                    node_id = f"{type_i}:{name_i}"
                    
                    if not G.has_node(node_id):
                        G.add_node(node_id, label=name_i, type=type_i, count=1)
                    else:
                        G.nodes[node_id]['count'] += 1
                        
                    for j in range(i + 1, len(entities)):
                        type_j, name_j = entities[j]
                        node_id_j = f"{type_j}:{name_j}"
                        
                        if not G.has_node(node_id_j):
                            G.add_node(node_id_j, label=name_j, type=type_j, count=0)
                            
                        if G.has_edge(node_id, node_id_j):
                            G[node_id][node_id_j]['weight'] += 1
                        else:
                            G.add_edge(node_id, node_id_j, weight=1)

        # Convert to D3 format
        nodes = []
        for n, d in G.nodes(data=True):
            nodes.append({
                "id": n,
                "label": d["label"],
                "type": d["type"],
                "val": d["count"]
            })
            
        links = []
        for u, v, d in G.edges(data=True):
            links.append({
                "source": u,
                "target": v,
                "weight": d["weight"]
            })
            
        return {"nodes": nodes, "links": links}

    @staticmethod
    def get_clinical_insights(clinic_id: str) -> Dict[str, Any]:
        """
        Calculates centrality and community clusters for a clinic.
        """
        graph_data = ClinicalGraphService.build_clinic_graph(clinic_id)
        
        G = nx.Graph()
        for link in graph_data["links"]:
            G.add_edge(link["source"], link["target"], weight=link["weight"])
            
        if G.number_of_nodes() == 0:
            return {"clusters": [], "central_nodes": []}

        # 1. PageRank for centrality
        pagerank = nx.pagerank(G, weight='weight')
        central_nodes = sorted(pagerank.items(), key=lambda x: x[1], reverse=True)[:5]
        
        # 2. Community detection
        from networkx.algorithms import community
        communities = community.greedy_modularity_communities(G)
        
        clusters = []
        for i, comm in enumerate(communities):
            clusters.append({
                "id": i,
                "members": list(comm),
                "size": len(comm)
            })
            
        return {
            "clusters": clusters,
            "central_nodes": [{"id": node, "score": score} for node, score in central_nodes]
        }
