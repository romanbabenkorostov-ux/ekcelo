"""C2 — §1-§6: ЕГРН-слепок (§1-§5) + ЭТП-профиль (§6) в ORM.

Порт `schema/egrn_current_schema.sql` на общий `Base` из models.py — чтобы вся
C2-схема (§1-§12) жила в одном `Base.metadata` и одной истории Alembic.

ADR-001: §1-§5 восстанавливаются из выписок ЕГРН; §6 (object_etp_profile, lots,
lot_items) — не-ЕГРН слой с source+confidence, при пересоздании НЕ восстанавливается.

Натуральные ключи сохранены (cad_number, inn, lot_id) ради совместимости с парсером
и графом (`graph_node_id` строится из cad_number/inn). JSON-поля ЭТП-профиля переведены
на PortableJSON (JSONB на PG, JSON1 на SQLite); даты — на DateTime (было TEXT).
"""
from datetime import datetime

from sqlalchemy import (
    CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from contracts.db.models import Base, PortableJSON


# --------------------------------------------------------------------------- #
# §1. Объекты недвижимости
# --------------------------------------------------------------------------- #
class Object(Base):
    __tablename__ = "objects"
    cad_number: Mapped[str] = mapped_column(String(50), primary_key=True)
    object_type: Mapped[str] = mapped_column(String(20), index=True)  # land|building|construction|flat|room
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    area: Mapped[float | None] = mapped_column(Float, nullable=True)
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    permitted_use: Mapped[str | None] = mapped_column(Text, nullable=True)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    floors: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # §1 расширение (mig 0004) — нормативные аспекты выписки (П/0329), парсер их извлекает
    quarter_cad_number: Mapped[str | None] = mapped_column(String(50), index=True, nullable=True)
    parent_cad_number: Mapped[str | None] = mapped_column(String(50), index=True, nullable=True)
    inventory_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    conditional_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cadastral_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    floor: Mapped[str | None] = mapped_column(String(32), nullable=True)   # этаж помещения (м.б. «1; 2»)
    okato: Mapped[str | None] = mapped_column(String(16), nullable=True)
    kladr: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fias_guid: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status_egrn: Mapped[str | None] = mapped_column(Text, nullable=True)   # «актуальные, ранее учтённые»
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# --------------------------------------------------------------------------- #
# §2. Реестр правообладателей (надстройка — subjects, 1:1 по inn)
# --------------------------------------------------------------------------- #
class EntityRegistry(Base):
    __tablename__ = "entity_registry"
    inn: Mapped[str] = mapped_column(String(12), primary_key=True)
    name_full: Mapped[str] = mapped_column(Text)
    name_short: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ogrn: Mapped[str | None] = mapped_column(String(15), nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(8), nullable=True)  # ЮЛ|ИП|ФЛ|Гос
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# --------------------------------------------------------------------------- #
# §3. Права и доли
# --------------------------------------------------------------------------- #
class Right(Base):
    __tablename__ = "rights"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cad_number: Mapped[str] = mapped_column(
        ForeignKey("objects.cad_number", ondelete="CASCADE"), index=True
    )
    right_type: Mapped[str] = mapped_column(String(64))  # ownership|lease|...
    right_holder_inn: Mapped[str | None] = mapped_column(
        ForeignKey("entity_registry.inn"), index=True, nullable=True
    )
    share_numerator: Mapped[int | None] = mapped_column(Integer, nullable=True)
    share_denominator: Mapped[int | None] = mapped_column(Integer, nullable=True)
    registration_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    registration_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_extract_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# --------------------------------------------------------------------------- #
# §4. История выписок
# --------------------------------------------------------------------------- #
class Extract(Base):
    __tablename__ = "extracts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    extract_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cad_number: Mapped[str] = mapped_column(ForeignKey("objects.cad_number"), index=True)
    extract_date: Mapped[str] = mapped_column(String(32))
    document_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_json: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    parsed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    parser_version: Mapped[str | None] = mapped_column(String(32), nullable=True)


# --------------------------------------------------------------------------- #
# §5. Ограничения / обременения объекта
# --------------------------------------------------------------------------- #
class ObjectRestriction(Base):
    __tablename__ = "object_restrictions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cad_number: Mapped[str] = mapped_column(ForeignKey("objects.cad_number"), index=True)
    restrict_type: Mapped[str | None] = mapped_column(String(64), nullable=True)  # czuit_zone|okn_territory|...
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    registry_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    valid_from: Mapped[str | None] = mapped_column(String(32), nullable=True)
    valid_to: Mapped[str | None] = mapped_column(String(32), nullable=True)
    basis_doc: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# --------------------------------------------------------------------------- #
# §6. ЭТП-профиль (не-ЕГРН слой; source + confidence)
# --------------------------------------------------------------------------- #
class ObjectEtpProfile(Base):
    __tablename__ = "object_etp_profile"
    cad_number: Mapped[str] = mapped_column(
        ForeignKey("objects.cad_number", ondelete="CASCADE"), primary_key=True
    )
    location_extra: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    building_extra: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    layout: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    legal_extra: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    risks: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    extras: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    source: Mapped[str] = mapped_column(String(8))
    confidence: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        CheckConstraint("source IN ('osv','exif','manual','nspd','llm')", name="ck_etp_source"),
        CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name="ck_etp_confidence"),
    )


class Lot(Base):
    __tablename__ = "lots"
    lot_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    platform_targets: Mapped[list | None] = mapped_column(PortableJSON, nullable=True)
    procedure_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    deal_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    primary_cad_number: Mapped[str | None] = mapped_column(
        ForeignKey("objects.cad_number", ondelete="SET NULL"), index=True, nullable=True
    )
    notes_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        CheckConstraint("length(lot_id) BETWEEN 1 AND 256", name="ck_lot_id_len"),
        CheckConstraint("lot_id NOT GLOB '*[^A-Za-z0-9_:/-]*'", name="ck_lot_id_charset"),
        CheckConstraint("deal_type IS NULL OR deal_type IN ('sale','lease','other')", name="ck_lot_deal_type"),
    )


class LotItem(Base):
    __tablename__ = "lot_items"
    lot_id: Mapped[str] = mapped_column(
        ForeignKey("lots.lot_id", ondelete="CASCADE"), primary_key=True
    )
    cad_number: Mapped[str] = mapped_column(
        ForeignKey("objects.cad_number", ondelete="CASCADE"), primary_key=True, index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    ord: Mapped[int] = mapped_column(Integer, default=1)

    __table_args__ = (
        CheckConstraint("role IN ('building','land','room','equipment','structure')", name="ck_lot_item_role"),
    )
