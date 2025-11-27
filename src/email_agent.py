from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PyPDF2 import PdfReader

if TYPE_CHECKING:
    from openai import OpenAI


@dataclass
class ProfileBase:
    name: str
    raw_text: str
    education: list[str]
    experiences: list[str]
    skills: list[str]
    projects: list[str]


@dataclass
class SenderProfile(ProfileBase):
    motivation: str
    ask: str

    @classmethod
    def from_json(cls, path: Path) -> "SenderProfile":
        data = _load_json(path)
        return cls(
            name=_require_field(data, "name", path),
            raw_text=_require_field(data, "raw_text", path),
            education=_load_str_list(data, "education", path),
            experiences=_load_str_list(data, "experiences", path),
            skills=_load_str_list(data, "skills", path),
            projects=_load_str_list(data, "projects", path),
            motivation=_require_field(data, "motivation", path),
            ask=_require_field(data, "ask", path),
        )

    @classmethod
    def from_pdf(
        cls,
        pdf_path: Path,
        *,
        motivation: str,
        ask: str,
        model: str = "gpt-4o-mini",
        client: "OpenAI" | None = None,
    ) -> "SenderProfile":
        motivation_text = motivation.strip()
        ask_text = ask.strip()
        if not motivation_text or not ask_text:
            raise ValueError("Both motivation and ask are required when loading profiles from PDF")

        profile = extract_profile_from_pdf(pdf_path, model=model, client=client)
        return cls(
            name=profile.name,
            raw_text=profile.raw_text,
            education=profile.education,
            experiences=profile.experiences,
            skills=profile.skills,
            projects=profile.projects,
            motivation=motivation_text,
            ask=ask_text,
        )


@dataclass
class ReceiverProfile(ProfileBase):
    context: str | None = None

    @classmethod
    def from_json(cls, path: Path) -> "ReceiverProfile":
        data = _load_json(path)
        return cls(
            name=_require_field(data, "name", path),
            raw_text=_require_field(data, "raw_text", path),
            education=_load_str_list(data, "education", path),
            experiences=_load_str_list(data, "experiences", path),
            skills=_load_str_list(data, "skills", path),
            projects=_load_str_list(data, "projects", path),
            context=data.get("context"),
        )

    @classmethod
    def from_pdf(
        cls,
        pdf_path: Path,
        *,
        model: str = "gpt-4o-mini",
        client: "OpenAI" | None = None,
        context: str | None = None,
    ) -> "ReceiverProfile":
        profile = extract_profile_from_pdf(pdf_path, model=model, client=client)
        return cls(
            name=profile.name,
            raw_text=profile.raw_text,
            education=profile.education,
            experiences=profile.experiences,
            skills=profile.skills,
            projects=profile.projects,
            context=context.strip() if isinstance(context, str) and context.strip() else None,
        )


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Failed to parse JSON in {path}: {exc}") from exc


def _require_field(data: dict[str, Any], key: str, source: Path | str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"Field '{key}' is required and must be a non-empty string in {source}"
        )
    return value.strip()


def _load_str_list(data: dict[str, Any], key: str, source: Path | str) -> list[str]:
    value = data.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"Field '{key}' must be a list of strings in {source}")
    cleaned: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            cleaned.append(item.strip())
    return cleaned


