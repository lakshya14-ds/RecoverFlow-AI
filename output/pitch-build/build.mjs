import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const root = process.cwd();
const build = path.join(root, 'output', 'pitch-build');
const out = path.join(root, 'output', 'presentation');
const skill = 'C:/Users/Lakshya Arora/.codex/plugins/cache/openai-primary-runtime/presentations/26.1017.22136/skills/presentations';
const modulePath = 'C:/Users/Lakshya Arora/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';
const { Presentation, PresentationFile } = await import(pathToFileURL(modulePath));
const { finalizePresentation } = await import(pathToFileURL(path.join(skill, 'container_tools/artifact_tool_utils.mjs')));
await fs.mkdir(out, { recursive: true });
const ppt = Presentation.create({ slideSize: { width: 1280, height: 720 } });
const C = { navy:'#081B2B', ink:'#0E2637', teal:'#0A8F91', amber:'#B76B23', paper:'#F6F4EE', white:'#FFFFFF', muted:'#546572', pale:'#DBE8E6' };
const screenshots = path.join(build, 'screenshots');
const src = (...names) => names.join('\n');

function box(slide, text, x, y, w, h, size=24, color=C.ink, bold=false, opts={}) {
  const sh = slide.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{style:'solid',fill:'none',width:0}});
  sh.text = text;
  sh.text.style = {fontFamily:'Arial',fontSize:size,color,bold,verticalAlignment:'middle',...opts};
  return sh;
}
function page(title, n, dark=false) {
  const s=ppt.slides.add(); s.background.fill=dark?C.navy:C.paper;
  box(s,title,64,53,1140,65,36,dark?C.white:C.ink,true);
  box(s,String(n).padStart(2,'0'),1175,661,44,24,13,dark?'#96ABBB':C.muted,true);
  return s;
}
function notes(slide, body) { slide.speakerNotes.text=body; }
async function pic(slide, name, x, y, w, h, fit='contain') {
  const bytes=await fs.readFile(path.join(screenshots,name));
  slide.images.add({blob:bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),contentType:'image/png',alt:`RecoverFlow live app screenshot: ${name}`,fit,position:{left:x,top:y,width:w,height:h}});
}
async function coverPic(slide) {
  const bytes=await fs.readFile(path.join(build,'cover.png'));
  slide.images.add({blob:bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),contentType:'image/png',alt:'Abstract invoice flow illustration',fit:'cover',position:{left:0,top:0,width:1280,height:720}});
}

