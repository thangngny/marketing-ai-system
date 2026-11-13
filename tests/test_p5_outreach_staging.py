"""
Tests for P5: Outreach Staging, Compliant Personalization, Reply Classification, and Sales Handoff.
"""
import pytest
from marketing_system.models import LeadCandidate, Environment
from marketing_system.outreach.personalizer import OutreachPersonalizer
from marketing_system.outreach.reply_classifier import ReplyClassifier
from marketing_system.outreach.handoff import SalesHandoffEngine


def test_outreach_personalizer_compliance():
    personalizer = OutreachPersonalizer()

    candidate = LeadCandidate(
        company="Công ty TNHH Thiết bị Y tế Chuyên Dụng Tâm An",
        legal_name="Công ty TNHH Thiết bị Y tế Chuyên Dụng Tâm An",
        vat_number="0107889123",
        domain="tamanmedical.com.vn",
        contact_name="Nguyễn Văn Hùng",
        title="Trưởng phòng Xuất Nhập Khẩu",
        email="hung.nv@tamanmedical.com.vn",
        industry_code="3250",
        source="apollo",
        environment=Environment.MOCK,
    )

    draft = personalizer.personalize(candidate, bdm_name="Hà Vân")

    assert draft.status == "STAGED_DRAFT"
    assert draft.recipient_email == "hung.nv@tamanmedical.com.vn"
    assert "Tâm An" in draft.subject
    assert "Nguyễn Văn Hùng" in draft.body_text
    assert "Hà Vân" in draft.body_text
    assert "{" not in draft.body_text  # No unresolved placeholder
    assert draft.compliance_footer_included is True
    assert "DỪNG" in draft.body_text
    assert "981 003344" in draft.body_text


def test_reply_classifier_intents():
    classifier = ReplyClassifier()

    # 1. Stop / Opt-out
    res_stop = classifier.classify("Phiền quá, vui lòng DỪNG gửi email quảng cáo!")
    assert res_stop.intent == "STOP_CONTACT"
    assert res_stop.confidence > 0.9
    assert "Opt-out" in res_stop.suggested_action or "chặn" in res_stop.suggested_action

    # 2. Quote request
    res_quote = classifier.classify("Chào em, gửi giúp mình bảng báo giá cước air 1.2 tấn từ Narita về Nội Bài nhé.")
    assert res_quote.intent == "QUOTE_REQUEST"
    assert res_quote.confidence > 0.85

    # 3. Interested
    res_int = classifier.classify("Bên mình rất quan tâm đến dịch vụ thông quan y tế, gọi lại trao đổi nhé: 0912345678")
    assert res_int.intent == "INTERESTED"

    # 4. Not interested
    res_not = classifier.classify("Cảm ơn bạn nhưng hiện tại công ty mình đã có đối tác forwarder độc quyền cả năm rồi.")
    assert res_not.intent == "NOT_INTERESTED"


def test_sales_handoff_dossier():
    handoff = SalesHandoffEngine()

    candidate = LeadCandidate(
        company="Công ty Cổ phần Công nghệ Sinh học BioPharm VN",
        legal_name="Công ty Cổ phần Công nghệ Sinh học BioPharm VN",
        vat_number="0314567890",
        domain="biopharmvn.com",
        contact_name="Trần Thị Mai Anh",
        title="Supply Chain Director",
        email="maianh.tran@biopharmvn.com",
        phone="0988776655",
        industry_code="4659",
        score=88,
        data_quality_score=92,
        commercial_fit_score=85,
        source="apollo",
        environment=Environment.MOCK,
    )

    dossier = handoff.generate_dossier(candidate)

    assert dossier.company_name == "Công ty Cổ phần Công nghệ Sinh học BioPharm VN"
    assert dossier.vat_number == "0314567890"
    assert dossier.contact_name == "Trần Thị Mai Anh"
    assert dossier.tier == "Tier 1 - High Priority"
    assert len(dossier.talking_points) >= 2
    assert len(dossier.objection_prep) >= 1
    assert dossier.task_proposal.due_in_days == 1
    assert "BioPharm" in dossier.task_proposal.subject