def extract_text_from_pdf(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    pages_text = [page.extract_text() or "" for page in reader.pages]
    combined = "\n".join(text.strip() for text in pages_text if text and text.strip())
    cleaned = combined.strip()
    if not cleaned:
        raise ValueError(f"No extractable text found in PDF {pdf_path}")
    return cleaned


def _profile_from_dict(profile_data: dict[str, Any], *, raw_text: str) -> ProfileBase:
    return ProfileBase(
        name=_require_field(profile_data, "name", "extracted profile"),
        raw_text=raw_text,
        education=_load_str_list(profile_data, "education", "extracted profile"),
        experiences=_load_str_list(profile_data, "experiences", "extracted profile"),
        skills=_load_str_list(profile_data, "skills", "extracted profile"),
        projects=_load_str_list(profile_data, "projects", "extracted profile"),
    )


def extract_profile_from_text(
    resume_text: str, *, model: str = "gpt-4o-mini", client: "OpenAI" | None = None
) -> ProfileBase:
    cleaned_text = resume_text.strip()
    if not cleaned_text:
        raise ValueError("Resume text must be a non-empty string")

    system_message = {
        "role": "system",
        "content": (
            "Extract a structured profile from the provided resume text. "
            "Return strict JSON with the keys: name (string), education (list of strings), "
            "experiences (list of strings), skills (list of strings), projects (list of strings)."
        ),
    }
    user_message = {
        "role": "user",
        "content": f"Resume text:\n{cleaned_text}\n\nReturn JSON only.",
    }

    from openai import OpenAI

    api_client = client or OpenAI()
    completion = api_client.chat.completions.create(
        model=model,
        messages=[system_message, user_message],
        response_format={"type": "json_object"},
    )
    content = completion.choices[0].message.content
    if not content:
        raise RuntimeError("OpenAI response did not contain any content")
    try:
        profile_data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse profile extraction response as JSON: {exc}") from exc

    return _profile_from_dict(profile_data, raw_text=cleaned_text)


def extract_profile_from_pdf(
    pdf_path: Path, *, model: str = "gpt-4o-mini", client: "OpenAI" | None = None
) -> ProfileBase:
    pdf_text = extract_text_from_pdf(pdf_path)
    return extract_profile_from_text(pdf_text, model=model, client=client)


def build_prompt(sender: SenderProfile, receiver: ReceiverProfile, goal: str) -> list[dict[str, str]]:
    goal_text = goal.strip()
    if not goal_text:
        raise ValueError("Goal must be a non-empty string")

    def _format_section(title: str, items: list[str]) -> str:
        if not items:
            return f"- {title}: (not specified)\n"
        bullet_points = "\n".join(f"  • {item}" for item in items)
        return f"- {title}:\n{bullet_points}\n"

    system_message = {
        "role": "system",
        "content": (
            "You craft sincere, concise first-contact cold emails that help two people build a genuine connection. "
            "Use the provided sender and receiver details to highlight authentic overlaps and mutual value. "
            "Output a complete email with a Subject line and body that is ready to paste into an email client."
        ),
    }

    user_message = {
        "role": "user",
        "content": (
            "Sender profile:\n"
            f"- Name: {sender.name}\n"
            f"- Motivation: {sender.motivation}\n"
            f"- Ask: {sender.ask}\n"
            + _format_section("Education", sender.education)
            + _format_section("Experiences", sender.experiences)
            + _format_section("Skills", sender.skills)
            + _format_section("Projects", sender.projects)
            + "Sender background (free text):\n"
            + f"{sender.raw_text}\n\n"
            + "Receiver profile:\n"
            + f"- Name: {receiver.name}\n"
            + (f"- Context: {receiver.context}\n" if receiver.context else "")
            + _format_section("Education", receiver.education)
            + _format_section("Experiences", receiver.experiences)
            + _format_section("Skills", receiver.skills)
            + _format_section("Projects", receiver.projects)
            + "Receiver background (free text):\n"
            + f"{receiver.raw_text}\n\n"
            + f"Goal: {goal_text}\n\n"
            + "Please return:\n"
            + "1) A concise, specific subject line\n"
            + "2) A short email body (max ~200 words) that feels human, references shared interests or context, and ends with a clear but polite call to action."
        ),
    }

    return [system_message, user_message]


def generate_email(
    sender: SenderProfile,
    receiver: ReceiverProfile,
    goal: str,
    *,
    model: str = "gpt-4o-mini",
    client: "OpenAI" | None = None,
) -> str:
    messages = build_prompt(sender, receiver, goal)
    from openai import OpenAI

    api_client = client or OpenAI()
    completion = api_client.chat.completions.create(model=model, messages=messages)
    content = completion.choices[0].message.content
    if not content:
        raise RuntimeError("OpenAI response did not contain any content")
    return content.strip()
