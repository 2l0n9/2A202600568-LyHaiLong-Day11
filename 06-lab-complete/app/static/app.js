// State management
let apiKey = localStorage.getItem('agent_api_key') || '';
let isCheckingHealth = false;
let isCheckingMetrics = false;

// DOM Elements
const apiKeyInput = document.getElementById('api-key-input');
const toggleKeyVisibilityBtn = document.getElementById('toggle-key-visibility');
const saveKeyBtn = document.getElementById('save-key-btn');
const keyWarning = document.getElementById('key-warning');
const metricsCard = document.getElementById('metrics-card');

const healthStatus = document.getElementById('health-status');
const readyStatus = document.getElementById('ready-status');
const uptimeVal = document.getElementById('uptime-val');

const totalRequestsEl = document.getElementById('total-requests');
const errorCountEl = document.getElementById('error-count');
const budgetRatioEl = document.getElementById('budget-ratio');
const budgetProgressEl = document.getElementById('budget-progress');

const chatMessages = document.getElementById('chat-messages');
const chatTextarea = document.getElementById('chat-textarea');
const sendMsgBtn = document.getElementById('send-msg-btn');
const clearChatBtn = document.getElementById('clear-chat-btn');

// Initialization
document.addEventListener('DOMContentLoaded', () => {
    // Restore saved API Key
    if (apiKey) {
        apiKeyInput.value = apiKey;
        keyWarning.classList.add('hidden');
        metricsCard.classList.remove('hidden');
        sendMsgBtn.disabled = false;
    } else {
        keyWarning.classList.remove('hidden');
        metricsCard.classList.add('hidden');
        sendMsgBtn.disabled = true;
    }

    // Event Listeners
    toggleKeyVisibilityBtn.addEventListener('click', toggleKeyVisibility);
    saveKeyBtn.addEventListener('click', saveApiKey);
    chatTextarea.addEventListener('input', handleTextInput);
    chatTextarea.addEventListener('keydown', handleKeyDown);
    sendMsgBtn.addEventListener('click', sendMessage);
    clearChatBtn.addEventListener('click', clearChat);

    // Setup suggested query buttons
    setupSuggestions();

    // Start background loops
    pollSystemStatus();
    pollMetrics();
    setInterval(pollSystemStatus, 5000);
    setInterval(pollMetrics, 10000);
});

// UI Event Handlers
function toggleKeyVisibility() {
    const isPassword = apiKeyInput.type === 'password';
    apiKeyInput.type = isPassword ? 'text' : 'password';
    toggleKeyVisibilityBtn.innerHTML = isPassword ? '<i class="fa-solid fa-eye-slash"></i>' : '<i class="fa-solid fa-eye"></i>';
}

function saveApiKey() {
    apiKey = apiKeyInput.value.trim();
    localStorage.setItem('agent_api_key', apiKey);
    
    if (apiKey) {
        keyWarning.classList.add('hidden');
        metricsCard.classList.remove('hidden');
        sendMsgBtn.disabled = chatTextarea.value.trim() === '';
        
        // Show success visual feedback
        saveKeyBtn.innerHTML = '<i class="fa-solid fa-check-double"></i> Saved!';
        saveKeyBtn.style.background = 'var(--success)';
        setTimeout(() => {
            saveKeyBtn.innerHTML = '<i class="fa-solid fa-check"></i> Save Key';
            saveKeyBtn.style.background = '';
        }, 1500);

        // Fetch metrics immediately
        pollMetrics();
    } else {
        keyWarning.classList.remove('hidden');
        metricsCard.classList.add('hidden');
        sendMsgBtn.disabled = true;
    }
}

function handleTextInput() {
    // Auto-resize textarea
    chatTextarea.style.height = 'auto';
    chatTextarea.style.height = (chatTextarea.scrollHeight) + 'px';
    
    // Enable/disable send button
    const hasText = chatTextarea.value.trim() !== '';
    sendMsgBtn.disabled = !hasText || !apiKey;
}

function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (apiKey && chatTextarea.value.trim() !== '') {
            sendMessage();
        }
    }
}

