from dataclasses import dataclass
from cinder.collections.schema import Collection
from cinder.db.connection import Database


@dataclass
class AddTable:
    collection: Collection
    destructive: bool = False


@dataclass
class AddColumn:
    table: str
    field_name: str
    col_sql: str   # just the column definition, e.g. "category TEXT"
    destructive: bool = False


@dataclass
class DropColumn:
    table: str
    col_name: str
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
                existing_cols = {col["name"] for col in await self.db.get_columns(collection.name)}
                schema_fields = {f.name for f in collection.fields} | self.BUILTIN_COLUMNS

                for f in collection.fields:
                    if f.name not in existing_cols:
                        operations.append(AddColumn(
                            table=collection.name,
                            field_name=f.name,
                            col_sql=f.column_sql(),
                        ))

                for col_name in sorted(existing_cols - schema_fields):
                    operations.append(DropColumn(table=collection.name, col_name=col_name))
        return operations
