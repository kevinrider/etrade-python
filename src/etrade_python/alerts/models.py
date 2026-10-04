"""Typed alert request and response models."""

from datetime import datetime
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from etrade_python._dates import parse_broker_datetime


class BrokerModel(BaseModel):
    """Base model that preserves unmodeled broker fields."""

    model_config = ConfigDict(extra="allow", frozen=True, populate_by_name=True)

    broker_metadata: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        extra = cast(dict[str, Any], getattr(self, "__pydantic_extra__", None) or {})
        if extra:
            object.__setattr__(self, "broker_metadata", {**self.broker_metadata, **extra})
            object.__setattr__(self, "__pydantic_extra__", {})


def _bool_query(value: bool | None) -> str | None:
    if value is None:
        return None
    return "true" if value else "false"


class AlertsRequest(BaseModel):
    """Query parameters for alert list lookup."""

    model_config = ConfigDict(frozen=True)

    count: int | None = Field(default=None, ge=1, le=300)
    category: str | None = None
    status: str | None = None
    direction: str | None = None
    search: str | None = None

    @field_validator("category")
    @classmethod
    def valid_category(cls, value: str | None) -> str | None:
        return _normalize_choice(value, {"STOCK", "ACCOUNT"}, "category")

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str | None) -> str | None:
        return _normalize_choice(value, {"READ", "UNREAD", "DELETED"}, "status")

    @field_validator("direction")
    @classmethod
    def valid_direction(cls, value: str | None) -> str | None:
        return _normalize_choice(value, {"ASC", "DESC"}, "direction")

    @field_validator("search")
    @classmethod
    def nonempty_search(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("A nonempty value is required")
        return value

    def query_params(self) -> dict[str, str | int | None]:
        return {
            "count": self.count,
            "category": self.category,
            "status": self.status,
            "direction": self.direction,
            "search": self.search,
        }


class AlertDetailsRequest(BaseModel):
    """Query parameters for alert details lookup."""

    model_config = ConfigDict(frozen=True)

    html_tags: bool | None = Field(default=None, alias="htmlTags")

    def query_params(self) -> dict[str, str | None]:
        return {"htmlTags": _bool_query(self.html_tags)}


class Alert(BrokerModel):
    id: int | None = None
    create_time: datetime | None = Field(default=None, alias="createTime")
    subject: str | None = None
    status: str | None = None

    @field_validator("create_time", mode="before")
    @classmethod
    def parse_create_time(cls, value: object) -> datetime | None:
        return _parse_alert_time(value)


class AlertDetailsResponse(Alert):
    msg_text: str | None = Field(default=None, alias="msgText")
    read_time: datetime | None = Field(default=None, alias="readTime")
    delete_time: datetime | None = Field(default=None, alias="deleteTime")
    symbol: str | None = None
    next: str | None = None
    prev: str | None = None

    @field_validator("read_time", "delete_time", mode="before")
    @classmethod
    def parse_optional_times(cls, value: object) -> datetime | None:
        return _parse_alert_time(value)


def _empty_alerts() -> list[Alert]:
    return []


class AlertsResponse(BrokerModel):
    total_alerts: int | None = Field(default=None, alias="totalAlerts")
    alerts: list[Alert] = Field(default_factory=_empty_alerts, alias="alerts")

    @model_validator(mode="before")
    @classmethod
    def normalize_response(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(cast(dict[str, Any], value))
        for source in ("Alert", "alert"):
            if source in data and "alerts" not in data:
                data["alerts"] = data[source]
            data.pop(source, None)
        return data

    @field_validator("alerts", mode="before")
    @classmethod
    def normalize_alerts(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, dict):
            return [cast(dict[str, Any], value)]
        return value


def _empty_failed_alert_ids() -> list[int]:
    return []


class FailedAlerts(BrokerModel):
    alert_ids: list[int] = Field(default_factory=_empty_failed_alert_ids, alias="alertId")

    @field_validator("alert_ids", mode="before")
    @classmethod
    def normalize_alert_ids(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, int):
            return [value]
        return value


class DeleteAlertsResponse(BrokerModel):
    result: str | None = None
    failed_alerts: FailedAlerts | None = Field(default=None, alias="failedAlerts")

    @model_validator(mode="before")
    @classmethod
    def normalize_response(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(cast(dict[str, Any], value))
        if "FailedAlerts" in data and "failedAlerts" not in data:
            data["failedAlerts"] = data["FailedAlerts"]
        data.pop("FailedAlerts", None)
        return data


def _normalize_choice(value: str | None, choices: set[str], label: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if not normalized:
        raise ValueError("A nonempty value is required")
    if normalized not in choices:
        raise ValueError(f"Unsupported alert {label}")
    return normalized


def _parse_alert_time(value: object) -> datetime | None:
    if value in (None, "", 0, "0"):
        return None
    return parse_broker_datetime(value)
