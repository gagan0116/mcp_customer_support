/**
 * Customer Support AI Demo - Frontend Application
 * Simplified version with pre-defined demo scenarios
 */

// ============================================
// Demo Scenarios Configuration
// These will be loaded from /scenarios/*.json in the future
// ============================================
const demoScenarios = {
    scenario1: {
        category: "RETURN",
        confidence: 0.99,
        user_id: "kumar17.amara@gmail.com",
        received_at: "2026-01-26T22:16:13+00:00",
        email_body: `Hello,

I am writing to request a return for my recent purchase from SuperStore.

Order ID: MX-2012-TP2113082-41207
Invoice Number: 5732
Item: Apple Smart Phone, Full Size (Quantity: 5)
Order Date: October 25, 2012

I would like to initiate a return for the above item. Please let me know the return eligibility, next steps, and any instructions required to proceed, including the return shipping process.

Thank you for your assistance. I look forward to your response.

Best regards,
Theone Pippenger`,
        attachments: [
            {
                filename: "invoice_Theone_Pippenger_5732.pdf",
                mimeType: "application/pdf",
                path: "scenarios/scenario1/invoice_Theone_Pippenger_5732.pdf"
            }
        ],
        // Mock extracted data for this scenario
        extractedData: {
            customer_email: "kumar17.amara@gmail.com",
            full_name: "Theone Pippenger",
            phone: null,
            invoice_number: "5732",
            order_invoice_id: "MX-2012-TP2113082-41207",
            order_date: "2012-10-25",
            return_request_date: "2026-01-26",
            ship_mode: "Standard",
            ship_city: "New York",
            ship_state: "New York",
            ship_country: "USA",
            currency: "USD",
            discount_amount: 0,
            shipping_amount: 12.99,
            total_amount: 549.95,
            order_items: [
                {
                    sku: "APPLE-PHONE-FS",
                    item_name: "Apple Smart Phone, Full Size",
                    category: "Electronics",
                    subcategory: "Smartphones",
                    quantity: 5,
                    unit_price: 107.99,
                    line_total: 539.95
                }
            ],
            item_condition: "UNOPENED",
            return_category: "RETURN",
            return_reason_category: "CHANGE_OF_MIND",
            return_reason: "Customer requesting standard return",
            confidence_score: 0.99
        },
        verifiedData: {
            status: "verified",
            data: {
                customer: {
                    customer_id: "CUST-2012-TP21130",
                    customer_email: "kumar17.amara@gmail.com",
                    full_name: "Theone Pippenger",
                    verified: true
                },
                order_details: {
                    order_id: "MX-2012-TP2113082-41207",
                    order_date: "2012-10-25",
                    total_amount: 549.95,
                    status: "DELIVERED",
                    delivery_date: "2012-10-30"
                },
                items: [
                    {
                        sku: "APPLE-PHONE-FS",
                        item_name: "Apple Smart Phone, Full Size",
                        quantity: 5,
                        unit_price: 107.99
                    }
                ]
            },
            return_category: "RETURN",
            confidence_score: 0.99
        }
    },
    scenario2: {
        category: "REFUND",
        confidence: 0.97,
        user_id: "sarah.johnson@gmail.com",
        received_at: "2026-01-28T14:32:45+00:00",
        email_body: `Dear Customer Support,

I am requesting a full refund for my MacBook Pro purchase.

Order Details:
- Order ID: ORD-2026-SJ-78432
- Invoice: INV-78432
- Product: MacBook Pro 14" M3 Pro
- Purchase Date: January 10, 2026
- Amount: $1,999.00

The laptop arrived with a defective display - there are visible dead pixels in the top right corner that appeared immediately upon first boot. I have documented this defect with photos attached.

This is clearly a manufacturing defect and I would like a full refund processed as soon as possible.

Thank you,
Sarah Johnson`,
        attachments: [
            {
                filename: "invoice_sarah_johnson_78432.pdf",
                mimeType: "application/pdf",
                path: "scenarios/scenario2/invoice_sarah_johnson_78432.pdf"
            },
            {
                filename: "defect_photo_1.jpg",
                mimeType: "image/jpeg",
                path: "scenarios/scenario2/defect_photo_1.jpg"
            }
        ],
        extractedData: {
            customer_email: "sarah.johnson@gmail.com",
            full_name: "Sarah Johnson",
            phone: null,
            invoice_number: "INV-78432",
            order_invoice_id: "ORD-2026-SJ-78432",
            order_date: "2026-01-10",
            return_request_date: "2026-01-28",
            ship_mode: "Express",
            ship_city: "Los Angeles",
            ship_state: "California",
            ship_country: "USA",
            currency: "USD",
            discount_amount: 0,
            shipping_amount: 0,
            total_amount: 1999.00,
            order_items: [
                {
                    sku: "MBP-14-M3P-512",
                    item_name: "MacBook Pro 14\" M3 Pro",
                    category: "Electronics",
                    subcategory: "Laptops",
                    quantity: 1,
                    unit_price: 1999.00,
                    line_total: 1999.00
                }
            ],
            item_condition: "DAMAGED_DEFECTIVE",
            return_category: "REFUND",
            return_reason_category: "DEFECTIVE",
            return_reason: "Display has visible dead pixels - manufacturing defect",
            confidence_score: 0.97
        },
        verifiedData: {
            status: "verified",
            data: {
                customer: {
                    customer_id: "CUST-2026-SJ001",
                    customer_email: "sarah.johnson@gmail.com",
                    full_name: "Sarah Johnson",
                    verified: true
                },
                order_details: {
                    order_id: "ORD-2026-SJ-78432",
                    order_date: "2026-01-10",
                    total_amount: 1999.00,
                    status: "DELIVERED",
                    delivery_date: "2026-01-12"
                },
                items: [
                    {
                        sku: "MBP-14-M3P-512",
                        item_name: "MacBook Pro 14\" M3 Pro",
                        quantity: 1,
                        unit_price: 1999.00
                    }
                ]
            },
            return_category: "REFUND",
            defect_confirmed: true,
            confidence_score: 0.97
        }
    },
    scenario3: {
        category: "REPLACEMENT",
        confidence: 0.95,
        user_id: "alex.chen@outlook.com",
        received_at: "2026-01-29T09:15:22+00:00",
        email_body: `Hello Support Team,

I need a replacement for my AirPods Pro that I purchased last week.

Order Information:
- Order #: ORD-2026-AC-55123
- Invoice #: INV-55123
- Product: AirPods Pro (2nd Generation)
- Price: $249.00

The left earbud is not producing any sound. I've tried resetting them multiple times and checked for firmware updates, but nothing works. The right earbud works perfectly fine.

Could you please send a replacement unit? I've attached my invoice for reference.

Best regards,
Alex Chen`,
        attachments: [
            {
                filename: "invoice_alex_chen_55123.pdf",
                mimeType: "application/pdf",
                path: "scenarios/scenario3/invoice_alex_chen_55123.pdf"
            }
        ],
        extractedData: {
            customer_email: "alex.chen@outlook.com",
            full_name: "Alex Chen",
            phone: null,
            invoice_number: "INV-55123",
            order_invoice_id: "ORD-2026-AC-55123",
            order_date: "2026-01-22",
            return_request_date: "2026-01-29",
            ship_mode: "Standard",
            ship_city: "Seattle",
            ship_state: "Washington",
            ship_country: "USA",
            currency: "USD",
            discount_amount: 0,
            shipping_amount: 0,
            total_amount: 249.00,
            order_items: [
                {
                    sku: "APP-2ND-GEN",
                    item_name: "AirPods Pro (2nd Generation)",
                    category: "Electronics",
                    subcategory: "Audio",
                    quantity: 1,
                    unit_price: 249.00,
                    line_total: 249.00
                }
            ],
            item_condition: "DAMAGED_DEFECTIVE",
            return_category: "REPLACEMENT",
            return_reason_category: "DEFECTIVE",
            return_reason: "Left earbud not producing sound - hardware malfunction",
            confidence_score: 0.95
        },
        verifiedData: {
            status: "verified",
            data: {
                customer: {
                    customer_id: "CUST-2026-AC001",
                    customer_email: "alex.chen@outlook.com",
                    full_name: "Alex Chen",
                    verified: true
                },
                order_details: {
                    order_id: "ORD-2026-AC-55123",
                    order_date: "2026-01-22",
                    total_amount: 249.00,
                    status: "DELIVERED",
                    delivery_date: "2026-01-25"
                },
                items: [
                    {
                        sku: "APP-2ND-GEN",
                        item_name: "AirPods Pro (2nd Generation)",
                        quantity: 1,
                        unit_price: 249.00
                    }
                ]
            },
            return_category: "REPLACEMENT",
            confidence_score: 0.95
        }
    },
    scenario4: {
        category: "RETURN",
        confidence: 0.98,
        user_id: "maria.garcia@yahoo.com",
        received_at: "2026-01-30T16:45:00+00:00",
        email_body: `Hi,

I'm writing to return my iPad Pro which has a cracked screen.

Details:
- Order Number: ORD-2026-MG-99012
- Invoice: INV-99012
- Item: iPad Pro 12.9" (6th Gen) - 256GB
- Purchase Date: January 5, 2026

The screen cracked during normal use - I was simply holding it when I noticed a crack spreading from the corner. This must be a manufacturing defect as I always use a protective case.

I've included photos showing the crack and my original invoice.

Please process this return at your earliest convenience.

Thank you,
Maria Garcia`,
        attachments: [
            {
                filename: "invoice_maria_garcia_99012.pdf",
                mimeType: "application/pdf",
                path: "scenarios/scenario4/invoice_maria_garcia_99012.pdf"
            },
            {
                filename: "cracked_screen.jpg",
                mimeType: "image/jpeg",
                path: "scenarios/scenario4/cracked_screen.jpg"
            },
            {
                filename: "cracked_screen_2.jpg",
                mimeType: "image/jpeg",
                path: "scenarios/scenario4/cracked_screen_2.jpg"
            }
        ],
        extractedData: {
            customer_email: "maria.garcia@yahoo.com",
            full_name: "Maria Garcia",
            phone: null,
            invoice_number: "INV-99012",
            order_invoice_id: "ORD-2026-MG-99012",
            order_date: "2026-01-05",
            return_request_date: "2026-01-30",
            ship_mode: "Express",
            ship_city: "Miami",
            ship_state: "Florida",
            ship_country: "USA",
            currency: "USD",
            discount_amount: 50.00,
            shipping_amount: 0,
            total_amount: 1049.00,
            order_items: [
                {
                    sku: "IPAD-PRO-129-256",
                    item_name: "iPad Pro 12.9\" (6th Gen) - 256GB",
                    category: "Electronics",
                    subcategory: "Tablets",
                    quantity: 1,
                    unit_price: 1099.00,
                    line_total: 1049.00
                }
            ],
            item_condition: "DAMAGED_DEFECTIVE",
            return_category: "RETURN",
            return_reason_category: "DEFECTIVE",
            return_reason: "Screen cracked during normal use - potential manufacturing defect",
            confidence_score: 0.98
        },
        verifiedData: {
            status: "verified",
            data: {
                customer: {
                    customer_id: "CUST-2026-MG001",
                    customer_email: "maria.garcia@yahoo.com",
                    full_name: "Maria Garcia",
                    verified: true
                },
                order_details: {
                    order_id: "ORD-2026-MG-99012",
                    order_date: "2026-01-05",
                    total_amount: 1049.00,
                    status: "DELIVERED",
                    delivery_date: "2026-01-08"
                },
                items: [
                    {
                        sku: "IPAD-PRO-129-256",
                        item_name: "iPad Pro 12.9\" (6th Gen) - 256GB",
                        quantity: 1,
                        unit_price: 1099.00
                    }
                ]
            },
            return_category: "RETURN",
            defect_images_analyzed: true,
            confidence_score: 0.98
        }
    }
};

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

    // From email
    elements.fromEmail.textContent = scenario.user_id;

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

    // Email body
    elements.emailBody.textContent = scenario.email_body;

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

        return `
            <a href="${att.path}" target="_blank" class="attachment-chip" title="Open in new tab">
                <span class="${iconClass}">${iconSvg}</span>
                <span>${att.filename}</span>
            </a>
        `;
    }).join('');
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
    const hasImages = scenario.attachments.some(a => a.mimeType.startsWith('image/'));
    const hasPdfs = scenario.attachments.some(a => a.mimeType === 'application/pdf');

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
                    const images = scenario.attachments.filter(a => a.mimeType.startsWith('image/'));
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

    const data = type === 'extracted'
        ? state.selectedScenario.extractedData
        : state.selectedScenario.verifiedData;
    const title = type === 'extracted' ? 'Extracted Order Data' : 'Verified Order Data';

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
function init() {
    initializeEventListeners();

    // Clear logs and add initial message
    elements.logsContainer.innerHTML = '';
    addLog('info', 'System initialized. Select a demo scenario to begin...');
}

// Start the application when DOM is ready
document.addEventListener('DOMContentLoaded', init);
