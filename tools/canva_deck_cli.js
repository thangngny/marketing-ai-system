#!/usr/bin/env node
/**
 * CANVA DECK AUTOMATION CLI
 * Connects directly to Canva Official MCP Server to create high-aesthetic
 * presentation decks, documents, and visual reports, export them to PDF/PPTX,
 * and pipe them through buzz-export to Buzz channels.
 */

const { spawn, execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

function parseArgs() {
  const args = process.argv.slice(2);
  const params = {
    brief: '',
    format: 'Presentation (16:9)',
    outlineFile: '',
    outputName: 'CANVA_DELIVERABLE_' + Date.now(),
    outDir: 'C:\\Users\\Admin\\.buzz\\OUTBOX',
    channel: '',
    exportPptx: true,
    exportPdf: true
  };

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === '--brief' || arg === '-b') params.brief = args[++i];
    else if (arg === '--format' || arg === '-f') params.format = args[++i];
    else if (arg === '--outline' || arg === '-o') params.outlineFile = args[++i];
    else if (arg === '--name' || arg === '-n') params.outputName = args[++i];
    else if (arg === '--outdir') params.outDir = args[++i];
    else if (arg === '--channel' || arg === '-c') params.channel = args[++i];
  }

  return params;
}

function wait(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function run() {
  const params = parseArgs();

  if (!params.brief && !params.outlineFile) {
    console.error('Usage: canva-create --brief "<prompt>" [--outline <file.json>] [--format <format>] [--name <name>] [--channel <uuid>]');
    process.exit(1);
  }

  let outline = null;
  if (params.outlineFile && fs.existsSync(params.outlineFile)) {
    try {
      outline = JSON.parse(fs.readFileSync(params.outlineFile, 'utf8'));
    } catch (e) {
      console.warn('Warning: Could not parse outline JSON, proceeding with brief only.');
    }
  }

  console.log('====================================================');
  console.log('🚀 CANVA AUTOMATION ENGINE — LAUNCHING MCP BRIDGE');
  console.log(`📌 Format: ${params.format}`);
  console.log(`📌 Output base: ${params.outputName}`);
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

  // Initialize
  const initId = send({
    jsonrpc: '2.0',
    method: 'initialize',
    params: {
      protocolVersion: '2024-11-05',
      capabilities: {},
      clientInfo: { name: 'canva-auto-cli', version: '1.0.0' }
    }
  });

  while (!responses.has(initId)) await wait(500);
  child.stdin.write(JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' }) + '\n');
  console.log('✅ Connected to Canva Official MCP Server.');

  // Create design
  console.log('🎨 Generating Canva Design with AI engine...');
  const createPayload = {
    brief: params.brief,
    format: params.format,
    user_intent: 'Create Canva design from user brief'
  };
  if (outline) {
    createPayload.outline = outline;
  }

  const createId = send({
    jsonrpc: '2.0',
    method: 'tools/call',
    params: {
      name: 'create-design',
      arguments: createPayload
    }
  });

  while (!responses.has(createId)) await wait(1000);
  const createResp = responses.get(createId);

  if (!createResp.result || !createResp.result.content) {
    console.error('❌ Canva creation error:', createResp);
    child.kill();
    process.exit(1);
  }

  const jobData = JSON.parse(createResp.result.content[0].text);
  const jobId = jobData.job_id;
  let continuationToken = jobData.continuation_token;
  let waitSec = jobData.polling_policy ? jobData.polling_policy.wait_seconds : 10;

  console.log(`⏳ Job dispatched [${jobId}]. Polling every ${waitSec}s...`);

  let completedDesign = null;
  for (let attempt = 1; attempt <= 25; attempt++) {
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
    waitSec = pollData.polling_policy ? pollData.polling_policy.wait_seconds : 10;
  }

  if (!completedDesign) {
    console.error('❌ Timeout waiting for Canva generation.');
    child.kill();
    process.exit(1);
  }

  // Fetch complete design info (edit_url and view_url)
  let editUrl = completedDesign.url || '';
  let viewUrl = completedDesign.url || '';
  try {
    const getDesignId = send({
      jsonrpc: '2.0',
      method: 'tools/call',
      params: {
        name: 'get-design',
        arguments: {
          design_id: completedDesign.id,
          user_intent: 'Get public view and full edit URLs'
        }
      }
    });
    while (!responses.has(getDesignId)) await wait(1000);
    const getDesignResp = responses.get(getDesignId);
    if (getDesignResp.result && getDesignResp.result.content) {
      const dData = JSON.parse(getDesignResp.result.content[0].text);
      if (dData.design && dData.design.urls) {
        editUrl = dData.design.urls.edit_url || editUrl;
        viewUrl = dData.design.urls.view_url || viewUrl;
      }
    }
  } catch (e) {
    console.warn('Note: Could not query get-design, using default url.');
  }

  console.log('====================================================');
  console.log(`🎉 DESIGN READY: ${completedDesign.id}`);
  console.log(`👁️ Canva View Link (Xem trực tiếp): ${viewUrl}`);
  console.log(`✏️ Canva Edit Link (Chỉnh sửa toàn quyền): ${editUrl}`);
  console.log('====================================================');

  const pdfPath = path.join(params.outDir, `${params.outputName}.pdf`);
  const pptxPath = path.join(params.outDir, `${params.outputName}.pptx`);

  // Export PDF
  if (params.exportPdf) {
    console.log('📥 Exporting high-res PDF from Canva...');
    const pdfId = send({
      jsonrpc: '2.0',
      method: 'tools/call',
      params: {
        name: 'export-design',
        arguments: {
          design_id: completedDesign.id,
          format: { type: 'pdf', export_quality: 'regular' },
          user_intent: 'Export PDF'
        }
      }
    });
    while (!responses.has(pdfId)) await wait(1000);
    const pdfResp = responses.get(pdfId);
    try {
      const pData = JSON.parse(pdfResp.result.content[0].text);
      const url = pData.job.urls[0];
      execSync(`curl.exe -s -L "${url}" -o "${pdfPath}"`);
      console.log(`✅ Saved PDF: ${pdfPath}`);
    } catch (e) {
      console.error('Failed to download PDF:', e.message);
    }
  }

  // Export PPTX
  if (params.exportPptx && params.format.toLowerCase().includes('presentation')) {
    console.log('📥 Exporting editable PowerPoint PPTX from Canva...');
    const pptxId = send({
      jsonrpc: '2.0',
      method: 'tools/call',
      params: {
        name: 'export-design',
        arguments: {
          design_id: completedDesign.id,
          format: { type: 'pptx' },
          user_intent: 'Export PPTX'
        }
      }
    });
    while (!responses.has(pptxId)) await wait(1000);
    const pptxResp = responses.get(pptxId);
    try {
      const pData = JSON.parse(pptxResp.result.content[0].text);
      const url = pData.job.urls[0];
      execSync(`curl.exe -s -L "${url}" -o "${pptxPath}"`);
      console.log(`✅ Saved PPTX: ${pptxPath}`);
    } catch (e) {
      console.error('Failed to download PPTX:', e.message);
    }
  }

  child.kill();

  // If channel is specified, automatically run buzz-export!
  if (params.channel) {
    console.log(`🚀 Publishing deliverables to Buzz channel: ${params.channel}...`);
    if (fs.existsSync(pdfPath)) {
      execSync(`buzz-export "${pdfPath}" --channel ${params.channel} --content "🎯 [CANVA DESIGN DELIVERABLE] Tệp PDF thiết kế cao cấp từ Canva.\n• 👁️ Link xem trực tiếp: ${viewUrl}\n• ✏️ Link mở full quyền chỉnh sửa: ${editUrl}"`, { stdio: 'inherit' });
    }
    if (fs.existsSync(pptxPath)) {
      execSync(`buzz-export "${pptxPath}" --channel ${params.channel} --content "📊 [POWERPOINT EDITABLE] File slide PowerPoint PPTX gốc (100% mở quyền chỉnh sửa trên máy tính không cần tài khoản Canva)"`, { stdio: 'inherit' });
    }
  }

  console.log('\n✨ CANVA DELIVERABLE GENERATION COMPLETE!');
}

run().catch(err => {
  console.error('Fatal CLI Error:', err);
  process.exit(1);
});