function setupSuggestions() {
    const suggestButtons = document.querySelectorAll('.suggest-btn');
    suggestButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            chatTextarea.value = btn.innerText;
            handleTextInput();
            chatTextarea.focus();
            if (apiKey) {
                sendMessage();
            }
        });
    });
}

function clearChat() {
    // Remove all message bubbles except system intro
    const introMsg = chatMessages.firstElementChild;
    chatMessages.innerHTML = '';
    if (introMsg) {
        chatMessages.appendChild(introMsg);
    }
}

// Background API calls
async function pollSystemStatus() {
    if (isCheckingHealth) return;
    isCheckingHealth = true;
    
    try {
        const response = await fetch('/health');
        const data = await response.json();
        
        if (response.ok) {
            updateStatusIndicator(healthStatus, 'status-ok', 'Healthy');
            if (data.uptime_seconds) {
                uptimeVal.innerText = formatUptime(data.uptime_seconds);
            }
            if (data.version) {
                document.getElementById('app-version').innerText = data.version;
            }
            if (data.environment) {
                const envBadge = document.getElementById('env-badge');
                envBadge.innerText = data.environment;
                envBadge.className = `badge ${data.environment === 'production' ? 'btn-danger' : ''}`;
            }
        } else {
            updateStatusIndicator(healthStatus, 'status-error', 'Unhealthy');
        }
    } catch (e) {
        updateStatusIndicator(healthStatus, 'status-error', 'Offline');
    }

    try {
        const response = await fetch('/ready');
        if (response.ok) {
            updateStatusIndicator(readyStatus, 'status-ok', 'Ready');
        } else {
            updateStatusIndicator(readyStatus, 'status-error', 'Not Ready');
        }
    } catch (e) {
        updateStatusIndicator(readyStatus, 'status-error', 'Disconnected');
    }
    
    isCheckingHealth = false;
}

async function pollMetrics() {
    if (!apiKey || isCheckingMetrics) return;
    isCheckingMetrics = true;

    try {
        const response = await fetch('/metrics', {
            headers: { 'X-API-Key': apiKey }
        });
        
        if (response.ok) {
            const data = await response.json();
            totalRequestsEl.innerText = data.total_requests ?? 0;
            errorCountEl.innerText = data.error_count ?? 0;
            
            const cost = data.daily_cost_usd ?? 0;
            const budget = data.daily_budget_usd ?? 5.0;
            budgetRatioEl.innerText = `$${cost.toFixed(4)} / $${budget.toFixed(2)}`;
            
            const pct = Math.min(100, data.budget_used_pct ?? 0);
            budgetProgressEl.style.width = `${pct}%`;
            if (pct > 90) {
                budgetProgressEl.style.background = 'var(--danger)';
            } else if (pct > 70) {
                budgetProgressEl.style.background = 'var(--warning)';
            } else {
                budgetProgressEl.style.background = 'var(--primary-gradient)';
            }
        }
    } catch (e) {
        console.error('Failed to fetch metrics:', e);
    }
    
    isCheckingMetrics = false;
}

// Chat API Calls
async function sendMessage() {
    const question = chatTextarea.value.trim();
    if (!question || !apiKey) return;

    // Clear textarea
    chatTextarea.value = '';
    handleTextInput();

    // 1. Render User Message
    appendMessage(question, 'user', new Date().toLocaleTimeString());

    // 2. Render Loading Indicator
    const loaderId = appendLoadingIndicator();

    try {
        // 3. POST request to /ask
        const response = await fetch('/ask', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-API-Key': apiKey
            },
            body: JSON.stringify({ question })
        });
        
        // Remove loader
        removeMessage(loaderId);

        if (response.ok) {
            const data = await response.json();
            // Render Assistant Message with formatting
            appendMessage(data.answer, 'assistant', new Date().toLocaleTimeString(), data.model);
            // Refresh metrics immediately
            pollMetrics();
        } else {
            const errData = await response.json().catch(() => ({ detail: 'Unknown Error' }));
            appendMessage(`❌ Lỗi (${response.status}): ${errData.detail}`, 'assistant', new Date().toLocaleTimeString(), null, true);
        }
    } catch (e) {
        removeMessage(loaderId);
        appendMessage(`❌ Failed to send request: ${e.message}`, 'assistant', new Date().toLocaleTimeString(), null, true);
    }
}

