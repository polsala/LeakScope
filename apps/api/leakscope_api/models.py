from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Host(Base):
    __tablename__ = "hosts"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    metadata_json: Mapped[dict] = mapped_column(JSON)


class Process(Base):
    __tablename__ = "processes"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    host_id: Mapped[str] = mapped_column(ForeignKey("hosts.id"))
    pid: Mapped[int] = mapped_column(Integer, index=True)
    last_seen: Mapped[float] = mapped_column(Float)
    metadata_json: Mapped[dict] = mapped_column(JSON)


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String, unique=True)
    process_key: Mapped[str] = mapped_column(ForeignKey("processes.key"))
    state: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[float] = mapped_column(Float)
    ended_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    config: Mapped[dict] = mapped_column(JSON)
    quality: Mapped[dict] = mapped_column(JSON)
    last_sequence: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str] = mapped_column(Text, default="")


class ProcessSample(Base):
    __tablename__ = "process_samples"
    __table_args__ = (UniqueConstraint("session_id", "sequence"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    process_key: Mapped[str] = mapped_column(String)
    sequence: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[float] = mapped_column(Float, index=True)
    data: Mapped[dict] = mapped_column(JSON)


class Marker(Base):
    __tablename__ = "markers"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    timestamp: Mapped[float] = mapped_column(Float)
    name: Mapped[str] = mapped_column(String)
    metadata_json: Mapped[dict] = mapped_column(JSON)


class Investigation(Base):
    __tablename__ = "investigations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"))
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[float] = mapped_column(Float)


class Hypothesis(Base):
    __tablename__ = "hypotheses"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id"))
    evidence: Mapped[dict] = mapped_column(JSON)


class Comparison(Base):
    __tablename__ = "comparisons"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[float] = mapped_column(Float)
    config: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"))
    title: Mapped[str] = mapped_column(String)
    created_at: Mapped[float] = mapped_column(Float)
    document: Mapped[dict] = mapped_column(JSON)
    html: Mapped[str] = mapped_column(Text)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[float] = mapped_column(Float, index=True)
    role: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    entity: Mapped[str] = mapped_column(String)


class Role(Base):
    __tablename__ = "roles"
    name: Mapped[str] = mapped_column(String, primary_key=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    role: Mapped[str] = mapped_column(ForeignKey("roles.name"))
    token_hash: Mapped[str] = mapped_column(String, unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class SystemSetting(Base):
    __tablename__ = "system_settings"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


class GCTypeSnapshot(Base):
    __tablename__ = "gc_type_snapshots"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    timestamp: Mapped[float] = mapped_column(Float)
    snapshot: Mapped[dict] = mapped_column(JSON)


class CallStack(Base):
    __tablename__ = "call_stacks"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    frames: Mapped[list] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String)


class Frame(Base):
    __tablename__ = "frames"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    module: Mapped[str] = mapped_column(String)
    symbol: Mapped[str | None] = mapped_column(String, nullable=True)
    line: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AllocationEventIndex(Base):
    __tablename__ = "allocation_event_indexes"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"))
    chunk_offset: Mapped[int] = mapped_column(Integer)
    first_sequence: Mapped[int] = mapped_column(Integer)
    last_sequence: Mapped[int] = mapped_column(Integer)
