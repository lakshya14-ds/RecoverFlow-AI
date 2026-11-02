with open('.codex/handoff.md', 'r', encoding='utf-8') as f:
    content = f.read()

target = '## Current state\r\n\r\n'
if target not in content:
    target = '## Current state\n\n'

new_current_state = '''## Current state\r\n\r\n- **README.md Screenshots, Walkthrough, and Mermaid Fix Applied (2026-11-02, Codex):**\r\n  - Removed the top logo image and changed judge-specific headings to an objective, user-facing \"Walkthrough\".\r\n  - Fixed the GitHub Mermaid parse error in Section 5 (End-to-End Workflow) by replacing the sequence diagram with a clean, robust directed flowchart (`flowchart TD`).\r\n  - Added 5 live desktop/modal screenshots into `docs/images/` (`01_business_signin_modal.png`, `02_financial_waterfall_and_briefing.png`, `03_multimodal_evidence_perception.png`, `04_negotiation_copilot_and_approval.png`, `05_business_owner_control_center.png`) and documented the technical and business workings alongside each image.\r\n  - Verified zero emojis, valid relative links, clean `git diff --check`, and synchronized all assets to the live AWS EC2 host.\r\n\r\n'''

content = content.replace(target, new_current_state, 1)

iteration_entry = '''\r\n### 2026-11-02 — Codex — README Walkthrough, Screenshots Integration, and Mermaid Fix\r\n\r\n- **Objective:** Fix the GitHub Mermaid display error, remove the top logo image, replace judge-targeted phrasing with a clean \"Walkthrough\", and embed 5 recent live screenshots with technical explanations.\r\n- **Changed:**\r\n  - `README.md`: Removed top `![RecoverFlow AI Logo]`; renamed Section 2 to `Walkthrough`; eliminated judge-specific phrasing across the document; converted Section 5's sequence diagram to a robust `flowchart TD` resolving GitHub's parser syntax error; embedded 5 live screenshots from `docs/images/` with detailed explanations of business sign-in, balance waterfall, Meta SAM 3.1 & Muse Voice perception, negotiation co-pilot with exact-version approval, and the executive control center.\r\n  - `docs/images/`: Added `01_business_signin_modal.png`, `02_financial_waterfall_and_briefing.png`, `03_multimodal_evidence_perception.png`, `04_negotiation_copilot_and_approval.png`, and `05_business_owner_control_center.png` captured live from `https://recoverflaw.duckdns.org/`.\r\n  - Synced `docs/images/` and `README.md` to AWS EC2 staging host.\r\n- **Verification:** Verified zero emojis in `README.md`, all 5 image links exist and load, `git diff --check README.md` passed cleanly, and live health endpoint confirmed HTTP 200.\r\n- **Limits / next:** Working tree clean.\r\n'''

content = content + iteration_entry

with open('.codex/handoff.md', 'w', encoding='utf-8', newline='') as f:
    f.write(content)

print('Updated handoff.md successfully')

