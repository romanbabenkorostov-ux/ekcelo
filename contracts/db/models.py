"""C2 — SQLAlchemy ORM (целевая объединённая схема EKCELO).

Реализует SCHEMA_SPEC.md: §1-§6 (ЕГРН-слепок + ЭТП) сохранены, §7-§12 — граф знаний,
геометрия, технологический/коммерческий/документный слои + субъекты-надстройка.

Переносимость SQLite (локально, JSON1) ↔ PostgreSQL (масштаб, JSONB):
- JSON  : JSON().with_variant(JSONB, "postgresql")
- UUID  : Uuid (native на PG, CHAR(32) на SQLite)
- Геометрия: WKT/GeoJSON + srid (PostGIS опционально на PG)

Миграции — Alembic (render_as_batch=True для SQLite). Источник истины метаданных — Base.metadata.
snake_case везде. Совместимо с C1 (graph_node_id), C4 (ViewModel facets), C5 (Lot).

NB: без `from __future__ import annotations` — SQLAlchemy 2.0 резолвит Mapped[...]
в миксинах по реальным типам (Python 3.10+ для union `X | None`).
"""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON, Boolean, CheckConstraint, Date, DateTime, Enum as SAEnum, Float,
    ForeignKey, Integer, String, Text, Uuid, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Переносимый JSON: JSONB на Postgres, обычный JSON (=> JSON1) на SQLite.
PortableJSON = JSON().with_variant(JSONB, "postgresql")


class Base(DeclarativeBase):
    pass


# --------------------------------------------------------------------------- #
# Миксины
# --------------------------------------------------------------------------- #
class PKMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class Bitemporal:
    """Две оси времени (ответ 14). valid_* — реальность, recorded/superseded — система."""
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class EntityKind(str, enum.Enum):
    land = "land"; building = "building"; room = "room"; structure = "structure"
    ons = "ons"; bu = "bu"; equipment = "equipment"; device = "device"
    right = "right"; encumbrance = "encumbrance"
    beneficiary_legal = "beneficiary_legal"; beneficiary_person = "beneficiary_person"
    state_body = "state_body"; level = "level"; doc = "doc"; lot = "lot"
    order = "order"; business_asset = "business_asset"
    flow_node = "flow_node"; demarcation_point = "demarcation_point"


class RelationDomain(str, enum.Enum):
    legal = "legal"; tech = "tech"; spatial = "spatial"
    accounting = "accounting"; commercial = "commercial"


class SubjectType(str, enum.Enum):
    INDIVIDUAL = "INDIVIDUAL"
    LEGAL_ENTITY = "LEGAL_ENTITY"
    INDIVIDUAL_ENTREPRENEUR = "INDIVIDUAL_ENTREPRENEUR"
    STATE_BODY = "STATE_BODY"
    # NB: бенефициар/асесор/админ — РОЛИ (C6), не тип субъекта (поправка A2).


class VatMode(str, enum.Enum):
    OSNO = "OSNO"; USN = "USN"; USN_VAT = "USN_VAT"


class DataSourceType(str, enum.Enum):
    EGRN = "EGRN"; EGRUL = "EGRUL"; EGRIP = "EGRIP"; OSV = "OSV"
    NSPD = "NSPD"; EXIF = "EXIF"; COURT_DECISION = "COURT_DECISION"
    SURVEY_MANUAL = "SURVEY_MANUAL"; LLM = "LLM"


# Веса источников (ответ 19). EGRUL/EGRIP отсутствуют — они НЕ доказывают OWNS.
SOURCE_WEIGHTS: dict[DataSourceType, float] = {
    DataSourceType.EGRN: 1.0,
    DataSourceType.COURT_DECISION: 1.0,
    DataSourceType.OSV: 0.8,
    DataSourceType.NSPD: 0.6,
    DataSourceType.EXIF: 0.5,
    DataSourceType.SURVEY_MANUAL: 0.3,
    DataSourceType.LLM: 0.4,
}


class AssertionStatus(str, enum.Enum):
    active = "active"; superseded = "superseded"; disputed = "disputed"; rejected = "rejected"


class FlowEventType(str, enum.Enum):
    DISCRETE = "DISCRETE"; CONTINUOUS = "CONTINUOUS"; CORRECTION = "CORRECTION"