// 1 Cover
{
  const s=ppt.slides.add(); s.background.fill=C.navy; await coverPic(s);
  box(s,'RecoverFlow',66,202,675,95,62,C.white,true);
  box(s,'Evidence-led recovery for disputed receivables',68,307,610,94,28,'#E5F4F3');
  box(s,'Hackathon demo  |  India MSME credit operations',69,607,620,30,17,'#B8CBD1');
  notes(s,'Original abstract visual generated for this deck. Product claims and demo figures come from repository README, .codex/prompt.md, and scripts/demo_hero.py. Synthetic demo; no live customer messages or payments.');
}
// 2 Problem
{
  const s=page('Problem statement',2);
  box(s,'A partial payment plus a dispute creates two different balances.',65,162,1000,78,34,C.ink,true);
  box(s,'A blunt reminder for the full outstanding amount can demand money the customer has specifically disputed.',65,267,1100,90,27,C.muted);
  box(s,'For a credit selling MSME, staff must reconcile the invoice, purchase order, receipt and customer reply before they can ask for the amount actually owed.',65,398,1100,136,27,C.ink);
  box(s,'Target user: Indian retailers and distributors selling on credit. Market need remains a pilot hypothesis.',65,612,1080,38,17,C.amber);
  notes(s,src('Source: .codex/prompt.md sections 1 and 8.','Target customer is a pitch hypothesis, not a measured market size.'));
}
// 3 Core idea
{
  const s=page('The recoverable balance',3,true);
  box(s,'₹90,000',67,191,480,105,72,C.white,true);
  box(s,'outstanding after partial payment',69,295,530,38,22,'#B8CBD1');
  box(s,'₹30,000',69,405,440,75,51,'#E8AA64',true);
  box(s,'disputed and on hold',70,481,430,38,21,'#D5BC9A');
  box(s,'₹60,000',677,405,430,75,51,'#7FE2D7',true);
  box(s,'undisputed and eligible for a draft',679,481,480,54,21,'#B8DAD8');
  box(s,'Invoice ₹2,40,000  −  received ₹1,50,000  =  outstanding ₹90,000',69,602,1100,42,22,C.white);
  notes(s,'Synthetic hero case, verified by scripts/seed_hero_case.py and successful local scripts/demo_hero.py run on 2026-10-24. The disputed ₹30,000 is a delivery shortfall in customer evidence.');
}
// 4 Workflow
{
  const s=page('Complete workflow',4);
  const steps=[
    ['01','Intake','CSV/PDF/image upload. Staff confirms extracted invoice and receipt.'],
    ['02','Investigate','Match invoice, PO, payment and messages. Link each claim to a source.'],
    ['03','Decide','Server rules split the balance and bound the next action.'],
    ['04','Approve','Staff edits or approves the exact draft version for the sandbox.'],
    ['05','Verify','Only a matched SIMULATED payment updates the ledger and case state.']
  ];
  let y=150;
  for(const [n,t,b] of steps){box(s,n,64,y,70,58,29,C.teal,true);box(s,t,150,y,245,52,29,C.ink,true);box(s,b,420,y,790,72,21,C.muted);y+=102;}
  notes(s,src('Sources: README.md; scripts/demo_hero.py; frontend/app.js; app/services/receivables.py; app/services/negotiation.py.','Customer-facing sends and payments remain simulator/sandbox.'));
}
// 5 Live case
{
  const s=page('The case file makes the split visible',5);
  await pic(s,'03-balance-evidence.png',58,161,1164,370);
  box(s,'Each figure has a source control. The ₹30,000 dispute stays on hold while the ₹60,000 request can advance.',63,557,1130,72,23,C.ink);
  notes(s,'Screenshot captured from local seeded app at 127.0.0.1:8012 on 2026-10-24. Synthetic data. Source: frontend/app.js case view; scripts/seed_hero_case.py.');
}
// 6 Evidence
{
  const s=page('Claims are traceable to evidence',6);
  await pic(s,'04-source-evidence.png',60,141,600,500);
  box(s,'Invoice PDF',710,184,460,46,29,C.ink,true);
  box(s,'Purchase order',710,279,460,46,29,C.ink,true);
  box(s,'Payment receipt',710,374,460,46,29,C.ink,true);
  box(s,'Customer dispute',710,469,460,46,29,C.ink,true);
  box(s,'Calculated balance',710,564,460,46,29,C.teal,true);
  notes(s,'Screenshot from local seeded app. Synthetic documents and messages. Source: scripts/seed_hero_case.py; frontend/app.js. An unsupported claim is omitted from the balance view.');
}
// 7 Features
{
  const s=page('Features the team can demo now',7);
  box(s,'Manual co-pilot',63,159,350,47,26,C.ink,true);
  box(s,'Staff owns the message.',64,207,340,35,18,C.muted);
  box(s,'Delegated mode',453,159,345,47,26,C.ink,true);
  box(s,'Approval and takeover controls.',454,207,350,35,18,C.muted);
  box(s,'Injection defense',843,159,350,47,26,C.ink,true);
  box(s,'Unsafe instructions escalate.',844,207,340,35,18,C.muted);
  await pic(s,'05-negotiation.png',63,272,1154,359);
  notes(s,'Screenshot from running seeded app. Functionality verified in offline scripts/demo_hero.py: Manual/Delegate transcript, exact-version approval, injection escalation. No live sends.');
}
// 8 Governance
{
  const s=page('Governance and responsibility',8,true);
  const rows=[
    ['Money','Server-side Decimal and integer-cent rules calculate balances; the model cannot alter the ledger.'],
    ['Messages','Staff approves the exact draft version. WhatsApp and email remain sandbox outboxes.'],
    ['Autonomy','Internal notes and unsent drafts only. Pause, take over and stop are available per case.'],
    ['Closure','A promise never closes a case. A matched SIMULATED payment creates PARTIALLY_RESOLVED.'],
    ['Trust','Untrusted uploads and customer text cannot override policy. Every action is auditable.']
  ];
  let y=148;for(const [h,b] of rows){box(s,h,68,y,230,49,28,'#7FE2D7',true);box(s,b,310,y,870,70,21,C.white);y+=100;}
  notes(s,'Sources: .codex/prompt.md sections 2, 3, 8; README.md; app/services/controlled_agent.py; app/services/negotiation.py. All payment and messaging descriptions refer to this demo configuration.');
}
// 9 Reusability
{
  const s=page('Reusability',9);
  box(s,'Reusable core',64,170,530,57,31,C.ink,true);
  box(s,'A source-linked case model, deterministic balance engine, versioned approval and audit trail can serve new industries and channels.',65,239,513,190,24,C.muted);
  box(s,'Replaceable edges',660,170,530,57,31,C.ink,true);
  box(s,'CSV/PDF/image intake, read-only Shopify, Gemini wording, sandbox messaging and SIMULATED Razorpay sit behind separate services.',661,239,525,195,24,C.muted);
  box(s,'Pilot setup: SQLite and local identity. Production requires managed tenancy, migrations, backups and provider tests.',65,546,1130,83,22,C.amber);
  notes(s,'Sources: README.md; docs/PROJECT_ANALYSIS_AND_SYSTEM_STATE.md; app/services/; app/api/. Production roadmap is documented, not implemented.');
}
// 10 ROI
{
  const s=page('ROI and business value',10);
  box(s,'₹60,000',66,178,510,93,64,C.teal,true);
  box(s,'eligible to pursue in the hero case',69,273,572,49,23,C.muted);
  box(s,'₹30,000',681,178,510,93,64,C.amber,true);
  box(s,'kept out of the collection request',684,273,510,49,23,C.muted);
  box(s,'Potential value',67,393,550,58,29,C.ink,true);
  box(s,'Less staff reconciliation time, fewer incorrect demands, and a clearer queue of undisputed cash.',67,450,1100,86,25,C.ink);
  box(s,'Pilot KPI: measure minutes per case, draft correction rate, eligible balance contacted and verified receipts. Recovery uplift is not yet measured.',67,579,1110,68,19,C.amber);
  notes(s,'Hero amounts are synthetic, from seed and demo scripts. Benefits are hypotheses. No measured ROI or recovery claim is made; proposed pilot KPIs are forward-looking.');
}
// 11 MVP readiness
{
  const s=page('MVP readiness',11);
  box(s,'Offline end-to-end demo',64,160,750,57,31,C.ink,true);
  box(s,'CSV + PDFs  →  source-linked case  →  edited approval  →  sandbox negotiation  →  SIMULATED matched payment',64,228,1140,82,24,C.muted);
  box(s,'30 / 30',65,359,333,83,53,C.teal,true);
  box(s,'synthetic ledger splits correct',66,446,355,60,20,C.muted);
  box(s,'10 / 10',455,359,330,83,53,C.teal,true);
  box(s,'offline upload routing correct',456,446,350,60,20,C.muted);
  box(s,'5 / 10',842,359,330,83,53,C.amber,true);
  box(s,'files reached Review without entry',843,446,355,72,20,C.muted);
  box(s,'Limits: verified dispute amounts supplied to the 30-case ledger test; live image extraction accuracy unmeasured; offline images need staff review.',64,563,1125,75,19,C.amber);
  notes(s,'Sources: docs/evaluation.md, freshly regenerated by successful scripts/demo_hero.py run on 2026-10-24. Counts are synthetic and do not establish customer recovery performance.');
}
// 12 Innovation
{
  const s=page('Originality and innovation',12,true);
  box(s,'The narrow wedge',66,166,550,59,32,'#7FE2D7',true);
  box(s,'Evidence-linked handling of partial payments and disputes for India-focused small credit teams.',67,234,1090,102,29,C.white);
  box(s,'The technical combination',66,391,580,59,32,'#E8AA64',true);
  box(s,'Rules own money and policy; AI helps with language and classification; staff own customer contact.',67,461,1090,112,29,C.white);
  box(s,'Next proof point: a measured pilot on real, consented cases and document samples.',67,619,1090,38,19,'#B8CBD1');
  notes(s,'Positioning source: .codex/prompt.md. Do not claim no autonomous receivables tools exist; competitors include HighRadius, Fazeshift and Stuut. This slide states the product niche and architecture, not novelty of autonomous collections in general.');
}

// Render and validate.
for(let i=0;i<ppt.slides.items.length;i++){
  const blob=await ppt.export({slide:ppt.slides.items[i],format:'png',scale:1});
  await fs.writeFile(path.join(build,`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await blob.arrayBuffer()));
}
const candidate=path.join(build,'candidate.pptx');
await (await PresentationFile.exportPptx(ppt)).save(candidate);
const result=await finalizePresentation({
  workspaceDir:root,candidatePath:candidate,finalPath:path.join(out,'RecoverFlow-Hackathon-Pitch-v3.pptx'),
  pythonExecutable:'C:/Users/Lakshya Arora/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe',
  integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
  layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit'],
  requiredNativeTableOwnerSlides:[],fontPolicy:{basis:'design',families:['Aptos']},
  verifyArtifactToolImport:true,
  receiptPath:path.join(build,'validation-v3.json'),
});
console.log(JSON.stringify({slides:ppt.slides.items.length,result}));
