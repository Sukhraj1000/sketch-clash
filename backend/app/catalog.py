"""Canonical identity is object kind; a reusable render template is a separate choice."""
from __future__ import annotations

from copy import deepcopy
import asyncio
import inspect
import re
import unicodedata
from typing import Any

CATALOG_VERSION = "1"


def normalize_key(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold().strip()
    value = re.sub(r"[^a-z0-9\s-]", " ", value)
    return re.sub(r"[\s-]+", "-", value).strip("-")[:64]


def _type(key: str, aliases: list[str], description: str, template: str = "generic", archetype: str = "Quick") -> dict:
    return {"canonical_type_id": key, "canonical_key": key, "display_name": key.replace("-", " ").title(),
            "aliases": aliases, "description": description, "template_id": template,
            "approved_archetypes": ["Quick", "Power", "Guard"], "default_archetype": archetype,
            "approved": True, "catalog_version": CATALOG_VERSION}


CHARACTER_TYPES = [
    _type("mug", ["coffee mug", "tea mug", "ceramic mug", "drinking mug"], "A handled drinking vessel with an open top and a short cylindrical body.", "mug", "Guard"),
    _type("bottle", ["water bottle", "drinks bottle", "glass bottle", "plastic bottle", "flask"], "A tall container with a narrow neck and a cap or opening for liquids.", "bottle", "Quick"),
    _type("cup", ["drinking cup", "paper cup", "plastic cup"], "An open drinking vessel. A handle is not required; do not merge automatically with a mug.", "generic", "Guard"),
    _type("plant", ["potted plant", "houseplant", "house plant"], "A living plant with leaves or stems, often in a pot.", "plant", "Guard"),
    _type("book", ["paperback", "hardback", "hardcover", "textbook"], "A bound stack of pages with a cover and spine.", "book", "Guard"),
    _type("ball", ["football", "soccer ball", "basketball", "tennis ball"], "A round object used for sport or play.", "ball", "Quick"),
    _type("phone", ["mobile phone", "cell phone", "smartphone", "iphone"], "A handheld rectangular electronic communication device with a screen."),
    _type("laptop", ["notebook computer", "macbook"], "A portable computer with an attached folding screen and keyboard.", archetype="Guard"),
    _type("keyboard", ["computer keyboard"], "An arrangement of keys used to enter text into a computer."),
    _type("mouse", ["computer mouse"], "A small handheld computer pointing device with buttons."),
    _type("pen", ["ballpoint pen", "fountain pen"], "A slim handheld implement that writes with ink."),
    _type("pencil", ["colour pencil", "colored pencil"], "A slim writing implement containing a solid graphite or pigment core."),
    _type("spoon", ["teaspoon", "tablespoon"], "A utensil with a handle and small shallow bowl."),
    _type("bowl", [], "A round open container with a concave interior.", archetype="Guard"),
    _type("plate", ["dinner plate"], "A broad shallow dish for food.", archetype="Guard"),
    _type("chair", ["office chair", "dining chair"], "A seat with a back and support legs.", archetype="Guard"),
    _type("shoe", ["trainer", "sneaker"], "An item of footwear with a sole and enclosed upper."),
    _type("headphones", ["headset"], "A pair of audio earpieces connected by a headband."),
    _type("scissors", [], "A handheld cutting tool with two pivoting blades and finger loops."),
    _type("remote-control", ["remote", "tv remote"], "A small handheld controller with buttons for an electronic device."),
    _type("apple", [], "A rounded fruit with smooth skin and often a short stem.", "generic", "Power"),
]


class CharacterCatalog:
    def __init__(self, collection: Any = None, retriever: Any = None):
        self.collection = collection
        self.retriever = retriever
        self._aliases = {}
        for record in CHARACTER_TYPES:
            for alias in [record["canonical_key"], *record["aliases"]]:
                self._aliases[normalize_key(alias)] = record

    async def resolve_character_type(self, candidate: str, description: str = "", *, semantic_search: bool = True) -> dict:
        key = normalize_key(candidate)
        if key in {"", "object", "thing", "item", "unknown", "generic", "unidentified", "unclear"}:
            return {"valid": False, "errors": ["The visible object needs a specific object-kind label."], "related": []}
        if key in self._aliases:
            return {"valid": True, "match": "exact_or_alias", "record": deepcopy(self._aliases[key]),
                    "related": [], "retrieval": {"status": "skipped", "detail": "Exact canonical type resolved."}}
        if self.collection is not None:
            # Catalogue records only. This read never grants ownership or inserts a resident.
            query = {"approved": True, "$or": [{"canonical_key": key}, {"normalized_aliases": key}]}
            projection = {"_id": 0, "embedding": 0}
            if inspect.iscoroutinefunction(self.collection.find_one):
                found = await self.collection.find_one(query, projection)
            else:
                found = await asyncio.to_thread(self.collection.find_one, query, projection)
            if found:
                return {"valid": True, "match": "exact_or_alias", "record": found, "related": [],
                        "retrieval": {"status": "skipped", "detail": "Exact persisted type resolved."}}
        retrieval = {"status": "unavailable", "detail": "Atlas semantic retrieval is not configured.", "candidates": []}
        if not semantic_search:
            retrieval = {'status': 'skipped', 'detail': 'This pipeline uses exact names and aliases; optional semantic template search is not requested.', 'candidates': []}
        elif self.retriever is not None:
            retrieval = await self.retriever.search(description or candidate)
        # Similarity proposes reusable templates; it must never silently merge canonical identity.
        record = _type(key, [], description[:600] or candidate)
        record["identity_basis"] = "new_normalized_object_kind"
        return {"valid": True, "match": "new_type", "record": record,
                "related": retrieval.get("candidates", []), "retrieval": retrieval,
                "note": "Related records express similarity, not identity or ownership."}

    async def ensure_type(self, record: dict) -> None:
        """Persist accepted kind metadata only; never insert world membership here."""
        if self.collection is None:
            return
        entry = deepcopy(record)
        entry["normalized_aliases"] = [normalize_key(alias) for alias in entry.get("aliases", [])]
        query = {"canonical_key": entry["canonical_key"]}
        update = {"$setOnInsert": entry}
        if inspect.iscoroutinefunction(self.collection.update_one):
            await self.collection.update_one(query, update, upsert=True)
        else:
            await asyncio.to_thread(self.collection.update_one, query, update, upsert=True)

    @staticmethod
    def seed_records() -> list[dict]:
        records = deepcopy(CHARACTER_TYPES)
        for record in records:
            record["normalized_aliases"] = [normalize_key(alias) for alias in record["aliases"]]
        return records