class UpdStatus(int, enum.Enum):
    INVOICE_AND_PRIMARY = 1   # с НДС (ОСНО / УСН-НДС)
    PRIMARY_ONLY = 2          # без НДС (УСН)


# --------------------------------------------------------------------------- #
# §7 Граф знаний
# --------------------------------------------------------------------------- #
class Entity(PKMixin, Base):
    """Реестр узлов логического графа (адресация поверх таблиц-владельцев)."""
    __tablename__ = "entities"

    graph_node_id: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    kind: Mapped[EntityKind] = mapped_column(SAEnum(EntityKind), index=True)
    ref_table: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ref_pk: Mapped[str | None] = mapped_column(String(64), nullable=True)
    label: Mapped[str | None] = mapped_column(String(512), nullable=True)
    cad_number: Mapped[str | None] = mapped_column(String(50), index=True, nullable=True)
    meta: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)

    __table_args__ = (
        CheckConstraint(
            r"graph_node_id GLOB '[A-Za-z0-9_:/-]*'", name="ck_entity_graph_node_id_charset"
        ),
    )


class RelationType(PKMixin, Base):
    __tablename__ = "relation_types"
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    domain: Mapped[RelationDomain] = mapped_column(SAEnum(RelationDomain), index=True)
    category: Mapped[str] = mapped_column(String(32))  # right|encumbrance|restriction|topology|flow|accounting|commercial


class Relation(PKMixin, Bitemporal, Base):
    """Ребро графа. Само по себе не истина — истинность через assertions/evidences."""
    __tablename__ = "relations"

    from_entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), index=True)
    to_entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), index=True)
    relation_type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("relation_types.id"), index=True)
    domain: Mapped[RelationDomain] = mapped_column(SAEnum(RelationDomain), index=True)
    meta: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)

    assertions: Mapped[list["Assertion"]] = relationship(back_populates="relation", cascade="all, delete-orphan")


# Доменные расширения 1:1 (правило: не смешивать ownership и topology в одном ребре)
class LegalRelation(Base):
    __tablename__ = "legal_relation"
    relation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("relations.id", ondelete="CASCADE"), primary_key=True)
    legal_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    registration_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    registry_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    right_type_code: Mapped[str | None] = mapped_column(String(64), nullable=True)


class TechRelation(Base):
    __tablename__ = "tech_relation"
    relation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("relations.id", ondelete="CASCADE"), primary_key=True)
    material_type_in: Mapped[str | None] = mapped_column(String(128), nullable=True)
    material_type_out: Mapped[str | None] = mapped_column(String(128), nullable=True)
    max_throughput: Mapped[float | None] = mapped_column(Float, nullable=True)
    conversion_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    loss_factor: Mapped[float | None] = mapped_column(Float, nullable=True)


class SpatialRelation(Base):
    __tablename__ = "spatial_relation"
    relation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("relations.id", ondelete="CASCADE"), primary_key=True)
    spatial_operator: Mapped[str | None] = mapped_column(String(32), nullable=True)  # LOCATED_ON/INSIDE/INTERSECTS
    geometry_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("geometries.id", ondelete="SET NULL"), nullable=True)


class AccountingRelation(Base):
    """ОСВ-право. ON_BALANCE_OF / LEASED_IN_BALANCE. legal_owner != balance_holder допускается."""
    __tablename__ = "accounting_relation"
    relation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("relations.id", ondelete="CASCADE"), primary_key=True)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("subjects.id"), nullable=True)
    account_number: Mapped[str | None] = mapped_column(String(16), nullable=True)  # 01.01 / 01.03 / 01.К
    accounting_basis: Mapped[str | None] = mapped_column(String(255), nullable=True)
    osv_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)


class Assertion(PKMixin, Bitemporal, Base):
    __tablename__ = "assertions"
    relation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("relations.id", ondelete="CASCADE"), index=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    status: Mapped[AssertionStatus] = mapped_column(SAEnum(AssertionStatus), default=AssertionStatus.active, index=True)
    asserted_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    asserted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    relation: Mapped["Relation"] = relationship(back_populates="assertions")
    evidences: Mapped[list["Evidence"]] = relationship(back_populates="assertion", cascade="all, delete-orphan")

    __table_args__ = (CheckConstraint("confidence_score >= 0.0 AND confidence_score <= 1.0", name="ck_assertion_conf"),)


