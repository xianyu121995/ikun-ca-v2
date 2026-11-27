"""Normalized drafts. Facts come from a parsed source; nothing here is invented."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Milestone:
    key: str
    label: str
    start_utc: str | None
    end_utc: str | None
    display: str
    timezone_label: str
    precision: str
    source_url: str


@dataclass
class Project:
    key: str
    name: str
    role: str
    place: str
    track: str
    url: str
    source_url: str
    note: str = ""


@dataclass
class Link:
    label: str
    url: str


@dataclass
class EventDraft:
    id: str
    title: str
    classification: str
    classification_reason: str
    ecosystem: str = "bnb"
    summary: str = ""
    location: str = ""
    prize: str = ""
    official_status: str | None = None
    start_utc: str | None = None
    end_utc: str | None = None
    submission_state: str = "not_published"
    submission_note: str = ""
    submission_form_url: str | None = None
    results_state: str = "not_published"
    results_note: str = ""
    milestones: list[Milestone] = field(default_factory=list)
    projects: list[Project] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    touch_results: bool = True
    touch_submission: bool = True

    def milestone_sources(self) -> set[str]:
        return {item.source_url for item in self.milestones if item.source_url}

    def project_sources(self) -> set[str]:
        return {item.source_url for item in self.projects if item.source_url}
