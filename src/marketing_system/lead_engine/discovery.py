"""
Dynamic Multi-Source Discovery Engine for Minh Van Logistics.
Fetches high-intent prospects across Apollo, Business Directories, and Trade Manifest patterns.
Replaces static hardcoded lead lists with dynamic queryable discovery.

INVARIANT: Production discovery NEVER falls back to synthetic or fixture data.
If an external API is unconfigured, timed out, or failing, the provider returns an
empty result with structured error status, preventing synthetic data from entering production.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from ..constants import Environment
from ..models import LeadCandidate, EvidenceStatus, utc_now

logger = logging.getLogger(__name__)


class DiscoveryFilter(BaseModel):
    industry_keywords: List[str] = Field(default_factory=lambda: ["medical", "thiết bị y tế", "dược phẩm", "linh kiện điện tử"])
    industry_codes: List[str] = Field(default_factory=lambda: ["3250", "2611", "4651", "4659"])
    trade_lanes: List[str] = Field(default_factory=lambda: ["JP-VN", "KR-VN", "CN-VN", "EU-VN"])
    destination_airports: List[str] = Field(default_factory=lambda: ["SGN", "HAN"])
    min_volume_kg: int = 200
    location: str = "Vietnam"
    limit: int = 25


class DiscoveryResult(BaseModel):
    total_discovered: int
    candidates: List[LeadCandidate]
    sources_used: List[str]
    source_statuses: Dict[str, str] = Field(default_factory=dict)
    filter_applied: DiscoveryFilter


class BaseDiscoveryProvider(ABC):
    name: str = "base"

    @abstractmethod
    def discover(self, filter_spec: DiscoveryFilter, env: Environment) -> List[LeadCandidate]:
        raise NotImplementedError

    def get_status(self, env: Environment) -> str:
        return "READY"


class ApolloDiscoveryProvider(BaseDiscoveryProvider):
    """
    Live Apollo B2B discovery provider.
    In PRODUCTION/STAGING, only queries the live connector.
    If the connector is unconfigured or fails, returns an empty list and logs the status.
    Never injects mock records into production datasets.
    """
    name: str = "apollo"

    def __init__(self, apollo_connector=None):
        self.connector = apollo_connector
        self.last_status: str = "INITIALIZED"

    def get_status(self, env: Environment) -> str:
        if self.connector and hasattr(self.connector, "configured") and self.connector.configured():
            return "CONFIGURED_LIVE"
        if env in (Environment.PRODUCTION, Environment.SANDBOX):
            return "NOT_CONFIGURED"
        return "MOCK_AVAILABLE"

    def discover(self, filter_spec: DiscoveryFilter, env: Environment) -> List[LeadCandidate]:
        candidates: List[LeadCandidate] = []

        # 1. Live Connector Query Path
        if self.connector and hasattr(self.connector, "configured") and self.connector.configured():
            try:
                query = " ".join(filter_spec.industry_keywords[:2])
                results = self.connector.search_people(q_keywords=query, per_page=filter_spec.limit)
                for item in (results or []):
                    org = item.get("organization", {})
                    company_name = org.get("name") or item.get("company_name", "")
                    if not company_name:
                        continue
                    c = LeadCandidate(
                        company=company_name,
                        domain=org.get("primary_domain") or item.get("domain"),
                        contact_name=item.get("name") or f"{item.get('first_name', '')} {item.get('last_name', '')}".strip(),
                        title=item.get("title"),
                        email=item.get("email"),
                        phone=item.get("phone_number") or org.get("phone"),
                        source="apollo",
                        environment=env,
                        synthetic=False,
                        stage="DISCOVERING"
                    )
                    # Raw observation from Apollo is SOURCE_OBSERVED, NOT verified
                    c.add_evidence(
                        field_name="company_profile",
                        field_value={"name": company_name, "domain": c.domain},
                        source_provider="apollo",
                        evidence_status=EvidenceStatus.SOURCE_OBSERVED,
                        confidence=0.80
                    )
                    candidates.append(c)
                self.last_status = "SUCCESS"
                return candidates[:filter_spec.limit]
            except Exception as e:
                logger.error("Apollo live discovery query failed: %s", e)
                self.last_status = f"ERROR: {e}"
                # CRITICAL INVARIANT: In production or staging, NEVER fall back to fixtures on error!
                return []

        # 2. Unconfigured Connector in Production / Staging
        if env in (Environment.PRODUCTION, Environment.SANDBOX):
            self.last_status = "NOT_CONFIGURED"
            logger.warning("Apollo discovery connector is not configured for environment=%s. Returning empty candidate list.", env)
            return []

        # 3. Explicit Mock Environment Fallback ONLY
        # Only reached when env == Environment.MOCK and connector is not configured.
        # Every record is strictly tagged with synthetic=True and source="apollo_mock_fixture"
        self.last_status = "MOCK_FIXTURE_USED"
        return _get_curated_mock_candidates(limit=filter_spec.limit, source_tag="apollo_mock_fixture", env=Environment.MOCK)


class TradeManifestDiscoveryProvider(BaseDiscoveryProvider):
    """
    Air Import Consignee discovery provider based on customs cargo trade manifests.
    If no live customs / AWB database connector is provided, returns empty in production
    and reports BLOCKED_LICENSE / NOT_CONFIGURED.
    """
    name: str = "trade_manifest"

    def __init__(self, manifest_connector=None):
        self.connector = manifest_connector
        self.last_status: str = "INITIALIZED"

    def get_status(self, env: Environment) -> str:
        if self.connector and hasattr(self.connector, "configured") and self.connector.configured():
            return "CONFIGURED_LIVE"
        if env in (Environment.PRODUCTION, Environment.SANDBOX):
            return "BLOCKED_LICENSE_NOT_CONFIGURED"
        return "MOCK_AVAILABLE"

    def discover(self, filter_spec: DiscoveryFilter, env: Environment) -> List[LeadCandidate]:
        if self.connector and hasattr(self.connector, "configured") and self.connector.configured():
            try:
                # Live customs trade query
                results = self.connector.query_consignees(routes=filter_spec.trade_lanes, limit=filter_spec.limit)
                candidates = []
                for item in (results or []):
                    c = LeadCandidate(
                        company=item["company"],
                        domain=item.get("domain"),
                        vat_number=item.get("vat_number"),
                        industry_code=item.get("industry_code"),
                        source="customs_air_manifest",
                        environment=env,
                        synthetic=False,
                        stage="DISCOVERING"
                    )
                    c.add_evidence(
                        field_name="air_cargo_flow",
                        field_value={"route": item.get("route"), "est_monthly_kg": item.get("est_kg")},
                        source_provider="customs_trade_manifest",
                        evidence_status=EvidenceStatus.SOURCE_OBSERVED,
                        confidence=0.85,
                        verification_method="customs_manifest_analysis"
                    )
                    candidates.append(c)
                self.last_status = "SUCCESS"
                return candidates[:filter_spec.limit]
            except Exception as e:
                logger.error("Trade manifest query failed: %s", e)
                self.last_status = f"ERROR: {e}"
                return []

        # Production / Staging without live manifest license: fail closed safely
        if env in (Environment.PRODUCTION, Environment.SANDBOX):
            self.last_status = "BLOCKED_LICENSE_NOT_CONFIGURED"
            logger.info("Trade manifest data provider requires enterprise customs license; not configured in %s.", env)
            return []

        # Mock environment only
        self.last_status = "MOCK_FIXTURE_USED"
        return _get_curated_mock_candidates(limit=filter_spec.limit, source_tag="customs_manifest_mock", env=Environment.MOCK)


class MockDiscoveryProvider(BaseDiscoveryProvider):
    """Explicit mock provider used ONLY in testing and demonstration environments."""
    name: str = "mock_curated"

    def discover(self, filter_spec: DiscoveryFilter, env: Environment) -> List[LeadCandidate]:
        return _get_curated_mock_candidates(limit=filter_spec.limit, source_tag="mock_curated", env=Environment.MOCK)


def _get_curated_mock_candidates(limit: int, source_tag: str, env: Environment) -> List[LeadCandidate]:
    """Internal helper to return explicitly tagged synthetic records for testing."""
    sample_dataset = [
        {
            "company": "Công ty TNHH Thiết bị Y tế Chuyên Dụng Tâm An",
            "vat_number": "0107889123",
            "domain": "tamanmedical.com.vn",
            "contact_name": "Nguyễn Văn Hùng",
            "title": "Trưởng phòng Mua hàng & Xuất Nhập Khẩu",
            "email": "hung.nv@tamanmedical.com.vn",
            "phone": "0912345671",
            "address": "Tầng 5, Tòa nhà Charmvit, 117 Trần Duy Hưng, Cầu Giấy, Hà Nội",
            "industry_code": "3250",
            "est_kg": 1500,
            "route": "JP-HAN",
        },
        {
            "company": "Công ty Cổ phần Công nghệ Sinh học Dược phẩm BioPharm VN",
            "vat_number": "0314567890",
            "domain": "biopharmvn.com",
            "contact_name": "Trần Thị Mai Anh",
            "title": "Giám đốc Chuỗi Cung Ứng (Supply Chain Director)",
            "email": "maianh.tran@biopharmvn.com",
            "phone": "0988776655",
            "address": "Khu Công nghệ Cao, TP. Thủ Đức, TP. Hồ Chí Minh",
            "industry_code": "4659",
            "est_kg": 2800,
            "route": "EU-SGN",
        },
        {
            "company": "Công ty TNHH Điện tử Chính xác MicroTech Vina",
            "vat_number": "2300987654",
            "domain": "microtechvina.vn",
            "contact_name": "Lê Hoàng Nam",
            "title": "Logistics & Customs Clearance Manager",
            "email": "nam.lh@microtechvina.vn",
            "phone": "0903456789",
            "address": "KCN Quế Võ, Tỉnh Bắc Ninh",
            "industry_code": "2611",
            "est_kg": 3500,
            "route": "KR-HAN",
        },
        {
            "company": "Công ty Cổ phần Phân phối Dược phẩm MediHealth Quốc tế",
            "vat_number": "0315998877",
            "domain": "medihealth-intl.vn",
            "contact_name": "Đặng Quốc Cường",
            "title": "Phó Giám Đốc Vận Hành",
            "email": "cuong.dq@medihealth-intl.vn",
            "phone": "0977112233",
            "address": "Quận 7, TP. Hồ Chí Minh",
            "industry_code": "4659",
            "est_kg": 950,
            "route": "KR-SGN",
        },
        {
            "company": "Công ty TNHH Quang Điện tử OptoViet Nam",
            "vat_number": "3702112233",
            "domain": "optoviet.com",
            "contact_name": "Phạm Minh Đức",
            "title": "Trưởng nhóm Ngoại thương",
            "email": "duc.pm@optoviet.com",
            "phone": "0933221100",
            "address": "KCN VSIP 1, Thuận An, Bình Dương",
            "industry_code": "2611",
            "est_kg": 1800,
            "route": "JP-SGN",
        },
    ]
    candidates = []
    for item in sample_dataset[:limit]:
        c = LeadCandidate(
            company=item["company"],
            domain=item["domain"],
            contact_name=item["contact_name"],
            title=item["title"],
            email=item["email"],
            phone=item["phone"],
            vat_number=item["vat_number"],
            registered_address=item["address"],
            industry_code=item["industry_code"],
            source=source_tag,
            environment=Environment.MOCK,  # Strictly mock tag
            synthetic=True,                # Explicitly synthetic
            stage="DISCOVERING"
        )
        c.add_evidence(
            field_name="discovery_match",
            field_value=item,
            source_provider=source_tag,
            evidence_status=EvidenceStatus.INFERRED,  # Inferred mock, NEVER verified
            confidence=0.5
        )
        candidates.append(c)
    return candidates


class DynamicDiscoveryEngine:
    def __init__(self, providers: Optional[List[BaseDiscoveryProvider]] = None):
        self.providers = providers or [
            ApolloDiscoveryProvider(),
            TradeManifestDiscoveryProvider()
        ]

    def discover_candidates(self, filter_spec: Optional[DiscoveryFilter] = None, env: Environment = Environment.MOCK) -> DiscoveryResult:
        filter_spec = filter_spec or DiscoveryFilter()
        collected: List[LeadCandidate] = []
        sources_used = []
        source_statuses = {}

        seen_companies = set()
        for prov in self.providers:
            sources_used.append(prov.name)
            source_statuses[prov.name] = prov.get_status(env)
            results = prov.discover(filter_spec, env)
            for cand in results:
                # Invariant: In production, reject any synthetic records
                if env in (Environment.PRODUCTION, Environment.SANDBOX) and cand.synthetic:
                    logger.critical("SECURITY INVARIANT VIOLATION: Synthetic record %s attempted to enter %s dataset", cand.company, env)
                    continue

                norm_key = cand.vat_number or cand.domain or cand.company.lower()
                if norm_key not in seen_companies:
                    seen_companies.add(norm_key)
                    collected.append(cand)

        limit = filter_spec.limit
        candidates = collected[:limit]
        return DiscoveryResult(
            total_discovered=len(candidates),
            candidates=candidates,
            sources_used=sources_used,
            source_statuses=source_statuses,
            filter_applied=filter_spec
        )