class Evidence(PKMixin, Base):
    __tablename__ = "evidences"
    assertion_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assertions.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[DataSourceType] = mapped_column(SAEnum(DataSourceType), index=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    weight: Mapped[float] = mapped_column(Float, default=0.5)
    extracted_data: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)

    assertion: Mapped["Assertion"] = relationship(back_populates="evidences")


def confidence_from_evidences(weights: list[float]) -> float:
    """Комбинация согласных доказательств: 1 - Π(1 - w). Конфликты резолвятся отдельно."""
    acc = 1.0
    for w in weights:
        acc *= (1.0 - max(0.0, min(1.0, w)))
    return round(1.0 - acc, 4)


# --------------------------------------------------------------------------- #
# §8 Геометрия
# --------------------------------------------------------------------------- #
class Geometry(PKMixin, Bitemporal, Base):
    __tablename__ = "geometries"
    entity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), index=True, nullable=True)
    cad_number: Mapped[str | None] = mapped_column(String(50), index=True, nullable=True)
    geometry_type: Mapped[str] = mapped_column(String(20))  # POINT/LINESTRING/POLYGON/MULTIPOLYGON
    coordinates_wkt: Mapped[str] = mapped_column(Text)
    geojson: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    bbox: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)  # {minx,miny,maxx,maxy}
    original_srid: Mapped[int | None] = mapped_column(Integer, nullable=True)  # напр. МСК-61
    srid: Mapped[int] = mapped_column(Integer, default=4326)  # WGS-84 для KMZ (C1)
    source_type: Mapped[DataSourceType | None] = mapped_column(SAEnum(DataSourceType), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)


# --------------------------------------------------------------------------- #
# §9 Технологический слой
# --------------------------------------------------------------------------- #
class Device(PKMixin, Bitemporal, Base):
    """КИП как ОС. Telemetry (сырьё) — вне проекта (TSDB), сюда не пишется."""
    __tablename__ = "devices"
    entity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entities.id"), nullable=True)
    device_type: Mapped[str] = mapped_column(String(32))  # scale/flowmeter/level_sensor/tracker
    serial: Mapped[str | None] = mapped_column(String(64), nullable=True)
    located_entity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entities.id"), nullable=True)
    geo_point: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    max_capacity: Mapped[float | None] = mapped_column(Float, nullable=True)  # для узлов-накопителей
    meta: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    # current_level НЕ хранится — считается из flow_events.


class FlowEvent(PKMixin, Base):
    """Нормализованное бизнес-событие потока. Маршрут — на ребре, динамика — здесь."""
    __tablename__ = "flow_events"
    relation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("relations.id", ondelete="CASCADE"), index=True)
    device_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"), nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    quantity: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(16))  # kg/l/pcs/t
    event_type: Mapped[FlowEventType] = mapped_column(SAEnum(FlowEventType), index=True)
    details: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)


# --------------------------------------------------------------------------- #
# §10 Субъекты (надстройка над §2 entity_registry)
# --------------------------------------------------------------------------- #
class Subject(PKMixin, Base):
    __tablename__ = "subjects"
    subject_type: Mapped[SubjectType] = mapped_column(SAEnum(SubjectType), index=True)
    inn: Mapped[str | None] = mapped_column(String(12), unique=True, index=True, nullable=True)
    ogrn: Mapped[str | None] = mapped_column(String(15), nullable=True)
    name_current: Mapped[str] = mapped_column(String(512), index=True)
    vat_mode: Mapped[VatMode] = mapped_column(SAEnum(VatMode), default=VatMode.OSNO)
    vat_rate: Mapped[float] = mapped_column(Float, default=20.0)
    vat_exemption_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)  # ст.149 НК РФ

    names: Mapped[list["SubjectName"]] = relationship(cascade="all, delete-orphan")
    bank_accounts: Mapped[list["BankAccount"]] = relationship(cascade="all, delete-orphan")


class SubjectName(PKMixin, Base):
    __tablename__ = "subject_names"
    subject_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), index=True)
    name_full: Mapped[str] = mapped_column(String(512))
    name_short: Mapped[str | None] = mapped_column(String(255), nullable=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)


class SubjectKpp(PKMixin, Base):
    __tablename__ = "subject_kpp"
    subject_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), index=True)
    kpp: Mapped[str] = mapped_column(String(9))
    is_main: Mapped[bool] = mapped_column(Boolean, default=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)


