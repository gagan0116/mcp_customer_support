/**
 * Customer Support AI Demo - Frontend Application
 * Dynamically loads scenarios from /scenarios/*.json
 */

// ============================================
// Demo Scenarios - Loaded dynamically
// ============================================
let demoScenarios = {};

// ============================================
// Load scenarios from JSON files
// ============================================
async function loadScenarios() {
    const scenarioIds = ['scenario1', 'scenario2', 'scenario3', 'scenario4'];

    for (const id of scenarioIds) {
        try {
            const url = `scenarios/${id}/${id}.json`;
            console.log(`Fetching: ${url}`);
            const response = await fetch(url);
            console.log(`Response for ${id}:`, response.status, response.statusText);
            if (response.ok) {
                const data = await response.json();
                demoScenarios[id] = data;
                console.log(`Loaded ${id}:`, data.category);
            } else {
                console.warn(`Failed to load ${id}: ${response.status}`);
            }
        } catch (error) {
            console.warn(`Error loading ${id}:`, error);
        }
    }

    return demoScenarios;
}

// ============================================
// Populate dropdown with loaded scenarios
// ============================================
function populateScenarioDropdown() {
    const select = document.getElementById('scenarioSelect');
    if (!select) return;

    // Clear existing options except the first placeholder
    while (select.options.length > 1) {
        select.remove(1);
    }

    // Add options for each loaded scenario
    for (const [id, scenario] of Object.entries(demoScenarios)) {
        const option = document.createElement('option');
        option.value = id;

        // Create a descriptive label based on scenario data
        const categoryEmoji = {
            'RETURN': '📦',
            'REFUND': '💰',
            'REPLACEMENT': '🔄'
        };
        const emoji = categoryEmoji[scenario.category] || '📧';
        // Use date in label instead of email (PII)
        const dateStr = new Date(scenario.received_at).toLocaleDateString();
        option.textContent = `${emoji} ${scenario.category} Request (${dateStr})`;

        select.appendChild(option);
    }

    console.log(`Populated dropdown with ${Object.keys(demoScenarios).length} scenarios`);
}

// ============================================
// State Management
// ============================================
const state = {
    selectedScenario: null,
    isProcessing: false,
    pipelineStep: 0,
    startTime: null,
    timerInterval: null
};

// ============================================
// DOM Elements
// ============================================
const elements = {
    // Scenario Selection
    scenarioSelect: document.getElementById('scenarioSelect'),

    // Email Preview
    emailPreview: document.getElementById('emailPreview'),
    emptyState: document.getElementById('emptyState'),
    categoryBadge: document.getElementById('categoryBadge'),
    fromEmail: document.getElementById('fromEmail'),
    receivedAt: document.getElementById('receivedAt'),
    confidenceFill: document.getElementById('confidenceFill'),
    confidenceValue: document.getElementById('confidenceValue'),
    emailBody: document.getElementById('emailBody'),
    attachmentsList: document.getElementById('attachmentsList'),

    // Submit
    submitBtn: document.getElementById('submitBtn'),

    // Pipeline
    pipelineSteps: document.querySelectorAll('.pipeline-step'),
    pipelineTimer: document.getElementById('pipelineTimer'),
    timerValue: document.getElementById('timerValue'),

    // Pipeline Results
    resultCategory: document.getElementById('resultCategory'),
    resultConfidenceFill: document.getElementById('resultConfidenceFill'),
    resultConfidenceValue: document.getElementById('resultConfidenceValue'),
    parsedFiles: document.getElementById('parsedFiles'),
    defectAnalysis: document.getElementById('defectAnalysis'),

    // Logs
    logsContainer: document.getElementById('logsContainer'),
    logsToggle: document.getElementById('logsToggle'),

    // Modal
    jsonModal: document.getElementById('jsonModal'),
    modalTitle: document.getElementById('modalTitle'),
    jsonContent: document.getElementById('jsonContent'),
    modalClose: document.getElementById('modalClose'),
    closeModalBtn: document.getElementById('closeModalBtn'),
    copyJsonBtn: document.getElementById('copyJsonBtn'),

    // View JSON Buttons
    viewJsonBtns: document.querySelectorAll('.view-json-btn')
};

