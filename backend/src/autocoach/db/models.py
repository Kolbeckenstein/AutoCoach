"""SQLAlchemy ORM models for post metadata and comments."""

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class PostRecord(Base):
    """Persisted metadata for a scraped r/formcheck post."""

    __tablename__ = "posts"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    lift_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    video_url: Mapped[str] = mapped_column(Text, nullable=False)
    video_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str] = mapped_column(String(100), nullable=False)
    post_score: Mapped[int] = mapped_column(Integer, nullable=False)
    created_utc: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    comments: Mapped[list["CommentRecord"]] = relationship(
        back_populates="post",
        cascade="all, delete-orphan",
    )


class CommentRecord(Base):
    """Persisted Reddit comment attached to a scraped post."""

    __tablename__ = "comments"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    post_id: Mapped[str] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    author: Mapped[str] = mapped_column(String(100), nullable=False)
    created_utc: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_top_level: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    post: Mapped["PostRecord"] = relationship(back_populates="comments")
