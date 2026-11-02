from pathlib import Path

content = Path('frontend/app.js').read_text(encoding='utf-8')

old_chunk = '''            detail.querySelectorAll('.sam-segment-chip').forEach(chip => chip.addEventListener('click', () => {
                const cropUrl = chip.dataset.crop;
                const label = chip.dataset.label;
                const notes = chip.dataset.notes;
                const conf = chip.dataset.conf;
                const modal = document.createElement('div');
                modal.className = 'sam-crop-preview-modal';
                modal.innerHTML = `
                    <div class="sam-modal-content">
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <div>
                                <span class="sam-tag">Verified Visual Proof</span>
                                <span class="sam-model-badge">(Meta SAM 3.1)</span>
                                <h3 style="margin:4px 0 0 0;">${escapeHtml(label)}</h3>
                            </div>
                            <button type="button" class="btn sam-close-btn" style="padding:4px 10px;">✕</button>
                        </div>
                        <p style="font-size:12px;color:#555;margin:4px 0;">Perception Confidence: <strong>${escapeHtml(conf)}%</strong> via Meta Model API</p>
                        <img src="${cropUrl}" class="sam-modal-crop" alt="${escapeHtml(label)}">
                        ${notes ? `<div class="snippet-box"><strong>Visual Proof Observation:</strong><br>${escapeHtml(notes)}</div>` : ''}
                        <div style="text-align:right;margin-top:10px;">
                            <button type="button" class="btn sam-close-btn">Close</button>
                        </div>
                    </div>
                `;
                document.body.appendChild(modal);
                modal.querySelectorAll('.sam-close-btn').forEach(b => b.addEventListener('click', () => modal.remove()));
                modal.addEventListener('click', e => { if (e.target === modal) modal.remove(); });
            }));'''

new_chunk = '''            detail.querySelectorAll('.sam-segment-chip').forEach(chip => chip.addEventListener('click', async () => {
                const cropUrl = chip.dataset.crop;
                const label = chip.dataset.label;
                const notes = chip.dataset.notes;
                const conf = chip.dataset.conf;
                let objectUrl = cropUrl;
                try {
                    const response = await apiFetch(cropUrl);
                    objectUrl = URL.createObjectURL(await response.blob());
                } catch (err) {
                    console.warn("Could not load blob for crop:", err);
                }
                const modal = document.createElement('div');
                modal.className = 'sam-crop-preview-modal';
                modal.innerHTML = `
                    <div class="sam-modal-content">
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <div>
                                <span class="sam-tag">Verified Visual Proof</span>
                                <span class="sam-model-badge">(Meta SAM 3.1)</span>
                                <h3 style="margin:4px 0 0 0;">${escapeHtml(label)}</h3>
                            </div>
                            <button type="button" class="btn sam-close-btn" style="padding:4px 10px;">✕</button>
                        </div>
                        <p style="font-size:12px;color:#555;margin:4px 0;">Visual Perception Confidence: <strong>${escapeHtml(conf)}%</strong> via Meta Model API</p>
                        <img src="${objectUrl}" class="sam-modal-crop" alt="${escapeHtml(label)}">
                        ${notes ? `<div class="snippet-box"><strong>Visual Proof Observation:</strong><br>${escapeHtml(notes)}</div>` : ''}
                        <div style="text-align:right;margin-top:10px;">
                            <button type="button" class="btn sam-close-btn">Close</button>
                        </div>
                    </div>
                `;
                document.body.appendChild(modal);
                const closeModal = () => {
                    if (objectUrl && objectUrl.startsWith('blob:')) URL.revokeObjectURL(objectUrl);
                    modal.remove();
                };
                modal.querySelectorAll('.sam-close-btn').forEach(b => b.addEventListener('click', closeModal));
                modal.addEventListener('click', e => { if (e.target === modal) closeModal(); });
            }));'''

assert old_chunk in content, 'old_chunk not found'
content = content.replace(old_chunk, new_chunk)
Path('frontend/app.js').write_text(content, encoding='utf-8')
print("Successfully patched modal image loading in frontend/app.js")

