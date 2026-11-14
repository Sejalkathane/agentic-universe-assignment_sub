import csv, json
from dataclasses import dataclass, field
from pathlib import Path
from .normalize import normalise_header


@dataclass
class Field:
    name: str
    type: str
    required: bool = False
    pii: bool = False
    reference: bool = False
    aliases: list = field(default_factory=list)
    values: list = field(default_factory=list)
    default: object = None

    @classmethod
    def from_json(cls, d):  # the ONLY place that knows the JSON shape
        return cls(d["name"], d["type"], bool(d.get("required")), bool(d.get("pii")),
                   bool(d.get("reference")), d.get("aliases", []),
                   d.get("values", d.get("enum", [])), d.get("default"))


@dataclass
class Schema:
    workflow_id: str
    fields: list

    @property
    def identity_phone(self):
        return next(f for f in self.fields if f.type == "phone")

    @property
    def reference_field(self):
        return next((f for f in self.fields if f.reference), None)

    def map_headers(self, header):
        norm = [normalise_header(h) for h in header]
        out = {}
        for f in self.fields:
            names = {normalise_header(n) for n in [f.name, *f.aliases]}
            for i, n in enumerate(norm):
                if n in names:
                    out[f.name] = i
                    break
        return out


def load_schemas(directory) -> dict:
    out = {}
    for p in sorted(Path(directory).glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        wf = d.get("workflow_id", p.stem)
        out[wf] = Schema(wf, [Field.from_json(f) for f in d["fields"]])
    return out


class Catalogue:
    def __init__(self, path):
        self._d = {}
        truthy = lambda v: str(v).strip().lower() in ("true", "1", "yes")
        with open(path, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                code = r.get("disposition_code") or r.get("code")
                self._d[(r.get("workflow_id") or None, code)] = (
                    truthy(r["is_terminal"]), truthy(r["is_success"]))

    def get(self, wf, code):
        return self._d.get((wf, code)) or self._d.get((None, code))

    def is_terminal(self, wf, code):
        return (self.get(wf, code) or (False, False))[0]

    def is_success(self, wf, code):
        return (self.get(wf, code) or (False, False))[1]