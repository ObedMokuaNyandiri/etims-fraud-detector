"""
Core Graph Engine — The heart of the eTIMS Knowledge Graph.

Transforms eTIMS transaction records into a directed graph and runs:
  1. Johnson's cycle detection (all elementary cycles)
  2. Betweenness centrality (broker identification)
  3. PageRank (influence scoring)
  4. Risk scoring (composite fraud likelihood)
"""

import hashlib
import json
import itertools
from dataclasses import dataclass, field

import networkx as nx


@dataclass
class DetectedRing:
    """A single circular invoicing ring."""
    members: list[str]
    edges: list[tuple[str, str]]
    total_amount: float = 0.0
    total_vat: float = 0.0
    transaction_ids: list[int] = field(default_factory=list)
    confidence: float = 0.0
    ring_hash: str = ""
    kra_vat_exposure: float = 0.0

    def compute_hash(self) -> str:
        """Deterministic fingerprint so we don't re-detect the same ring."""
        normalized = tuple(sorted(self.members))
        self.ring_hash = hashlib.sha256(
            json.dumps(normalized).encode()
        ).hexdigest()[:16]
        return self.ring_hash


class GraphEngine:
    """
    Builds and analyzes the eTIMS transaction knowledge graph.

    Usage:
        engine = GraphEngine()
        engine.add_transaction(buyer, seller, amount, vat, tx_id)
        rings = engine.detect_cycles(max_length=8)
        scores = engine.compute_risk_scores()
    """

    def __init__(self):
        self.graph = nx.DiGraph()
        self._edge_data: dict[tuple[str, str], list[dict]] = {}

    def clear(self):
        """Reset the graph."""
        self.graph.clear()
        self._edge_data.clear()

    def add_transaction(
        self,
        buyer_pin: str,
        seller_pin: str,
        amount: float,
        vat_amount: float,
        transaction_id: int,
        invoice_number: str = "",
        invoice_date: str | None = None,
    ):
        """Add a directed edge: seller → buyer (money flows buyer→seller, invoice flows seller→buyer)."""
        # In VAT fraud, the invoice chain matters: seller issues invoice TO buyer.
        # We model: seller --invoice--> buyer  (direction of the tax document)
        if not self.graph.has_node(seller_pin):
            self.graph.add_node(seller_pin)
        if not self.graph.has_node(buyer_pin):
            self.graph.add_node(buyer_pin)

        edge_key = (seller_pin, buyer_pin)
        if edge_key not in self._edge_data:
            self._edge_data[edge_key] = []

        self._edge_data[edge_key].append({
            "amount": amount,
            "vat": vat_amount,
            "tx_id": transaction_id,
            "invoice": invoice_number,
            "date": str(invoice_date) if invoice_date else "",
        })

        # Aggregate edge weight = total amount across all invoices between this pair
        total_amount = sum(e["amount"] for e in self._edge_data[edge_key])
        total_vat = sum(e["vat"] for e in self._edge_data[edge_key])
        tx_count = len(self._edge_data[edge_key])

        self.graph.add_edge(
            seller_pin,
            buyer_pin,
            weight=total_amount,
            vat=total_vat,
            count=tx_count,
        )

    def detect_cycles(self, max_length: int = 8, min_amount: float = 0.0) -> list[DetectedRing]:
        """
        Find all elementary cycles in the transaction graph.
        Uses Johnson's algorithm via NetworkX.

        Args:
            max_length: Maximum cycle length to report (filters long chains).
            min_amount: Minimum total cycle amount to flag.

        Returns:
            List of DetectedRing objects sorted by total_amount descending.
        """
        rings: list[DetectedRing] = []
        seen_hashes: set[str] = set()

        # Johnson's algorithm — finds ALL elementary circuits
        for cycle_nodes in nx.simple_cycles(self.graph, length_bound=max_length):
            if len(cycle_nodes) < 3:
                continue  # Need at least 3 nodes for a ring

            # Build edge list for this cycle
            edges = []
            for i in range(len(cycle_nodes)):
                src = cycle_nodes[i]
                dst = cycle_nodes[(i + 1) % len(cycle_nodes)]
                edges.append((src, dst))

            # Calculate total amounts flowing through the ring
            total_amount = 0.0
            total_vat = 0.0
            tx_ids = []

            for src, dst in edges:
                edge_key = (src, dst)
                if edge_key in self._edge_data:
                    # Aggregate split invoices
                    for tx in self._edge_data[edge_key]:
                        total_amount += tx["amount"]
                        total_vat += tx["vat"]
                        tx_ids.append(tx["tx_id"])

            if total_amount < min_amount:
                continue

            ring = DetectedRing(
                members=list(cycle_nodes),
                edges=edges,
                total_amount=total_amount,
                total_vat=total_vat,
                transaction_ids=tx_ids,
                kra_vat_exposure=total_vat,  # Total VAT circulating in the scheme
            )
            ring.compute_hash()

            # Deduplicate rotations of the same cycle
            if ring.ring_hash in seen_hashes:
                continue
            seen_hashes.add(ring.ring_hash)

            # Confidence scoring
            ring.confidence = self._score_ring_confidence(ring)
            rings.append(ring)

        # Sort by total amount (highest fraud exposure first)
        rings.sort(key=lambda r: r.total_amount, reverse=True)
        return rings

    def _score_ring_confidence(self, ring: DetectedRing) -> float:
        """
        Heuristic confidence score for a detected ring.
        Factors:
          - Cycle tightness (shorter = more suspicious)
          - Amount consistency & Margin Decay (amounts dropping slightly per hop to mimic margins)
          - Temporal Sequencing (invoices chronologically flowing across the hops)
        """
        score = 0.0

        # 1. Cycle length penalty: 3-node rings are most suspicious, 2-nodes are benign reciprocal trade and are ignored
        length_scores = {3: 0.95, 4: 0.85, 5: 0.70, 6: 0.55, 7: 0.40, 8: 0.30}
        score += length_scores.get(len(ring.members), 0.20)

        # 2. Amount analysis: Margin Decay vs Consistency
        edge_amounts = []
        edge_dates = []
        for src, dst in ring.edges:
            edge_key = (src, dst)
            if edge_key in self._edge_data:
                # Aggregate split invoices on this hop
                agg_amt = sum(tx["amount"] for tx in self._edge_data[edge_key])
                edge_amounts.append(agg_amt)
                
                # Get the earliest invoice date for this hop
                valid_dates = [tx["date"] for tx in self._edge_data[edge_key] if tx["date"]]
                if valid_dates:
                    edge_dates.append(min(valid_dates))

        if len(edge_amounts) > 1:
            # Rotate amounts so the highest amount is first (logical start of the scheme)
            max_idx = edge_amounts.index(max(edge_amounts))
            rotated_amounts = edge_amounts[max_idx:] + edge_amounts[:max_idx]

            mean_amt = sum(rotated_amounts) / len(rotated_amounts)
            if mean_amt > 0:
                variance = sum((a - mean_amt) ** 2 for a in rotated_amounts) / len(rotated_amounts)
                cv = (variance ** 0.5) / mean_amt
                
                # Check for Margin Decay (amounts consistently decreasing)
                is_decaying = all(rotated_amounts[i] >= rotated_amounts[i+1] * 0.9 for i in range(len(rotated_amounts)-1))
                
                if is_decaying and cv > 0.01:
                    score += 0.4  # High bonus for realistic margin decay
                else:
                    # Low CV = suspiciously consistent = higher confidence
                    consistency_bonus = max(0, 0.3 - cv * 0.5)
                    score += consistency_bonus

        # 3. Temporal Sequencing
        if len(edge_dates) == len(ring.edges):
            # Rotate dates so the earliest date is first
            min_idx = edge_dates.index(min(edge_dates))
            rotated_dates = edge_dates[min_idx:] + edge_dates[:min_idx]

            # Check if dates are chronologically increasing
            is_temporal = all(rotated_dates[i] <= rotated_dates[i+1] for i in range(len(rotated_dates)-1))
            if is_temporal:
                score += 0.3  # Huge bonus for sequenced circular flow

        return min(score, 1.0)

    def compute_risk_scores(self) -> dict[str, dict]:
        """
        Compute composite risk scores for all nodes using:
          - Betweenness centrality (broker potential)
          - PageRank (influence in network)
          - In/out degree ratio
        """
        betweenness = nx.betweenness_centrality(self.graph, weight="weight")
        degree_cent = nx.degree_centrality(self.graph)

        scores = {}
        for node in self.graph.nodes():
            in_deg = self.graph.in_degree(node)
            out_deg = self.graph.out_degree(node)
            degree_ratio = out_deg / max(in_deg, 1)

            # Composite risk score (weighted combination)
            risk = (
                betweenness.get(node, 0) * 0.50
                + degree_cent.get(node, 0) * 0.20
                + min(degree_ratio, 2.0) / 2.0 * 0.30  # Normalized degree ratio
            )

            scores[node] = {
                "risk_score": round(min(risk, 1.0), 4),
                "betweenness": round(betweenness.get(node, 0), 4),
                "pagerank": round(degree_cent.get(node, 0), 6),
                "in_degree": in_deg,
                "out_degree": out_deg,
            }

        return scores

    def get_graph_data(self) -> dict:
        """
        Export graph as nodes + edges for D3.js visualization.
        """
        nodes = []
        for node in self.graph.nodes():
            nodes.append({
                "id": node,
                "in_degree": self.graph.in_degree(node),
                "out_degree": self.graph.out_degree(node),
            })

        edges = []
        for src, dst, data in self.graph.edges(data=True):
            edge_txs = self._edge_data.get((src, dst), [])
            edges.append({
                "source": src,
                "target": dst,
                "amount": data.get("weight", 0),
                "vat": data.get("vat", 0),
                "count": data.get("count", 1),
                "invoices": [tx.get("invoice", "") for tx in edge_txs],
            })

        return {"nodes": nodes, "edges": edges}

    @property
    def stats(self) -> dict:
        """Quick summary statistics."""
        return {
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
            "density": round(nx.density(self.graph), 4) if self.graph.number_of_nodes() > 1 else 0,
            "is_connected": nx.is_weakly_connected(self.graph) if self.graph.number_of_nodes() > 0 else False,
            "components": nx.number_weakly_connected_components(self.graph) if self.graph.number_of_nodes() > 0 else 0,
        }
