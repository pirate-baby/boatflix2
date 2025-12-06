/**
 * Media Manager - Common JavaScript functionality
 */

// ============================================================================
// Toast Notifications
// ============================================================================

/**
 * Show a toast notification
 * @param {string} message - The message to display
 * @param {string} type - Type of toast: 'success', 'error', 'info', 'warning'
 * @param {number} duration - Duration in milliseconds (default: 4000)
 */
function showToast(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    // Icon based on type
    const icons = {
        success: '✓',
        error: '✕',
        warning: '⚠',
        info: 'ℹ'
    };

    toast.innerHTML = `
        <span class="toast-icon">${icons[type] || icons.info}</span>
        <span class="toast-message">${escapeHtml(message)}</span>
        <button class="toast-close" onclick="this.parentElement.remove()">×</button>
    `;

    container.appendChild(toast);

    // Animate in
    requestAnimationFrame(() => {
        toast.classList.add('toast-show');
    });

    // Auto remove
    setTimeout(() => {
        toast.classList.remove('toast-show');
        toast.classList.add('toast-hide');
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Escape HTML special characters to prevent XSS
 * @param {string} text - Text to escape
 * @returns {string} Escaped text
 */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Format file size in human-readable format
 * @param {number} bytes - Size in bytes
 * @returns {string} Formatted size
 */
function formatFileSize(bytes) {
    if (bytes >= 1073741824) {
        return (bytes / 1073741824).toFixed(2) + ' GB';
    } else if (bytes >= 1048576) {
        return (bytes / 1048576).toFixed(1) + ' MB';
    } else if (bytes >= 1024) {
        return Math.round(bytes / 1024) + ' KB';
    }
    return bytes + ' B';
}

/**
 * Format duration in seconds to HH:MM:SS or MM:SS
 * @param {number} seconds - Duration in seconds
 * @returns {string} Formatted duration
 */
function formatDuration(seconds) {
    if (!seconds || isNaN(seconds)) return '--:--';

    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);

    if (h > 0) {
        return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
    }
    return `${m}:${s.toString().padStart(2, '0')}`;
}

/**
 * Format ISO date string to relative time
 * @param {string} isoString - ISO date string
 * @returns {string} Relative time (e.g., "5m ago")
 */
function formatRelativeTime(isoString) {
    if (!isoString) return 'Unknown';

    const date = new Date(isoString);
    const now = new Date();
    const diff = (now - date) / 1000;

    if (diff < 60) return 'Just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;

    return date.toLocaleDateString();
}

/**
 * Format ISO date string to local date/time
 * @param {string} isoString - ISO date string
 * @returns {string} Formatted date/time
 */
function formatDateTime(isoString) {
    if (!isoString) return '-';

    const date = new Date(isoString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit'
    });
}

// ============================================================================
// Loading States
// ============================================================================

/**
 * Show loading state on a button
 * @param {HTMLElement} button - The button element
 * @param {boolean} loading - Whether to show loading state
 */
function setButtonLoading(button, loading) {
    if (!button) return;

    const textSpan = button.querySelector('.btn-text');
    const loadingSpan = button.querySelector('.btn-loading');

    if (loading) {
        button.disabled = true;
        if (textSpan) textSpan.style.display = 'none';
        if (loadingSpan) loadingSpan.style.display = 'inline-block';
    } else {
        button.disabled = false;
        if (textSpan) textSpan.style.display = 'inline';
        if (loadingSpan) loadingSpan.style.display = 'none';
    }
}

// ============================================================================
// Keyboard Shortcuts
// ============================================================================

document.addEventListener('keydown', (e) => {
    // Escape to close modals
    if (e.key === 'Escape') {
        const openDialogs = document.querySelectorAll('dialog[open]');
        openDialogs.forEach(dialog => dialog.close());
    }
});

// ============================================================================
// HTMX Extensions
// ============================================================================

// Add loading class to elements during HTMX requests
document.addEventListener('htmx:beforeRequest', (evt) => {
    evt.detail.elt.classList.add('htmx-loading');
});

document.addEventListener('htmx:afterRequest', (evt) => {
    evt.detail.elt.classList.remove('htmx-loading');
});

// Handle HTMX errors
document.addEventListener('htmx:responseError', (evt) => {
    console.error('HTMX request failed:', evt.detail);
    showToast('Request failed. Please try again.', 'error');
});

// ============================================================================
// Auto-refresh handling
// ============================================================================

// Pause auto-refresh when tab is not visible
let refreshPaused = false;

document.addEventListener('visibilitychange', () => {
    refreshPaused = document.hidden;
});

// ============================================================================
// Form Helpers
// ============================================================================

/**
 * Get form data as an object
 * @param {HTMLFormElement} form - The form element
 * @returns {Object} Form data as key-value pairs
 */
function getFormData(form) {
    const formData = new FormData(form);
    const data = {};

    for (const [key, value] of formData.entries()) {
        data[key] = value;
    }

    return data;
}

/**
 * Submit form data as JSON
 * @param {string} url - API endpoint URL
 * @param {Object} data - Data to send
 * @param {string} method - HTTP method (default: POST)
 * @returns {Promise} Response promise
 */
async function submitJson(url, data, method = 'POST') {
    const response = await fetch(url, {
        method,
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(data),
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Request failed' }));
        throw new Error(error.detail || 'Request failed');
    }

    return response.json();
}

// ============================================================================
// Confidence Helpers
// ============================================================================

/**
 * Get CSS class for confidence level
 * @param {number|string} confidence - Confidence value (0-1) or string
 * @returns {string} CSS class name
 */
function getConfidenceClass(confidence) {
    if (typeof confidence === 'string') {
        return confidence === 'high' ? 'success' :
               confidence === 'medium' ? 'warning' : 'error';
    }

    return confidence >= 0.8 ? 'success' :
           confidence >= 0.5 ? 'warning' : 'error';
}

/**
 * Get confidence label
 * @param {number|string} confidence - Confidence value (0-1) or string
 * @returns {string} Label text
 */
function getConfidenceLabel(confidence) {
    if (typeof confidence === 'string') {
        return confidence;
    }

    return confidence >= 0.8 ? 'high' :
           confidence >= 0.5 ? 'medium' : 'low';
}

// ============================================================================
// Initialize
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Set up any global event listeners
    console.log('Media Manager UI initialized');
});
