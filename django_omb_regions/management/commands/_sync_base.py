from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar

from django.core.management.base import BaseCommand
from django.db import models, transaction
from titlecase import titlecase

if TYPE_CHECKING:
  from collections.abc import Callable, Iterable, Sequence
  from typing import Any

  from django.db.models import Manager


ModelT = TypeVar("ModelT", bound=models.Model)


@dataclass
class SyncSummary:
  created: int = 0
  updated: int = 0
  skipped: int = 0


class SyncBaseCommand(BaseCommand, metaclass=ABCMeta):
  """Shared contract for reference and taxonomy sync commands.

  Subclasses implement the pipeline phases and set ``sync_noun``::

    _fetch -> _build_records -> _upsert -> _sync_relationships
    -> _report_summary

  The default ``handle`` runs that pipeline for commands whose ``_fetch`` takes
  no arguments. Commands that need extra options (e.g. ``--year``) override
  ``handle`` while still reusing the shared arguments, summary, and helpers.
  """

  sync_noun: str = "records"
  supports_skip_relationships: bool = False
  skip_relationships_help: str = "Skip relationship synchronization."

  def add_arguments(self, parser: Any) -> None:
    self.add_missing_only_argument(parser)
    if self.supports_skip_relationships:
      self.add_skip_relationships_argument(parser)

  def add_missing_only_argument(self, parser: Any) -> None:
    parser.add_argument(
      "--missing-only",
      action="store_true",
      help=(f"Only create missing {self.sync_noun}; do not update existing rows."),
    )

  def add_skip_relationships_argument(self, parser: Any) -> None:
    parser.add_argument(
      "--skip-relationships",
      action="store_true",
      help=self.skip_relationships_help,
    )

  def handle(self, *args: Any, **options: Any) -> None:
    source_data = self._fetch()
    records = self._build_records(source_data)
    summary = self._upsert(records, missing_only=options["missing_only"])

    if self.supports_skip_relationships and options.get("skip_relationships"):
      self.stdout.write(f"Syncing {self.sync_noun} relationships skipped.")
    else:
      self._sync_relationships(records)

    self._report_summary(summary)

  @abstractmethod
  def _fetch(self, *args: Any, **kwargs: Any) -> Any: ...

  @abstractmethod
  def _build_records(self, *args: Any, **kwargs: Any) -> list[Any]: ...

  @abstractmethod
  def _upsert(
    self,
    records: list[Any],
    *,
    missing_only: bool,
  ) -> SyncSummary: ...

  def _sync_relationships(self, records: list[Any]) -> None:
    pass

  def _report_summary(self, summary: SyncSummary) -> None:
    self.stdout.write(
      self.style.SUCCESS(
        f"Synced {self.sync_noun} "
        f"({summary.created} created, "
        f"{summary.updated} updated, "
        f"{summary.skipped} skipped)."
      )
    )

  def _upsert_records(
    self,
    records: Iterable[Any],
    *,
    manager: Manager[ModelT],
    key_fields: Sequence[str],
    defaults: Callable[[Any], dict[str, Any]],
    missing_only: bool,
  ) -> SyncSummary:
    record_list = list(records)
    summary = SyncSummary()

    filter_kwargs = {
      f"{field}__in": [getattr(record, field) for record in record_list]
      for field in key_fields
    }
    existing_keys = set(manager.filter(**filter_kwargs).values_list(*key_fields))

    with transaction.atomic():
      for record in record_list:
        record_key = tuple(getattr(record, field) for field in key_fields)
        if missing_only and record_key in existing_keys:
          summary.skipped += 1
          continue

        manager.update_or_create(
          **{field: getattr(record, field) for field in key_fields},
          defaults=defaults(record),
        )
        if record_key in existing_keys:
          summary.updated += 1
        else:
          summary.created += 1

    return summary

  def _parse_name(self, value: object) -> str:
    return str(titlecase(str(value).strip()))