// ============================================
// Event Listeners
// ============================================
function initializeEventListeners() {
    // Scenario Selection
    elements.scenarioSelect.addEventListener('change', handleScenarioChange);

    // Submit Button
    elements.submitBtn.addEventListener('click', handleSubmit);

    // Logs Toggle
    elements.logsToggle.addEventListener('click', toggleLogs);

    // Modal
    elements.modalClose.addEventListener('click', closeModal);
    elements.closeModalBtn.addEventListener('click', closeModal);
    elements.copyJsonBtn.addEventListener('click', copyJsonToClipboard);
    elements.jsonModal.addEventListener('click', (e) => {
        if (e.target === elements.jsonModal) closeModal();
    });

    // View JSON Buttons (using event delegation for dynamic buttons)
    document.addEventListener('click', (e) => {
        if (e.target.closest('.view-json-btn')) {
            const btn = e.target.closest('.view-json-btn');
            handleViewJson(btn.dataset.json);
        }
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeModal();
    });
}

// ============================================
// Handler Functions
// ============================================
function handleScenarioChange(e) {
    const scenarioId = e.target.value;

    if (!scenarioId) {
        // No scenario selected
        elements.emailPreview.classList.add('hidden');
        elements.emptyState.classList.remove('hidden');
        elements.submitBtn.disabled = true;
        state.selectedScenario = null;
        return;
    }

    const scenario = demoScenarios[scenarioId];
    if (scenario) {
        state.selectedScenario = scenario;
        populateEmailPreview(scenario);

        // Reset pipeline
        resetPipeline();

        addLog('info', `Scenario loaded: ${scenario.category} request from ${scenario.user_id}`);
    }
}

function populateEmailPreview(scenario) {
    // Show email preview, hide empty state
    elements.emailPreview.classList.remove('hidden');
    elements.emptyState.classList.add('hidden');
    elements.submitBtn.disabled = false;

    // Category badge
    elements.categoryBadge.textContent = scenario.category;
    elements.categoryBadge.className = `category-badge ${scenario.category.toLowerCase()}`;

    // From email - HIDDEN for PII
    // elements.fromEmail.textContent = scenario.user_id;

    // Received timestamp
    const receivedDate = new Date(scenario.received_at);
    elements.receivedAt.textContent = receivedDate.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        hour12: true
    });

    // Confidence
    const confidencePercent = Math.round(scenario.confidence * 100);
    elements.confidenceFill.style.width = `${confidencePercent}%`;
    elements.confidenceValue.textContent = `${confidencePercent}%`;

    // Email body - clean up the duplicated text if present
    let emailText = scenario.email_body || '';

    // The email_body often has duplicate content (formatted + plain text concatenated)
    // Look for the signature pattern and take content up to and including first signature
    const signatureMatch = emailText.match(/Best regards,[\r\n]+[A-Za-z\s]+/);
    if (signatureMatch) {
        const firstSignatureEnd = emailText.indexOf(signatureMatch[0]) + signatureMatch[0].length;
        // Check if there's substantial content after the signature (indicating duplication)
        const afterSignature = emailText.substring(firstSignatureEnd).trim();
        if (afterSignature.length > 50) {
            // There's duplicated content after - truncate to just the formatted part
            emailText = emailText.substring(0, firstSignatureEnd);
        }
    }

    // Clean up extra whitespace
    emailText = emailText.replace(/(\r\n){3,}/g, '\r\n\r\n').trim();
    elements.emailBody.textContent = emailText;

    // Attachments
    renderAttachments(scenario.attachments);
}

