"""Read-only Google inventory composition and same-turn referent issuance candidate."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING

from global_hybrid_v2.adapters.controlled_responses import ServerTurnContext
from global_hybrid_v2.adapters.google_vehicle_control import (
    COMPANY_INVENTORY_RANGE,
    COMPANY_INVENTORY_SPREADSHEET_ID,
)
from global_hybrid_v2.google_auth import GoogleAuthUnavailable
from global_hybrid_v2.inventory_identity import (
    AuthoritativeInventoryResolver,
    GoogleInventorySource,
    InventoryIdentityHold,
    InventoryResolution,
    InventorySnapshot,
    TrustedTurnReferent,
    read_current_snapshot,
)
from global_hybrid_v2.settings import Settings

if TYPE_CHECKING:
    from global_hybrid_v2.inventory_identity import InventoryObservation


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).casefold()).strip()


def _request_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _descriptor(observation: InventoryObservation) -> str | None:
    cells = observation.cells + ("",) * max(0, 6 - len(observation.cells))
    make, year, model = (_normalized(cells[3]), _normalized(cells[4]), _normalized(cells[5]))
    if not make or not re.fullmatch(r"\d{4}", year) or not model:
        return None
    return f"{year} {make} {model}"


def _mentioned(request_text: str, descriptor: str) -> bool:
    request = _normalized(request_text)
    pattern = r"(?<![\w-])" + re.escape(descriptor) + r"(?![\w-])"
    return re.search(pattern, request) is not None


class TrustedTurnReferentIssuer:
    """Server-owned, process-local same-turn seal; never trusts caller field payloads."""

    def __init__(self) -> None:
        self._key = secrets.token_bytes(32)

    def _seal(self, referent: TrustedTurnReferent) -> str:
        payload = "\0".join((referent.conversation_id, referent.turn_id,
                             referent.request_digest, referent.make,
                             referent.model_year, referent.model, referent.source_owner,
                             referent.source_currentness_token,
                             referent.source_observation_id)).encode("utf-8")
        return hmac.new(self._key, payload, hashlib.sha256).hexdigest()

    def issue(self, *, turn: ServerTurnContext, request_text: str,
              snapshot: InventorySnapshot) -> TrustedTurnReferent:
        if not turn.conversation_id or not turn.turn_id or not request_text.strip():
            raise InventoryIdentityHold("HOLD_TRUSTED_REFERENT_SCOPE_MISMATCH")
        matches = [(item, descriptor) for item in snapshot.observations
                   if (descriptor := _descriptor(item)) and _mentioned(request_text, descriptor)]
        if len(matches) > 1:
            raise InventoryIdentityHold("HOLD_IDENTITY_CONFLICT")
        if not matches:
            if re.search(r"這台|剛才那台|那輛|那台", request_text):
                raise InventoryIdentityHold("HOLD_REFERENT_UNBOUND")
            raise InventoryIdentityHold("HOLD_REFERENT_NOT_FOUND")
        observation, _ = matches[0]
        cells = observation.cells
        referent = TrustedTurnReferent(
            turn.conversation_id, turn.turn_id, cells[3].strip(), cells[4].strip(),
            cells[5].strip(), "LIBRARY", _request_digest(request_text),
            snapshot.currentness_token, observation.observation_id,
        )
        return TrustedTurnReferent(**{**referent.__dict__, "issuer_seal": self._seal(referent)})

    def verify(self, referent: TrustedTurnReferent, *, turn: ServerTurnContext,
               request_text: str, snapshot: InventorySnapshot) -> None:
        if (referent.conversation_id != turn.conversation_id or
                referent.turn_id != turn.turn_id or
                referent.request_digest != _request_digest(request_text) or
                referent.source_currentness_token != snapshot.currentness_token or
                not referent.issuer_seal or
                not hmac.compare_digest(referent.issuer_seal, self._seal(referent))):
            raise InventoryIdentityHold("HOLD_TRUSTED_REFERENT_SCOPE_MISMATCH")
        matching = [item for item in snapshot.observations
                    if item.observation_id == referent.source_observation_id]
        if (len(matching) != 1 or _descriptor(matching[0]) is None or
                not _mentioned(request_text, _descriptor(matching[0]) or "")):
            raise InventoryIdentityHold("HOLD_TRUSTED_REFERENT_SCOPE_MISMATCH")


@dataclass(frozen=True)
class InventoryRuntime:
    source: GoogleInventorySource
    issuer: TrustedTurnReferentIssuer

    def read_snapshot(self) -> InventorySnapshot:
        return read_current_snapshot(self.source)

    def resolve_issued(self, *, referent: TrustedTurnReferent, turn: ServerTurnContext,
                       request_text: str, snapshot: InventorySnapshot,
                       resolver: AuthoritativeInventoryResolver) -> InventoryResolution:
        self.issuer.verify(referent, turn=turn, request_text=request_text, snapshot=snapshot)
        current = self.read_snapshot()
        if current.currentness_token != snapshot.currentness_token:
            raise InventoryIdentityHold("HOLD_TRUSTED_REFERENT_SCOPE_MISMATCH")
        self.issuer.verify(referent, turn=turn, request_text=request_text, snapshot=current)
        return resolver.resolve(referent, current)


def configured_inventory_runtime(settings: Settings) -> InventoryRuntime:
    """Construct without network I/O; never uses an alternate credential or fallback."""
    credential = settings.google_service_account_json
    if credential is None:
        raise InventoryIdentityHold("INVENTORY_SOURCE_BINDING_UNAVAILABLE")
    try:
        source = GoogleInventorySource.from_service_account_json(credential.get_secret_value())
    except GoogleAuthUnavailable as exc:
        raise InventoryIdentityHold("INVENTORY_SOURCE_BINDING_UNAVAILABLE") from exc
    return InventoryRuntime(source, TrustedTurnReferentIssuer())


def inventory_binding_readback(settings: Settings, runtime: InventoryRuntime | None) -> dict:
    """Bounded configuration readback; it does not claim authenticated Google access."""
    bound = (isinstance(runtime, InventoryRuntime) and
             isinstance(runtime.source, GoogleInventorySource) and
             isinstance(runtime.issuer, TrustedTurnReferentIssuer) and
             settings.google_service_account_json is not None)
    return {
        "inventory_source": "BOUND" if bound else "UNBOUND",
        "inventory_file_id": COMPANY_INVENTORY_SPREADSHEET_ID,
        "inventory_sheet_name": "車源",
        "inventory_read_scope": COMPANY_INVENTORY_RANGE,
        "credential_present": settings.google_service_account_json is not None,
        "trusted_referent_issuer": "BOUND" if bound else "UNBOUND",
        "durable_identity_evidence": "UNBOUND",
        "root_a": "UNBOUND",
    }
