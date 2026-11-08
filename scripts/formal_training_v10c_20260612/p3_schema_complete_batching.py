#!/usr/bin/env python3
"""Schema-complete batching for the P3 repaired paired experiment.

PyG heterogeneous batching assumes that every graph exposes the same stores.
The frozen practical PT files are individually valid, but omit an edge store
when a relation has no edges.  A later graph can therefore receive an invalid
offset, or its relation can be omitted, when several graphs are collated.

This module does not rebuild or alter a graph.  It only materializes missing
allowed edge stores as empty ``[2, 0]`` tensors before collation and validates
all existing endpoints against their per-graph node stores.
"""

from __future__ import annotations

from typing import Iterable

import torch

import train_v10c_formal_hgt as formal


COLLATION_REPAIR_NAME = "schema_complete_empty_edge_stores"
COLLATION_REPAIR_VERSION = "2.0.0"

# Capture the unchanged formal dataset before a P3-v2 process installs the
# schema-complete subclass.  The class continues to load the same frozen PT and
# apply the same mode filtering/component weights as the practical trainer.
LegacyFormalDataset = formal.FormalDataset


def expected_node_types(mode: str) -> tuple[str, ...]:
    try:
        values = formal.architecture.base.MODE_NODE_TYPES[mode]
    except KeyError as exc:
        raise ValueError(f"unknown graph mode: {mode!r}") from exc
    return tuple(values)


def expected_edge_types(mode: str) -> tuple[tuple[str, str, str], ...]:
    try:
        values = formal.architecture.base.MODE_EDGES[mode]
    except KeyError as exc:
        raise ValueError(f"unknown graph mode: {mode!r}") from exc
    return tuple(sorted(values))


def _validate_edge_index(
    data,
    edge_type: tuple[str, str, str],
    edge_index: torch.Tensor,
) -> None:
    if not isinstance(edge_index, torch.Tensor):
        raise TypeError(f"{edge_type} edge_index is not a tensor")
    if edge_index.dtype != torch.long:
        raise TypeError(
            f"{edge_type} edge_index must use torch.long, got {edge_index.dtype}"
        )
    if edge_index.dim() != 2 or edge_index.size(0) != 2:
        raise RuntimeError(
            f"{edge_type} edge_index must have shape [2,E], got "
            f"{tuple(edge_index.shape)}"
        )
    if edge_index.numel() == 0:
        return

    source_type, _, destination_type = edge_type
    source_nodes = int(data[source_type].num_nodes)
    destination_nodes = int(data[destination_type].num_nodes)
    invalid = (
        (edge_index[0] < 0)
        | (edge_index[1] < 0)
        | (edge_index[0] >= source_nodes)
        | (edge_index[1] >= destination_nodes)
    )
    if bool(invalid.any()):
        raise RuntimeError(
            "individual graph contains an out-of-bounds relation endpoint: "
            f"edge_type={edge_type} invalid_edges={int(invalid.sum())} "
            f"source_nodes={source_nodes} destination_nodes={destination_nodes}"
        )


def ensure_schema_complete(data, mode: str):
    """Add only missing empty edge stores and validate the per-graph schema."""

    nodes = expected_node_types(mode)
    edges = expected_edge_types(mode)
    observed_nodes = set(data.node_types)
    missing_nodes = sorted(set(nodes).difference(observed_nodes))
    unexpected_nodes = sorted(observed_nodes.difference(nodes))
    if missing_nodes or unexpected_nodes:
        raise RuntimeError(
            "schema-complete batching refuses node-store drift: "
            f"missing={missing_nodes} unexpected={unexpected_nodes}"
        )
    for node_type in nodes:
        if "x" not in data[node_type]:
            raise RuntimeError(f"node store {node_type!r} has no x tensor")
        if data[node_type].x.dim() != 2:
            raise RuntimeError(
                f"node store {node_type!r} x must be rank 2, got "
                f"{tuple(data[node_type].x.shape)}"
            )

    allowed = set(edges)
    unexpected_edges = sorted(set(data.edge_types).difference(allowed))
    if unexpected_edges:
        raise RuntimeError(
            f"schema-complete batching refuses unexpected relations: {unexpected_edges}"
        )

    for edge_type in edges:
        if edge_type not in data.edge_types or "edge_index" not in data[edge_type]:
            data[edge_type].edge_index = torch.empty((2, 0), dtype=torch.long)
        _validate_edge_index(data, edge_type, data[edge_type].edge_index)

    if set(data.edge_types) != allowed:
        raise RuntimeError("failed to materialize the complete heterogeneous schema")
    return data


class SchemaCompleteFormalDataset(LegacyFormalDataset):
    """The unchanged formal dataset plus deterministic empty-store completion."""

    def __getitem__(self, index):
        data = super().__getitem__(index)
        return ensure_schema_complete(data, self.mode)


def install_schema_complete_dataset() -> None:
    """Bind the repaired dataset to the otherwise unchanged formal trainer."""

    formal.FormalDataset = SchemaCompleteFormalDataset


def relation_endpoint_batch_mismatches(
    batch,
    edge_types: Iterable[tuple[str, str, str]],
) -> int:
    """Count heterotypic/homotypic relation endpoints assigned to other graphs."""

    mismatches = 0
    for edge_type in edge_types:
        edge_index = batch[edge_type].edge_index
        if edge_index.numel() == 0:
            continue
        source_type, _, destination_type = edge_type
        source_batch = batch[source_type].batch[edge_index[0]]
        destination_batch = batch[destination_type].batch[edge_index[1]]
        mismatches += int((source_batch != destination_batch).sum().item())
    return mismatches