function renderAttachments(attachments) {
    if (!attachments || attachments.length === 0) {
        elements.attachmentsList.innerHTML = `
            <span class="no-attachments">No attachments</span>
        `;
        return;
    }

    elements.attachmentsList.innerHTML = attachments.map(att => {
        const isPdf = att.mimeType === 'application/pdf';
        const iconClass = isPdf ? 'file-icon' : 'image-icon';
        const iconSvg = isPdf
            ? `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
               </svg>`
            : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                <circle cx="8.5" cy="8.5" r="1.5"/>
                <polyline points="21 15 16 10 5 21"/>
               </svg>`;

        // Create Blob URL for base64 data
        let fileUrl = '#';
        if (att.data && att.data.__type__ === 'bytes' && att.data.encoding === 'base64') {
            try {
                const blob = base64ToBlob(att.data.data, att.mimeType);
                fileUrl = URL.createObjectURL(blob);
            } catch (e) {
                console.error('Error creating blob for attachment:', e);
            }
        } else if (att.path) {
            fileUrl = att.path;
        }

        return `
            <a href="${fileUrl}" target="_blank" class="attachment-chip" title="Open in new tab">
                <span class="${iconClass}">${iconSvg}</span>
                <span>${att.filename}</span>
            </a>
        `;
    }).join('');
}

// Helper to convert base64 to Blob
function base64ToBlob(base64, mimeType) {
    const byteCharacters = atob(base64);
    const byteArrays = [];

    for (let offset = 0; offset < byteCharacters.length; offset += 512) {
        const slice = byteCharacters.slice(offset, offset + 512);
        const byteNumbers = new Array(slice.length);

        for (let i = 0; i < slice.length; i++) {
            byteNumbers[i] = slice.charCodeAt(i);
        }

        const byteArray = new Uint8Array(byteNumbers);
        byteArrays.push(byteArray);
    }

    return new Blob(byteArrays, { type: mimeType });
}

async function handleSubmit() {
    if (state.isProcessing || !state.selectedScenario) return;

    // Start processing
    state.isProcessing = true;
    state.pipelineStep = 0;

    // Update button state
    elements.submitBtn.querySelector('.btn-content').classList.add('hidden');
    elements.submitBtn.querySelector('.btn-loader').classList.remove('hidden');
    elements.submitBtn.disabled = true;

    // Start timer
    startTimer();

    addLog('info', '🚀 Starting email processing pipeline...');

    // Simulate pipeline execution
    await runPipeline();
}

async function runPipeline() {
    const scenario = state.selectedScenario;
    const hasImages = scenario.attachments && scenario.attachments.some(a =>
        a.mimeType && a.mimeType.startsWith('image/')
    );
    const hasPdfs = scenario.attachments && scenario.attachments.some(a =>
        a.mimeType === 'application/pdf'
    );

    const steps = [
        {
            name: 'classification',
            duration: 1500,
            log: '📧 Classifying email intent...',
            onComplete: () => {
                // Update result category
                elements.resultCategory.textContent = scenario.category;
                elements.resultCategory.className = `result-value category-${scenario.category.toLowerCase()}`;

                const conf = Math.round(scenario.confidence * 100);
                elements.resultConfidenceFill.style.width = `${conf}%`;
                elements.resultConfidenceValue.textContent = `${conf}%`;
            }
        },
        {
            name: 'parsing',
            duration: 2000,
            log: '📄 Parsing attached documents with LlamaParse...',
            onComplete: () => {
                if (hasPdfs) {
                    const pdfs = scenario.attachments.filter(a => a.mimeType === 'application/pdf');
                    elements.parsedFiles.innerHTML = pdfs.map(p => `
                        <div class="result-file">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="20 6 9 17 4 12"/>
                            </svg>
                            <span>${p.filename}</span>
                        </div>
                    `).join('');
                } else {
                    elements.parsedFiles.innerHTML = `<span class="no-images-text">No PDF documents to parse</span>`;
                }
            }
        },
        {
            name: 'defect',
            duration: hasImages ? 2500 : 1000,
            log: hasImages
                ? '🔍 Analyzing defect images with Gemini Vision...'
                : '🔍 Checking for defect images...',
            onComplete: () => {
                if (hasImages) {
                    const images = scenario.attachments.filter(a =>
                        a.mimeType && a.mimeType.startsWith('image/')
                    );
                    elements.defectAnalysis.innerHTML = `
                        <div class="defect-result">
                            <span class="defect-status">✓ ${images.length} image(s) analyzed</span>
                            <span class="defect-detail">Defect confirmed - visible damage detected</span>
                        </div>
                    `;
                } else {
                    elements.defectAnalysis.innerHTML = `<span class="no-images-text">No defect images in this request</span>`;
                }
            }
        },
        {
            name: 'extraction',
            duration: 3000,
            log: '🧠 Extracting structured data with Gemini 3...'
        },
        {
            name: 'verification',
            duration: 2500,
            log: '🔐 Verifying order in database...'
        },
        {
            name: 'adjudication',
            duration: 3000,
            log: '⚖️ Evaluating against return policy...'
        },
        {
            name: 'decision',
            duration: 1500,
            log: '✅ Generating final decision...'
        }
    ];

    for (let i = 0; i < steps.length; i++) {
        const step = steps[i];
        const stepElement = document.querySelector(`[data-step="${step.name}"]`);

        // Set step as active
        stepElement.classList.add('active');
        stepElement.querySelector('.step-status').textContent = 'Processing...';
        stepElement.querySelector('.step-status').className = 'step-status processing';

        addLog('info', step.log);

        // Wait for step duration
        await sleep(step.duration);

        // Call onComplete callback if exists
        if (step.onComplete) {
            step.onComplete();
        }

        // Mark step as completed
        stepElement.classList.remove('active');
        stepElement.classList.add('completed');
        stepElement.querySelector('.step-status').textContent = 'Completed';
        stepElement.querySelector('.step-status').className = 'step-status completed';

        // Show step result
        const resultElement = stepElement.querySelector('.step-result');
        if (resultElement) {
            resultElement.classList.remove('hidden');
        }

        // Add completion log
        addLog('success', `✓ ${step.name.charAt(0).toUpperCase() + step.name.slice(1)} completed`);
    }

    // Pipeline complete
    stopTimer();
    state.isProcessing = false;

    // Reset button
    elements.submitBtn.querySelector('.btn-content').classList.remove('hidden');
    elements.submitBtn.querySelector('.btn-loader').classList.add('hidden');
    elements.submitBtn.disabled = false;

    addLog('success', `🎉 Pipeline completed! ${state.selectedScenario.category} request APPROVED.`);
}

// ============================================
// Timer Functions
// ============================================
function startTimer() {
    state.startTime = Date.now();
    elements.pipelineTimer.classList.remove('hidden');

    state.timerInterval = setInterval(() => {
        const elapsed = Date.now() - state.startTime;
        const seconds = Math.floor(elapsed / 1000);
        const minutes = Math.floor(seconds / 60);
        const secs = seconds % 60;
        elements.timerValue.textContent = `${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    }, 100);
}

function stopTimer() {
    if (state.timerInterval) {
        clearInterval(state.timerInterval);
        state.timerInterval = null;
    }
}

// ============================================
// Logs Functions
// ============================================
function toggleLogs() {
    elements.logsContainer.classList.toggle('collapsed');
    elements.logsToggle.classList.toggle('collapsed');
}

function addLog(type, message) {
    const time = new Date().toLocaleTimeString('en-US', {
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });

    const logEntry = document.createElement('div');
    logEntry.className = `log-entry ${type}`;
    logEntry.innerHTML = `
        <span class="log-time">${time}</span>
        <span class="log-message">${message}</span>
    `;

    elements.logsContainer.appendChild(logEntry);
    elements.logsContainer.scrollTop = elements.logsContainer.scrollHeight;
}

// ============================================
// Modal Functions
// ============================================
function handleViewJson(type) {
    if (!state.selectedScenario) return;

    // For scenarios loaded from JSON, show the raw scenario data
    let data;
    let title;

    if (type === 'extracted') {
        // Show the email classification/extraction data
        data = {
            category: state.selectedScenario.category,
            confidence: state.selectedScenario.confidence,
            user_id: state.selectedScenario.user_id,
            received_at: state.selectedScenario.received_at,
            email_body: state.selectedScenario.email_body,
            attachments: state.selectedScenario.attachments ?
                state.selectedScenario.attachments.map(a => ({
                    filename: a.filename,
                    mimeType: a.mimeType
                })) : []
        };
        title = 'Extracted Email Data';
    } else {
        // Show verification status (mock for demo)
        data = {
            status: 'verified',
            category: state.selectedScenario.category,
            confidence: state.selectedScenario.confidence,
            user_id: state.selectedScenario.user_id,
            received_at: state.selectedScenario.received_at
        };
        title = 'Verified Order Data';
    }

    elements.modalTitle.textContent = title;
    elements.jsonContent.querySelector('code').textContent = JSON.stringify(data, null, 2);
    elements.jsonModal.classList.remove('hidden');
}

function closeModal() {
    elements.jsonModal.classList.add('hidden');
}

function copyJsonToClipboard() {
    const json = elements.jsonContent.querySelector('code').textContent;
    navigator.clipboard.writeText(json).then(() => {
        const originalText = elements.copyJsonBtn.innerHTML;
        elements.copyJsonBtn.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                <polyline points="20 6 9 17 4 12"/>
            </svg>
            Copied!
        `;
        setTimeout(() => {
            elements.copyJsonBtn.innerHTML = originalText;
        }, 2000);
    });
}

// ============================================
// Pipeline Functions
// ============================================
function resetPipeline() {
    elements.pipelineSteps.forEach(step => {
        step.classList.remove('active', 'completed', 'error');
        step.querySelector('.step-status').textContent = 'Pending';
        step.querySelector('.step-status').className = 'step-status pending';

        const resultElement = step.querySelector('.step-result');
        if (resultElement) {
            resultElement.classList.add('hidden');
        }
    });

    elements.pipelineTimer.classList.add('hidden');
    elements.timerValue.textContent = '00:00';
}

// ============================================
// Utility Functions
// ============================================
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// ============================================
// Initialize Application
// ============================================
async function init() {
    // Load scenarios from JSON files
    console.log('Initializing app...');
    await loadScenarios();

    // Populate dropdown with loaded scenarios
    populateScenarioDropdown();

    const loadedCount = Object.keys(demoScenarios).length;
    console.log(`Loaded ${loadedCount} scenarios total`);

    initializeEventListeners();
    addLog('info', 'System initialized. Select a demo scenario to begin...');
}

// Start the application when DOM is ready
document.addEventListener('DOMContentLoaded', init);