// Helpers
function updateStatusIndicator(el, className, text) {
    el.className = `status-indicator ${className}`;
    el.querySelector('.text').innerText = text;
}

function formatUptime(seconds) {
    if (seconds < 60) return `${seconds.toFixed(0)}s`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m`;
    const hours = Math.floor(minutes / 60);
    const remainingMins = minutes % 60;
    return `${hours}h ${remainingMins}m`;
}

function appendMessage(text, sender, time, model = null, isError = false) {
    const isUser = sender === 'user';
    const msgCard = document.createElement('div');
    msgCard.className = `msg-bubble ${isUser ? 'user-msg' : 'assistant-msg'}`;
    
    const avatarIcon = isUser ? 'fa-user' : 'fa-robot';
    
    let modelBadgeHTML = '';
    if (model) {
        modelBadgeHTML = `<span class="badge" style="font-size: 8px; margin-left: 8px; vertical-align: middle;">${model}</span>`;
    }

    // Format Markdown-like citation syntax: [1], [2], [Luật...]
    let formattedText = escapeHtml(text);
    
    // Parse Sources footnote divider
    let sourcesHTML = '';
    const sourcesIndex = formattedText.indexOf('\n\nSources:\n');
    if (sourcesIndex !== -1) {
        const sourceText = formattedText.substring(sourcesIndex + 11);
        formattedText = formattedText.substring(0, sourcesIndex);
        
        const sourceLines = sourceText.split('\n').filter(l => l.trim() !== '');
        if (sourceLines.length > 0) {
            sourcesHTML = `
                <div class="sources-container">
                    <div class="sources-title"><i class="fa-solid fa-link"></i> Nguồn tham khảo:</div>
                    <div class="sources-list">
                        ${sourceLines.map(line => {
                            const match = line.match(/^\[(\d+)\]\s*(.*)$/);
                            if (match) {
                                return `<div class="source-item"><span class="badge" style="font-size: 9px;">[${match[1]}]</span> ${match[2]}</div>`;
                            }
                            return `<div class="source-item">${line}</div>`;
                        }).join('')}
                    </div>
                </div>
            `;
        }
    }

    // Format inline bracket citations: [1], [Điều 2 Luật...]
    formattedText = formattedText.replace(/\[([^\]]+)\]/g, (match, p1) => {
        return `<span class="citation-badge" title="Source: ${p1}"><i class="fa-solid fa-file-invoice"></i> ${p1}</span>`;
    });

    // Replace linebreaks with <br>
    formattedText = formattedText.replace(/\n/g, '<br>');

    msgCard.innerHTML = `
        <div class="msg-avatar"><i class="fa-solid ${avatarIcon}"></i></div>
        <div class="msg-content-wrapper">
            <div class="msg-content" style="${isError ? 'background-color: var(--danger-bg); border-color: rgba(239, 68, 68, 0.2);' : ''}">
                <p>${formattedText}</p>
                ${sourcesHTML}
            </div>
            <span class="msg-time">${time}${modelBadgeHTML}</span>
        </div>
    `;

    chatMessages.appendChild(msgCard);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function appendLoadingIndicator() {
    const id = 'loader_' + Date.now();
    const msgCard = document.createElement('div');
    msgCard.className = 'msg-bubble assistant-msg';
    msgCard.id = id;
    
    msgCard.innerHTML = `
        <div class="msg-avatar"><i class="fa-solid fa-robot"></i></div>
        <div class="msg-content-wrapper">
            <div class="msg-content">
                <div class="typing-indicator">
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                </div>
            </div>
            <span class="msg-time">Generating Answer...</span>
        </div>
    `;
    
    chatMessages.appendChild(msgCard);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return id;
}

function removeMessage(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

function escapeHtml(string) {
    return String(string)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}
