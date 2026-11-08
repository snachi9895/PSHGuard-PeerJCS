#!/usr/bin/env python3
"""Bounded P3 relation-conditioned behavior-evidence readout.

This module deliberately leaves the frozen V10c graph, input tensors, HGT
encoder, and type-balanced Module/AST/Event readout unchanged.  It adds one
graph-level evidence summary formed only from endpoints of three already
existing forward behavior relations.  Raw API names, raw Param text, package
names, and family identities are neither loaded nor represented here.
"""

from __future__ import annotations

from typing import Any

import torch
import torch.nn.functional as F
from torch import nn
from torch_geometric.nn import global_max_pool, global_mean_pool

import train_v10c_formal_hgt as formal


# Capture the accepted practical class before the P3 trainer installs this
# candidate into the otherwise unchanged formal trainer.
PracticalTypeBalancedHGTV9 = formal.architecture.TypeBalancedHGTV9

BEHAVIOR_EVIDENCE_RELATIONS: tuple[tuple[str, str, str], ...] = (
    ("ast", "E_Event", "event"),
    ("ast", "E_Param", "param"),
    ("event", "E_EventParam", "param"),
)


class RelationConditionedBehaviorEvidenceReadout(PracticalTypeBalancedHGTV9):
    """Add a relation-balanced endpoint-evidence summary after the frozen HGT.

    Each eligible edge is represented from its contextualized source endpoint,
    destination endpoint, and their elementwise interaction.  A learned
    relation embedding conditions the shared evidence projector.  Evidence is
    mean/max pooled within each relation and graph; the three relation-level
    summaries are then balanced equally, so a relation cannot dominate merely
    because it contains more edges.
    """

    evidence_relations = BEHAVIOR_EVIDENCE_RELATIONS

    def __init__(self, hidden_dim: int, schema, mode: str):
        if mode != "ast_event_param_context":
            raise ValueError(
                "P3 RCBER is frozen only for mode=ast_event_param_context, "
                f"got {mode!r}"
            )
        super().__init__(hidden_dim, schema, mode)
        self.hidden_dim = int(hidden_dim)
        self.evidence_projector = nn.Linear(hidden_dim * 3, hidden_dim)
        self.evidence_relation_embedding = nn.Embedding(
            len(self.evidence_relations), hidden_dim
        )
        self.evidence_norm = nn.LayerNorm(hidden_dim)
        self.evidence_pool_norm = nn.LayerNorm(hidden_dim * 2)

        # Replacing only the graph classifier is unavoidable because the
        # frozen type-balanced representation gains one additional 2H block.
        # The practical classifier was constructed first by ``super`` so all
        # shared encoder/readout parameters keep identical creation order.
        classifier_input_dim = hidden_dim * 2 * (len(self.node_types) + 1)
        self.classifier = nn.Sequential(
            nn.Linear(classifier_input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim, 2),
        )
        self.last_evidence_audit: dict[str, Any] = {}

    def _encode(self, data) -> dict[str, torch.Tensor]:
        x_dict = {
            node_type: F.relu(self.lin_dict[node_type](data[node_type].x))
            for node_type in data.node_types
            if node_type in self.lin_dict
        }
        edge_index_dict = {
            edge_type: data[edge_type].edge_index
            for edge_type in data.edge_types
            if "edge_index" in data[edge_type]
        }
        if edge_index_dict:
            x1 = {
                key: F.relu(value)
                for key, value in self.conv1(x_dict, edge_index_dict).items()
            }
            x_dict = self.merge(x_dict, x1)
            x2 = {
                key: F.relu(value)
                for key, value in self.conv2(x_dict, edge_index_dict).items()
            }
            x_dict = self.merge(x_dict, x2)
        return x_dict

    def _type_balanced_readout(
        self,
        data,
        x_dict: dict[str, torch.Tensor],
        batch_size: int,
    ) -> list[torch.Tensor]:
        representations: list[torch.Tensor] = []
        for node_type in self.node_types:
            x = x_dict.get(node_type)
            if x is None or x.size(0) == 0:
                width = int(self.type_norms[node_type].normalized_shape[0])
                pooled = torch.zeros(
                    (batch_size, width),
                    dtype=next(self.parameters()).dtype,
                    device=data.y.device,
                )
            else:
                pooled = torch.cat(
                    [
                        global_mean_pool(
                            x, data[node_type].batch, size=batch_size
                        ),
                        global_max_pool(
                            x, data[node_type].batch, size=batch_size
                        ),
                    ],
                    dim=1,
                )
            representations.append(self.type_norms[node_type](pooled))
        return representations

    def _relation_balanced_evidence_readout(
        self,
        data,
        x_dict: dict[str, torch.Tensor],
        batch_size: int,
    ) -> torch.Tensor:
        relation_means: list[torch.Tensor] = []
        relation_maxima: list[torch.Tensor] = []
        relation_presence: list[torch.Tensor] = []
        relation_edge_counts: dict[str, int] = {}
        endpoint_batch_mismatches = 0

        dtype = next(self.parameters()).dtype
        device = data.y.device
        for relation_index, edge_type in enumerate(self.evidence_relations):
            key = "__".join(edge_type)
            edge_index = None
            if edge_type in data.edge_types and "edge_index" in data[edge_type]:
                edge_index = data[edge_type].edge_index
            edge_count = 0 if edge_index is None else int(edge_index.size(1))
            relation_edge_counts[key] = edge_count

            if edge_count == 0:
                relation_means.append(
                    torch.zeros((batch_size, self.hidden_dim), dtype=dtype, device=device)
                )
                relation_maxima.append(
                    torch.zeros((batch_size, self.hidden_dim), dtype=dtype, device=device)
                )
                relation_presence.append(
                    torch.zeros((batch_size, 1), dtype=torch.bool, device=device)
                )
                continue

            source_type, _, destination_type = edge_type
            source_index = edge_index[0]
            destination_index = edge_index[1]
            source_batch = data[source_type].batch[source_index]
            destination_batch = data[destination_type].batch[destination_index]
            endpoint_batch_mismatches += int(
                (source_batch != destination_batch).sum().item()
            )
            if endpoint_batch_mismatches:
                raise RuntimeError(
                    "P3 evidence relation connects endpoints from different graphs"
                )

            source = x_dict[source_type][source_index]
            destination = x_dict[destination_type][destination_index]
            evidence_input = torch.cat(
                [source, destination, source * destination], dim=1
            )
            evidence = self.evidence_projector(evidence_input)
            evidence = evidence + self.evidence_relation_embedding.weight[relation_index]
            evidence = F.relu(self.evidence_norm(evidence))

            relation_means.append(
                global_mean_pool(evidence, source_batch, size=batch_size)
            )
            relation_maxima.append(
                global_max_pool(evidence, source_batch, size=batch_size)
            )
            counts = torch.bincount(source_batch, minlength=batch_size)
            relation_presence.append((counts > 0).view(batch_size, 1))

        means = torch.stack(relation_means, dim=0)
        maxima = torch.stack(relation_maxima, dim=0)
        presence = torch.stack(relation_presence, dim=0)
        present_count = presence.sum(dim=0)
        balanced_mean = (
            means * presence.to(dtype=means.dtype)
        ).sum(dim=0) / present_count.clamp_min(1).to(dtype=means.dtype)

        masked_maxima = maxima.masked_fill(~presence, float("-inf"))
        balanced_max = masked_maxima.max(dim=0).values
        any_present = present_count > 0
        balanced_max = torch.where(
            any_present,
            balanced_max,
            torch.zeros_like(balanced_max),
        )
        pooled = self.evidence_pool_norm(
            torch.cat([balanced_mean, balanced_max], dim=1)
        )
        # Keep the promised neutral value for graphs with no eligible relation;
        # LayerNorm bias must not turn absence into a learned constant vector.
        pooled = pooled * any_present.to(dtype=pooled.dtype)

        self.last_evidence_audit = {
            "relation_edge_counts": relation_edge_counts,
            "graphs_with_any_evidence": int(any_present.sum().item()),
            "batch_size": batch_size,
            "endpoint_batch_mismatches": endpoint_batch_mismatches,
            "pooled_l1": float(pooled.detach().abs().sum().cpu().item()),
        }
        return pooled

    def forward(self, data):
        x_dict = self._encode(data)
        batch_size = int(data.y.view(-1).size(0))
        representations = self._type_balanced_readout(data, x_dict, batch_size)
        representations.append(
            self._relation_balanced_evidence_readout(data, x_dict, batch_size)
        )
        return self.classifier(torch.cat(representations, dim=1))


def common_state_dict(state_dict: dict[str, torch.Tensor]) -> dict[str, torch.Tensor]:
    """Return tensors that must initialize identically to the practical model."""

    excluded_prefixes = (
        "classifier.",
        "evidence_projector.",
        "evidence_relation_embedding.",
        "evidence_norm.",
        "evidence_pool_norm.",
    )
    return {
        name: value
        for name, value in state_dict.items()
        if not name.startswith(excluded_prefixes)
    }
