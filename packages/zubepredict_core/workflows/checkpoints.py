from __future__ import annotations

import base64
from collections.abc import Iterator, Sequence
from typing import Any, cast
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
    get_checkpoint_metadata,
)
from supabase import Client

from zubepredict_core.repositories.supabase import SupabaseRepositoryError


class SupabaseCheckpointSaver(BaseCheckpointSaver[int]):
    """Persist JSON-safe LangGraph checkpoints through the trusted Supabase client."""

    checkpoints_table = "workflow_checkpoints"
    writes_table = "workflow_checkpoint_writes"

    def __init__(self, client: Client, owner_id: UUID) -> None:
        super().__init__()
        self._client = client
        self._owner_id = str(owner_id)

    @staticmethod
    def _encode(value: tuple[str, bytes]) -> tuple[str, str]:
        value_type, blob = value
        return value_type, base64.b64encode(blob).decode("ascii")

    @staticmethod
    def _decode(value_type: str, blob: str) -> tuple[str, bytes]:
        return value_type, base64.b64decode(blob.encode("ascii"))

    def _execute(self, query: Any, action: str) -> Any:
        try:
            return query.execute()
        except Exception as exc:
            raise SupabaseRepositoryError(
                f"Supabase could not {action} LangGraph workflow checkpoints."
            ) from exc

    @staticmethod
    def _identity(config: RunnableConfig) -> tuple[str, str, str | None]:
        configurable = config.get("configurable", {})
        thread_id = str(configurable["thread_id"])
        namespace = str(configurable.get("checkpoint_ns", ""))
        checkpoint_id = get_checkpoint_id(config)
        return thread_id, namespace, checkpoint_id

    def _pending_writes(
        self, thread_id: str, namespace: str, checkpoint_id: str
    ) -> list[tuple[str, str, Any]]:
        query = (
            self._client.table(self.writes_table)
            .select("task_id,channel,value_type,value_blob,write_index")
            .eq("owner_id", self._owner_id)
            .eq("thread_id", thread_id)
            .eq("checkpoint_ns", namespace)
            .eq("checkpoint_id", checkpoint_id)
            .order("write_index")
        )
        response = self._execute(query, "read")
        return [
            (
                str(item["task_id"]),
                str(item["channel"]),
                self.serde.loads_typed(
                    self._decode(str(item["value_type"]), str(item["value_blob"]))
                ),
            )
            for item in (response.data or [])
        ]

    def _tuple(self, item: dict[str, Any]) -> CheckpointTuple:
        thread_id = str(item["thread_id"])
        namespace = str(item["checkpoint_ns"])
        checkpoint_id = str(item["checkpoint_id"])
        parent_id = item.get("parent_checkpoint_id")
        checkpoint = cast(
            Checkpoint,
            self.serde.loads_typed(
                self._decode(str(item["checkpoint_type"]), str(item["checkpoint_blob"]))
            ),
        )
        metadata = cast(
            CheckpointMetadata,
            self.serde.loads_typed(
                self._decode(str(item["metadata_type"]), str(item["metadata_blob"]))
            ),
        )
        config: RunnableConfig = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": namespace,
                "checkpoint_id": checkpoint_id,
            }
        }
        parent_config: RunnableConfig | None = None
        if parent_id:
            parent_config = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": namespace,
                    "checkpoint_id": str(parent_id),
                }
            }
        return CheckpointTuple(
            config=config,
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=parent_config,
            pending_writes=self._pending_writes(thread_id, namespace, checkpoint_id),
        )

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        thread_id, namespace, checkpoint_id = self._identity(config)
        query = (
            self._client.table(self.checkpoints_table)
            .select("*")
            .eq("owner_id", self._owner_id)
            .eq("thread_id", thread_id)
            .eq("checkpoint_ns", namespace)
        )
        if checkpoint_id:
            query = query.eq("checkpoint_id", checkpoint_id)
        else:
            query = query.order("created_at", desc=True)
        response = self._execute(query.limit(1), "read")
        data = response.data or []
        return self._tuple(data[0]) if data else None

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        query = (
            self._client.table(self.checkpoints_table).select("*").eq("owner_id", self._owner_id)
        )
        if config is not None:
            thread_id, namespace, _ = self._identity(config)
            query = query.eq("thread_id", thread_id).eq("checkpoint_ns", namespace)
        if before is not None and (before_id := get_checkpoint_id(before)):
            query = query.lt("checkpoint_id", before_id)
        query = query.order("created_at", desc=True)
        if limit is not None:
            query = query.limit(limit)
        response = self._execute(query, "list")
        yielded = 0
        for item in response.data or []:
            checkpoint_tuple = self._tuple(item)
            if filter and any(
                checkpoint_tuple.metadata.get(key) != value for key, value in filter.items()
            ):
                continue
            yield checkpoint_tuple
            yielded += 1
            if limit is not None and yielded >= limit:
                break

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        del new_versions  # Full JSON-safe state is stored atomically in checkpoint_blob.
        thread_id, namespace, parent_id = self._identity(config)
        checkpoint_type, checkpoint_blob = self._encode(self.serde.dumps_typed(checkpoint))
        metadata_type, metadata_blob = self._encode(
            self.serde.dumps_typed(get_checkpoint_metadata(config, metadata))
        )
        payload = {
            "owner_id": self._owner_id,
            "thread_id": thread_id,
            "checkpoint_ns": namespace,
            "checkpoint_id": checkpoint["id"],
            "parent_checkpoint_id": parent_id,
            "checkpoint_type": checkpoint_type,
            "checkpoint_blob": checkpoint_blob,
            "metadata_type": metadata_type,
            "metadata_blob": metadata_blob,
        }
        query = self._client.table(self.checkpoints_table).upsert(
            payload,
            on_conflict="owner_id,thread_id,checkpoint_ns,checkpoint_id",
        )
        self._execute(query, "write")
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": namespace,
                "checkpoint_id": checkpoint["id"],
            }
        }

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        if not writes:
            return
        thread_id, namespace, checkpoint_id = self._identity(config)
        if checkpoint_id is None:
            raise ValueError("LangGraph pending writes require a checkpoint_id.")
        payload: list[dict[str, Any]] = []
        for index, (channel, value) in enumerate(writes):
            value_type, value_blob = self._encode(self.serde.dumps_typed(value))
            payload.append(
                {
                    "owner_id": self._owner_id,
                    "thread_id": thread_id,
                    "checkpoint_ns": namespace,
                    "checkpoint_id": checkpoint_id,
                    "task_id": task_id,
                    "write_index": index,
                    "channel": channel,
                    "value_type": value_type,
                    "value_blob": value_blob,
                    "task_path": task_path,
                }
            )
        query = self._client.table(self.writes_table).upsert(
            payload,
            on_conflict=("owner_id,thread_id,checkpoint_ns,checkpoint_id,task_id,write_index"),
        )
        self._execute(query, "write pending")
