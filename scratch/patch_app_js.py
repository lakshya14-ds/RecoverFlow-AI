from pathlib import Path

content = Path('frontend/app.js').read_text(encoding='utf-8')

old_sam_panel = '''                            ${ev.segments && ev.segments.length > 0 ? `
                                <div class="sam-perception-panel">
                                    <div class="sam-badge">
                                        <span class="sam-tag">Meta SAM 3.1</span>
                                        <span>Perception Visual Proof</span>
                                    </div>
                                    <div class="sam-segments-grid">
                                        ${ev.segments.map(seg => `
                                            <div class="sam-segment-chip" data-crop="${escapeHtml(seg.crop_url)}" data-label="${escapeHtml(seg.label)}" data-notes="${escapeHtml(seg.notes || '')}" data-conf="${Math.round(seg.confidence * 100)}">
                                                <span class="sam-icon">${seg.concept === 'stamp_signature' ? '🔏' : seg.concept === 'receiving_notes' ? '📝' : '📦'}</span>
                                                <span class="sam-chip-label">${escapeHtml(seg.label)}</span>
                                                <span class="sam-chip-conf">${Math.round(seg.confidence * 100)}%</span>
                                            </div>
                                        `).join('')}
                                    </div>
                                </div>
                            ` : (String(ev.source_reference).includes('challan') || String(ev.source_reference).includes('.png') || String(ev.source_reference).includes('.jpg') || String(ev.source_reference).includes('upload')) ? `
                                <div style="margin-top:8px;">
                                    <button type="button" class="btn run-sam-btn" data-evidence-id="${Number(ev.id)}">Segment with Meta SAM 3.1</button>
                                </div>
                            ` : ''}'''

new_sam_panel = '''                            ${ev.segments && ev.segments.length > 0 ? `
                                <div class="sam-perception-panel">
                                    <div class="sam-badge">
                                        <span class="sam-tag">Visual Proof &amp; Stamps</span>
                                        <span class="sam-model-badge">(Meta SAM 3.1 AI Perception)</span>
                                    </div>
                                    <div style="font-size:0.82rem; color:#475569; margin:4px 0 8px 0; font-weight:500;">Click any verified crop below to inspect stamps, signatures, or delivery notes:</div>
                                    <div class="sam-segments-grid">
                                        ${ev.segments.map(seg => `
                                            <div class="sam-segment-chip" data-crop="${escapeHtml(seg.crop_url)}" data-label="${escapeHtml(seg.label)}" data-notes="${escapeHtml(seg.notes || '')}" data-conf="${Math.round(seg.confidence * 100)}">
                                                <span class="sam-icon">${seg.concept === 'stamp_signature' ? '🔏' : seg.concept === 'receiving_notes' ? '📝' : '📦'}</span>
                                                <span class="sam-chip-label">${escapeHtml(seg.label)}</span>
                                                <span class="sam-chip-conf">${Math.round(seg.confidence * 100)}%</span>
                                            </div>
                                        `).join('')}
                                    </div>
                                </div>
                            ` : (String(ev.source_reference).includes('challan') || String(ev.source_reference).includes('.png') || String(ev.source_reference).includes('.jpg') || String(ev.source_reference).includes('.pdf') || String(ev.source_reference).includes('upload')) ? `
                                <div style="margin-top:8px;">
                                    <button type="button" class="btn run-sam-btn" data-evidence-id="${Number(ev.id)}">🔍 Extract Visual Proof &amp; Stamps <span class="model-tag-bracket">(Powered by Meta SAM 3.1)</span></button>
                                </div>
                            ` : ''}'''

assert old_sam_panel in content, 'old_sam_panel not found'
content = content.replace(old_sam_panel, new_sam_panel)

old_handler = '''            detail.querySelectorAll('.run-sam-btn').forEach(button => button.addEventListener('click', async () => {
                button.textContent = 'Segmenting with SAM 3.1...';
                button.disabled = true;
                try {
                    await apiFetch(`/api/v1/cases/${id}/evidence/${button.dataset.evidenceId}/segment`, {method: 'POST'});
                    openCase(id);
                } catch (error) {
                    alert('SAM 3.1 perception failed: ' + error.message);
                    button.textContent = 'Segment with Meta SAM 3.1';
                    button.disabled = false;
                }
            }));'''

new_handler = '''            detail.querySelectorAll('.run-sam-btn').forEach(button => button.addEventListener('click', async () => {
                button.innerHTML = '⏳ Extracting visual proof &amp; stamps <span class="model-tag-bracket">(Meta SAM 3.1)...</span>';
                button.disabled = true;
                try {
                    await apiFetch(`/api/v1/cases/${id}/evidence/${button.dataset.evidenceId}/segment`, {method: 'POST'});
                    openCase(id);
                } catch (error) {
                    alert('Visual proof extraction failed: ' + error.message);
                    button.innerHTML = '🔍 Extract Visual Proof &amp; Stamps <span class="model-tag-bracket">(Powered by Meta SAM 3.1)</span>';
                    button.disabled = false;
                }
            }));'''

assert old_handler in content, 'old_handler not found'
content = content.replace(old_handler, new_handler)

old_modal = '''                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <div>
                                <span class="sam-tag">Meta SAM 3.1 Perception Crop</span>
                                <h3 style="margin:4px 0 0 0;">${escapeHtml(label)}</h3>
                            </div>
                            <button type="button" class="btn sam-close-btn" style="padding:4px 10px;">✕</button>
                        </div>'''

new_modal = '''                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <div>
                                <span class="sam-tag">Verified Visual Proof</span>
                                <span class="sam-model-badge">(Meta SAM 3.1)</span>
                                <h3 style="margin:4px 0 0 0;">${escapeHtml(label)}</h3>
                            </div>
                            <button type="button" class="btn sam-close-btn" style="padding:4px 10px;">✕</button>
                        </div>'''

assert old_modal in content, 'old_modal not found'
content = content.replace(old_modal, new_modal)

Path('frontend/app.js').write_text(content, encoding='utf-8')
print("Successfully patched frontend/app.js")