class BankAccount(PKMixin, Base):
    __tablename__ = "bank_accounts"
    subject_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), index=True)
    bank_name: Mapped[str] = mapped_column(String(255))
    bik: Mapped[str] = mapped_column(String(9))
    corr_account: Mapped[str] = mapped_column(String(20))
    settlement_account: Mapped[str] = mapped_column(String(20))
    opened_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    closed_at: Mapped[date | None] = mapped_column(Date, nullable=True)


class IpStatusPeriod(PKMixin, Base):
    __tablename__ = "ip_status_periods"
    subject_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), index=True)
    ogrnip: Mapped[str] = mapped_column(String(15))
    registered_at: Mapped[date] = mapped_column(Date)
    terminated_at: Mapped[date | None] = mapped_column(Date, nullable=True)


class SubjectExternalRef(PKMixin, Base):
    """Мост к innogrn.db (checko) / nma.db (ФИПС) — ADR-P03, НЕ уплощать."""
    __tablename__ = "subject_external_ref"
    subject_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), index=True)
    external_db: Mapped[str] = mapped_column(String(16))  # innogrn / nma
    external_key: Mapped[str] = mapped_column(String(32))  # inn / ogrn


# --------------------------------------------------------------------------- #
# §11 Коммерческий слой
# --------------------------------------------------------------------------- #
class LotSnapshot(PKMixin, Base):
    """Неизменяемый слепок живого лота. Источник для печатных форм/УПД/презентаций."""
    __tablename__ = "lot_snapshots"
    lot_id: Mapped[str] = mapped_column(String(256), index=True)  # FK→lots.lot_id (§6)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    frozen_data: Mapped[dict] = mapped_column(PortableJSON)
    xsd_version: Mapped[str] = mapped_column(String(20), default="5.03")
    reason: Mapped[str] = mapped_column(String(32))  # contract_signed / invoice_issued


class Order(PKMixin, Base):
    __tablename__ = "orders"
    lot_id: Mapped[str] = mapped_column(String(256), index=True)
    customer_subject_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("subjects.id"), nullable=True)
    assessor_subject_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("subjects.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Contract(PKMixin, Base):
    __tablename__ = "contracts"
    order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    executor_subject_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("subjects.id"), nullable=True)
    customer_subject_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("subjects.id"), nullable=True)
    tz_json: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    lot_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("lot_snapshots.id"), nullable=True)
    body_url: Mapped[str | None] = mapped_column(String(512), nullable=True)


class Invoice(PKMixin, Base):
    __tablename__ = "invoices"
    contract_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("contracts.id", ondelete="CASCADE"), index=True)
    number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    vat_amount: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(32), default="issued")


class UpdDocument(PKMixin, Base):
    """УПД. status=1 (с НДС) обязателен если supplier.vat_mode == USN_VAT (ответ 18)."""
    __tablename__ = "upd_documents"
    contract_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("contracts.id", ondelete="CASCADE"), index=True)
    number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[UpdStatus] = mapped_column(SAEnum(UpdStatus), default=UpdStatus.INVOICE_AND_PRIMARY)
    xml_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    xsd_version: Mapped[str] = mapped_column(String(20), default="5.03")
    validated: Mapped[bool] = mapped_column(Boolean, default=False)


# --------------------------------------------------------------------------- #
# §12 Документы и классификатор
# --------------------------------------------------------------------------- #
class Document(PKMixin, Base):
    __tablename__ = "documents"
    doc_type: Mapped[str] = mapped_column(String(64), index=True)  # см. DOC_CLASSIFIER_SPEC
    number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    issuer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    classifier_json: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    source_type: Mapped[DataSourceType | None] = mapped_column(SAEnum(DataSourceType), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    parsed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DocLink(PKMixin, Base):
    """Материализация «документ → какие сущности/поля обогащает»."""
    __tablename__ = "doc_links"
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    target_entity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entities.id", ondelete="SET NULL"), nullable=True)
    target_table: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_field: Mapped[str | None] = mapped_column(String(64), nullable=True)
    relation_code: Mapped[str] = mapped_column(String(32))  # ESTABLISHES / EVIDENCES / DEPICTS
    source_type: Mapped[DataSourceType | None] = mapped_column(SAEnum(DataSourceType), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
