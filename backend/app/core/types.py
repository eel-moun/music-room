"""Shared column types and enums."""

from enum import StrEnum

from sqlalchemy import Enum


class Visibility(StrEnum):
    public = "public"
    private = "private"


def str_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    """VARCHAR + CHECK constraint (easier to migrate than a native Postgres ENUM)."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=20,
        values_callable=lambda e: [m.value for m in e],
    )
