with open('.codex/handoff.md', 'r', encoding='utf-8') as f:
    content = f.read()

target = '## Current state\r\n\r\n'
if target not in content:
    target = '## Current state\n\n'

new_current_state = '''## Current state\r\n\r\n- **README.md Step 2, 3, and 4 Screenshots and Descriptions Aligned (2026-11-02, Codex):**\r\n  - Replaced duplicate case-table views in Steps 2, 3, and 4 with the exact user-provided workspace screenshots:\r\n    - Step 2 (`docs/images/02_financial_waterfall_and_briefing.png`): Opened case file workspace displaying the financial balance waterfall (Total Billed / Paid to Date / Remaining Balance / Disputed on Hold / Undisputed Ready to Collect) and the prompt-injection defense alert banner.\r\n    - Step 3 (`docs/images/03_multimodal_evidence_perception.png`): Verified Evidence tab displaying Meta SAM 3.1 computer-vision perceptual crops (receiver stamp 95%, warehouse shortage notes 92%, damaged goods 90%) and the Meta Muse Spark briefing.\r\n    - Step 4 (`docs/images/04_negotiation_copilot_and_approval.png`): Negotiation & AI Co-pilot tab showing autonomous Meta AI control modes (`Manual with co-pilot`, `Delegate to AI`), staff message editor, and simulated customer reply testing box.\r\n  - Synchronized updated images and `README.md` to AWS EC2 staging host.\r\n\r\n'''

content = content.replace(target, new_current_state, 1)

iteration_entry = '''\r\n### 2026-11-02 — Codex — Updated Walkthrough Screenshots for Steps 2, 3, and 4\r\n\r\n- **Objective:** Replace identical bill-table screenshots in Steps 2, 3, and 4 with the specific case workspace views provided by the user.\r\n- **Changed:**\r\n  - `docs/images/02_financial_waterfall_and_briefing.png`: Replaced with user's screenshot showing the opened case workspace, financial waterfall balance cards, and blocked policy prompt-injection event.\r\n  - `docs/images/03_multimodal_evidence_perception.png`: Replaced with user's screenshot showing the Verified Evidence & AI Proof tab with Meta SAM 3.1 visual perception chips and Muse Spark executive brief.\r\n  - `docs/images/04_negotiation_copilot_and_approval.png`: Replaced with user's screenshot showing the Negotiation & AI Co-pilot tab with control modes, staff message editor, and simulated customer reply box.\r\n  - `README.md`: Updated accompanying walkthrough text for Steps 2, 3, and 4 to accurately explain the visual elements in each image. Cleaned trailing whitespace; confirmed zero emojis.\r\n  - Synced `docs/images/` and `README.md` to AWS EC2 staging host via SCP.\r\n- **Verification:** Verified `git diff --check README.md` passed cleanly; confirmed all image paths exist and load.\r\n- **Limits / next:** Working tree clean.\r\n'''

content = content + iteration_entry

with open('.codex/handoff.md', 'w', encoding='utf-8', newline='') as f:
    f.write(content)

print('Updated handoff.md successfully')

