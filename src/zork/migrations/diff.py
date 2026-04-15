from dataclasses import dataclass

from zork.collections.schema import Collection
from zork.db.connection import Database


@dataclass
class AddTable:
    collection: Collection
    destructive: bool = False


@dataclass
class AddColumn:
    table: str
    field_name: str
    col_sql: str  # just the column definition, e.g. "category TEXT"
    destructive: bool = False


@dataclass
class DropColumn:
    table: str
    col_name: str
    destructive: bool = True


@dataclass
class AddIndex:
    table: str
    index_name: str
    columns: tuple[str, ...]
    destructive: bool = False


@dataclass
class DropIndex:
    table: str
    index_name: str
    destructive: bool = True


class SchemaComparator:
    BUILTIN_COLUMNS = {"id", "created_at", "updated_at"}

    def __init__(self, db: Database, collections: list[Collection]):
        self.db = db
        self.collections = collections

    async def diff(self) -> list:
        operations = []
        for collection in self.collections:
            if not await self.db.table_exists(collection.name):
                operations.append(AddTable(collection=collection))
            else:
                existing_cols = {
                    col["name"] for col in await self.db.get_columns(collection.name)
                }
                schema_fields = {
                    f.name for f in collection.fields
                } | self.BUILTIN_COLUMNS

                for f in collection.fields:
                    if f.name not in existing_cols:
                        operations.append(
                            AddColumn(
                                table=collection.name,
                                field_name=f.name,
                                col_sql=f.column_sql(),
                            )
                        )

                for col_name in sorted(existing_cols - schema_fields):
                    operations.append(
                        DropColumn(table=collection.name, col_name=col_name)
                    )

                if await self.db.table_exists(collection.name):
                    existing_idx = set(await self.db.get_indexes(collection.name))
                    for sql in collection.build_index_sqls():
                        idx_name = sql.split()[5]
                        if idx_name not in existing_idx:
                            cols_str = sql.split("(", 1)[1].rstrip(")")
                            cols = tuple(c.strip() for c in cols_str.split(","))
                            operations.append(
                                AddIndex(
                                    table=collection.name,
                                    index_name=idx_name,
                                    columns=cols,
                                )
                            )
                    expected_idx = {
                        sql.split()[5] for sql in collection.build_index_sqls()
                    }
                    for idx in sorted(existing_idx - expected_idx):
                        operations.append(
                            DropIndex(table=collection.name, index_name=idx)
                        )
        return operations
