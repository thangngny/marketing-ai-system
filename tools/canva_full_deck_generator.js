const { spawn, execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

async function runFullCanvaGeneration() {
  console.log('====================================================');
  console.log('🚀 GENERATING FULL 13-SLIDE MASTER DECK IN CANVA');
  console.log('====================================================');

  const child = spawn('npx', ['-y', 'mcp-remote', 'https://mcp.canva.com/mcp'], {
    shell: true,
    stdio: ['pipe', 'pipe', 'pipe']
  });

  let buffer = '';
  let idCounter = 1;
  const responses = new Map();

  function send(msg) {
    const id = idCounter++;
    msg.id = id;
    child.stdin.write(JSON.stringify(msg) + '\n');
    return id;
  }

  function wait(ms) { return new Promise(r => setTimeout(r, ms)); }

  child.stdout.on('data', (data) => {
    buffer += data.toString();
    const lines = buffer.split('\n');
    buffer = lines.pop();
    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const msg = JSON.parse(line);
        if (msg.id) responses.set(msg.id, msg);
      } catch (e) {}
    }
  });

  await wait(3000);

  const initId = send({
    jsonrpc: '2.0',
    method: 'initialize',
    params: {
      protocolVersion: '2024-11-05',
      capabilities: {},
      clientInfo: { name: 'canva-full-master', version: '1.0.0' }
    }
  });

  while (!responses.has(initId)) await wait(500);
  child.stdin.write(JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' }) + '\n');
  console.log('✅ Connected to Canva Official MCP Server.');

  const outline = {
    sections: [
      {
        title: "KẾ HOẠCH TRIỂN KHAI FACEBOOK Q4/2026 — MINH VÂN LOGISTICS",
        description: "China Import Marketing & SDR Execution Strategy",
        points: [
          "Báo cáo chiến lược toàn diện trình Ban Giám Đốc Minh Vân Logistics",
          "Mục tiêu cốt lõi: Thiết lập đường dẫn đo lường khép kín từ Facebook Signal đến Quote và Shipment",
          "Định vị: Coi phễu là phi tuyến tính, tín hiệu thương mại override điểm tương tác",
          "Thời gian thực thi: Quý 4/2026 (Tháng 10 - Tháng 12/2026)"
        ]
      },
      {
        title: "ĐÁNH GIÁ ĐIỀU HÀNH & KẾT LUẬN CHIẾN LƯỢC",
        description: "Phán quyết điều hành: Đúng kiến trúc, thiết lập 4 trạng thái kiểm soát",
        points: [
          "GO: Duy trì hành trình China Import đơn nhất, phễu phi tuyến và bộ chỉ số IC-01→IC-12",
          "GO CÓ ĐIỀU KIỆN: Chạy Wave 1 với IC-01→IC-06, ưu tiên wedge máy móc/thiết bị + phụ tùng",
          "HOLD: Tạm hoãn case study IC-07, workflow IC-09 và form thu lead IC-10-12 chờ UAT",
          "NO DECISION: Không vội scale ngân sách hay chọn vertical thắng cuộc trước khi có baseline"
        ]
      },
      {
        title: "MA TRẬN KIỂM ĐỊNH 10 ĐIỂM AUDIT RỦI RO",
        description: "Khắc phục triệt để các rào cản vận hành trước khi kích hoạt chiến dịch",
        points: [
          "Rủi ro ICP: Khóa chặt tiêu chí ICP 90 ngày với phân khúc máy móc & phụ tùng công nghiệp",
          "Rủi ro Claim: Loại bỏ phát ngôn chưa kiểm chứng, chuyển sang ngôn ngữ checkpoint và quy trình",
          "Rủi ro Đo lường: Gán mã tracking chi tiết IC -> FB-CI derivative ID -> UTM -> CRM Owner",
          "Rủi ro CTA: Chia thang cam kết, chỉ mở private intake sau khi hoàn tất kiểm thử UAT",
          "Rủi ro Quá tải: Điều chỉnh nhịp độ an toàn: 2 feed post + 1 Reel chuyên môn/tuần"
        ]
      },
      {
        title: "PHÂN ĐỊNH RẠCH RÒI: SỰ THẬT (FACT) & GIẢ ĐỊNH (ASSUMPTION)",
        description: "Tách biệt dữ liệu đã xác thực với các giả định cần kiểm chứng",
        points: [
          "FACT: Bộ Công Thương ghi nhận nhập khẩu từ Trung Quốc đạt 115,2 tỷ USD trong H1/2026",
          "FACT: Brief đã định nghĩa 5 marketing stages và cơ chế commercial-signal override",
          "ASSUMPTION: China Import là pilot tối ưu nhất; máy móc/phụ tùng là wedge có conversion cao",
          "CHƯA XÁC MINH: ICP được duyệt, positioning claim set, stack Zoho end-to-end"
        ]
      },
      {
        title: "HỆ SINH THÁI PHÂN VAI LIÊN KÊNH (6 LỚP)",
        description: "Phân định trách nhiệm rõ ràng, không tối ưu Facebook độc lập",
        points: [
          "Website / SEO: Canonical Hub lưu trữ bài phân tích, FAQ, biểu thuế, quy trình chuẩn",
          "Facebook Organic & Ads: Kênh phân phối, kích hoạt topic signal và ngữ cảnh người mua",
          "Email Marketing: Thư viện nuôi dưỡng khách hàng theo từng chủ đề & giai đoạn phễu",
          "SDR Team: Tiếp nhận signal có ngữ cảnh, xác minh nhu cầu thực tế",
          "Sales Team: Toàn quyền sở hữu các mốc SQL, Báo giá (Quote) và Doanh thu đơn vận",
          "CRM & Automation: Sổ cái sự kiện (Event ledger), phân luồng nhân sự và chống spam"
        ]
      },
      {
        title: "MỤC TIÊU PILOT & KHUNG TIÊU CHUẨN ICP 90 NGÀY",
        description: "Định danh chính xác chân dung khách hàng mục tiêu của Wedge Máy Móc",
        points: [
          "Doanh nghiệp: Khách hàng B2B đang hoặc chuẩn bị nhập khẩu chính ngạch từ Trung Quốc trong 90 ngày",
          "Người ra quyết định: Logistics/XNK Manager, Procurement Buyer, Chuyên viên XNK",
          "Wedge mũi nhọn: Máy móc & thiết bị dây chuyền sản xuất công nghiệp + Phụ tùng thay thế",
          "Điểm kích hoạt: Gặp vướng mắc chứng từ, so sánh phương án vận tải biển/bộ, có deadline gấp",
          "Trường dữ liệu cần thu thập: Tuyến đường, mặt hàng, mốc ETD-ETA, khối lượng/container, Incoterm"
        ]
      },
      {
        title: "LỘ TRÌNH NỘI DUNG WAVE 1: TRỤ CỘT IC-01 ĐẾN IC-03",
        description: "3 Pillar nội dung nền tảng tập trung chính sách và chứng từ",
        points: [
          "IC-01 Chính sách & Quy định: Cập nhật kiểm tra chuyên ngành, thuế suất máy móc mới nhất",
          "IC-02 Mã HS Code & Thuế: Sai sót thường gặp khi áp mã HS máy công cụ & dây chuyền đồng bộ",
          "IC-03 Chứng nhận Xuất xứ (C/O): Tiêu chí form E hợp lệ, rủi ro bị bác C/O và cách kiểm tra",
          "Format & CTA: Infographic bảng tra cứu, checklist tải về, không thu lead ép buộc"
        ]
      },
      {
        title: "LỘ TRÌNH NỘI DUNG WAVE 1: TRỤ CỘT IC-04 ĐẾN IC-06",
        description: "3 Pillar nội dung nghiệp vụ hiện trường và so sánh tuyến",
        points: [
          "IC-04 Thủ tục Hải quan: Quy trình phân luồng Đỏ/Vàng đối với máy móc cũ theo QĐ 18",
          "IC-05 Đóng gói & An toàn: Quy cách chằng buộc, bảo quản máy cơ khí chính xác đi đường biển/bộ",
          "IC-06 Tối ưu Tuyến vận tải: So sánh tổng chi phí & thời gian: Đường bộ xuyên biên giới vs. Đường biển",
          "Format & CTA: Sơ đồ luồng (Workflow), Reel video hiện trường, bảng đối sánh chi phí"
        ]
      },
      {
        title: "MA TRẬN PHÂN PHỐI NỘI DUNG & CADENCE AN TOÀN",
        description: "Lịch xuất bản cơ sở và quy trình kiểm duyệt chất lượng SME 4 bước",
        points: [
          "Nhịp độ chuẩn: 2 bài Feed tiêu chuẩn + 1 Video Reel chuyên môn/tuần; 1 flex slot dự phòng",
          "Tổng sản lượng: 12-14 bài chất lượng cao/tháng, đảm bảo chiều sâu kiến thức",
          "Kiểm tra nguồn (Currentness): 100% trích dẫn phải có ngày tra cứu và link cơ quan chức năng",
          "Bảo mật dữ liệu (Redaction): Che mờ 100% tên khách hàng, MST, số tiền trên chứng từ minh họa",
          "Phê duyệt chuyên môn: Bắt buộc có chữ ký duyệt của Chuyên viên Hải quan (SME Sign-off)"
        ]
      },
      {
        title: "THIẾT KẾ LEAD FORM & SƠ ĐỒ QUALIFICATION FLOW",
        description: "Quy chuẩn biểu mẫu thu thập và luồng dịch chuyển trạng thái Lead",
        points: [
          "Qualification Flow: Form Submit ➔ Inquiry ➔ Marketing Triage ➔ MQL ➔ Sales Review ➔ SQL ➔ Deal",
          "Các trường bắt buộc: Người liên hệ, Ngữ cảnh công ty, Mặt hàng, Tuyến đường, Mốc thời gian, Yêu cầu",
          "Nguyên tắc bảo mật: Tuyệt đối không yêu cầu gửi chứng từ, MST, giá mua trên comment công khai",
          "Quy định Consent: Phải có ô tick đồng ý tư vấn, tách biệt với điều khoản marketing"
        ]
      },
      {
        title: "BẢNG PHÂN TẦNG ƯU TIÊN & CAM KẾT PHẢN HỒI (SLAS P0-P3)",
        description: "Quy định thời gian xử lý nội bộ nghiêm ngặt cho từng mức độ tín hiệu",
        points: [
          "P0 (Khẩn cấp - Có nhu cầu ngay/sự cố cảng/deadline <= 7 ngày): Triage <= 1 giờ; xử lý <= 1 ngày",
          "P1 (Ưu tiên cao - Hàng về <= 30 ngày, có tuyến + mặt hàng): SDR gọi <= 4 giờ; Sales duyệt <= 1 ngày",
          "P2 (Tiềm năng - Hàng về 31-90 ngày hoặc hỏi kỹ thuật): Phản hồi tư vấn <= 1 ngày làm việc",
          "P3 (Thông tin - Tải tài liệu/hỏi dạo): Đưa vào luồng nuôi dưỡng tự động; không gọi điện làm phiền"
        ]
      },
      {
        title: "3 KỊCH BẢN NGÂN SÁCH PILOT & CÔNG THỨC CPSQL",
        description: "Khung phân bổ chi phí thử nghiệm và công thức đo lường hiệu quả kinh tế",
        points: [
          "Kịch bản 1 (Lean Signal Test - Khuyến nghị): 3.000.000 VNĐ/tháng, giải ngân theo tuần sau khi pass gate",
          "Kịch bản 2 (Learning Test): 6.000.000 VNĐ/tháng, chạy 1 cell chính + 1 biến thể so sánh",
          "Kịch bản 3 (Upper Pilot Cap): 9.000.000 VNĐ/tháng, trần tối đa khi có bằng chứng chuyển đổi",
          "Công thức CPSQL = Tổng chi tiêu Facebook Ads / Số lượng Sales-accepted SQL thực tế",
          "Nguyên tắc: Không tính toán ROI ảo khi chưa có dữ liệu đối soát lợi nhuận gộp từ Kế toán"
        ]
      },
      {
        title: "CHECKLIST 9 LAUNCH GATES & LỘ TRÌNH 30-60-90 NGÀY",
        description: "Điều kiện tiên quyết trước khi giải ngân và kế hoạch hành động 3 tháng",
        points: [
          "Bắt buộc PASS 100% 9 Launch Gates: Duyệt ICP, duyệt claim, Meta access, CRM UAT, SLA Sales...",
          "Tháng 1 (Ngày 1-30): Khóa ICP, gán tracking, UAT luồng xử lý. Chạy Lean test tối đa 3 triệu VNĐ",
          "Tháng 2 (Ngày 31-60): Rà soát tỷ lệ chấp thuận SQL của Sales, phân tích nguyên nhân từ chối",
          "Tháng 3 (Ngày 61-90): Đối chiếu chi phí CPSQL với lợi nhuận đơn vận thực tế; quyết định scale"
        ]
      }
    ]
  };

  console.log(`🎨 Requesting Canva to generate ${outline.sections.length} slides...`);
  const createId = send({
    jsonrpc: '2.0',
    method: 'tools/call',
    params: {
      name: 'create-design',
      arguments: {
        brief: 'A comprehensive 13-slide executive presentation deck in high-contrast navy blue and crimson red corporate branding for Minh Van Logistics: Complete Facebook Execution Plan China Import Q4/2026. Every slide must contain detailed data, structured frameworks, KPI tables, and execution gates.',
        format: 'Presentation (16:9)',
        outline: outline,
        user_intent: 'Create full 13-slide master presentation deck in Canva'
      }
    }
  });

  while (!responses.has(createId)) await wait(1000);
  const createResp = responses.get(createId);
  const jobData = JSON.parse(createResp.result.content[0].text);
  const jobId = jobData.job_id;
  let continuationToken = jobData.continuation_token;
  let waitSec = jobData.polling_policy ? jobData.polling_policy.wait_seconds : 15;

  console.log(`⏳ Job dispatched [${jobId}]. Polling every ${waitSec}s...`);

  let completedDesign = null;
  for (let attempt = 1; attempt <= 30; attempt++) {
    await wait(waitSec * 1000);
    process.stdout.write(`   ↳ Poll #${attempt}... `);

    const pollId = send({
      jsonrpc: '2.0',
      method: 'tools/call',
      params: {
        name: 'get-create-design-async-job',
        arguments: {
          job_id: jobId,
          continuation_token: continuationToken,
          user_intent: 'Check Canva design status'
        }
      }
    });

    while (!responses.has(pollId)) await wait(1000);
    const pollResp = responses.get(pollId);
    const pollData = JSON.parse(pollResp.result.content[0].text);

    if (pollData.status === 'completed') {
      completedDesign = pollData.design;
      console.log('DONE! 🎉');
      break;
    } else if (pollData.status === 'failed') {
      console.log('FAILED ❌');
      console.error(pollData.failure);
      child.kill();
      process.exit(1);
    } else {
      console.log('in progress');
    }

    continuationToken = pollData.continuation_token || continuationToken;
    waitSec = pollData.polling_policy ? pollData.polling_policy.wait_seconds : 15;
  }

  if (!completedDesign) {
    console.error('❌ Timeout waiting for Canva generation.');
    child.kill();
    process.exit(1);
  }

  console.log('====================================================');
  console.log(`🎉 FULL DESIGN READY: ${completedDesign.id}`);
  console.log(`🔗 Canva URL: ${completedDesign.url}`);
  console.log('====================================================');

  const outDir = 'C:\\Users\\Admin\\.buzz\\OUTBOX';
  const pdfPath = path.join(outDir, 'CANVA_FACEBOOK_PLAN_FULL_13_SLIDES_MASTER.pdf');
  const pptxPath = path.join(outDir, 'CANVA_FACEBOOK_PLAN_FULL_13_SLIDES_MASTER.pptx');

  // Export PDF
  console.log('📥 Exporting Full PDF from Canva...');
  const pdfId = send({
    jsonrpc: '2.0',
    method: 'tools/call',
    params: {
      name: 'export-design',
      arguments: {
        design_id: completedDesign.id,
        format: { type: 'pdf', export_quality: 'regular' },
        user_intent: 'Export Full PDF'
      }
    }
  });
  while (!responses.has(pdfId)) await wait(1000);
  const pdfResp = responses.get(pdfId);
  try {
    const pData = JSON.parse(pdfResp.result.content[0].text);
    const url = pData.job.urls[0];
    execSync(`curl.exe -s -L "${url}" -o "${pdfPath}"`);
    console.log(`✅ Saved Full PDF: ${pdfPath} (${(fs.statSync(pdfPath).size / (1024*1024)).toFixed(1)} MB)`);
  } catch (e) {
    console.error('PDF export failed:', e.message);
  }

  // Export PPTX
  console.log('📥 Exporting Full PowerPoint PPTX from Canva...');
  const pptxId = send({
    jsonrpc: '2.0',
    method: 'tools/call',
    params: {
      name: 'export-design',
      arguments: {
        design_id: completedDesign.id,
        format: { type: 'pptx' },
        user_intent: 'Export Full PPTX'
      }
    }
  });
  while (!responses.has(pptxId)) await wait(1000);
  const pptxResp = responses.get(pptxId);
  try {
    const pData = JSON.parse(pptxResp.result.content[0].text);
    const url = pData.job.urls[0];
    execSync(`curl.exe -s -L "${url}" -o "${pptxPath}"`);
    console.log(`✅ Saved Full PPTX: ${pptxPath} (${(fs.statSync(pptxPath).size / (1024*1024)).toFixed(1)} MB)`);
  } catch (e) {
    console.error('PPTX export failed:', e.message);
  }

  child.kill();
  console.log('\n✨ FULL 13-SLIDE MASTER EXPORT COMPLETE!');
}

runFullCanvaGeneration().catch(e => {
  console.error('Fatal:', e);
  process.exit(1);
});
