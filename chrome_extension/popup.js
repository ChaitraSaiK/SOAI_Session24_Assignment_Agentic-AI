// Immediate console log to verify script is loaded
console.log('Script loaded!');

// Configuration
const API_URL = 'http://127.0.0.1:8000';
const TIMEOUT = 10000; // 10 seconds

// Add after configuration
let userId = null;

document.addEventListener('DOMContentLoaded', function() {
    // Generate or retrieve user ID
    chrome.storage.local.get(['userId'], function(result) {
        if (result.userId) {
            userId = result.userId;
        } else {
            userId = 'user_' + Math.random().toString(36).substr(2, 9);
            chrome.storage.local.set({userId: userId});
        }
    });

    const statusDiv = document.getElementById('status');
    const dragZone = document.getElementById('dragZone');
    const questionTextarea = document.getElementById('question');
    const askButton = document.getElementById('askButton');
    let isProcessing = false;

    // Helper function to update status with appropriate styling
    function updateStatus(message, type) {
        statusDiv.textContent = message;
        statusDiv.className = `status-${type}`;
    }

    // Helper function to disable/enable buttons
    function setButtonsState(disabled) {
        document.querySelectorAll('button').forEach(button => {
            button.disabled = disabled;
        });
    }

    // Process events function
    async function processEvents(days) {
        if (isProcessing) return;
        isProcessing = true;
        setButtonsState(true);
        updateStatus('Processing your request...', 'processing');

        try {
            // First check if server is running
            const healthResponse = await fetch('http://127.0.0.1:8000/health');
            if (!healthResponse.ok) {
                throw new Error('Server is not running');
            }

            // Get the token
            const token = await chrome.identity.getAuthToken({ interactive: true });
            if (!token) {
                throw new Error('Failed to get authentication token');
            }

            // Process events
            const response = await fetch('http://127.0.0.1:8000/process-events', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    token: token.token,
                    days: days
                })
            });

            if (!response.ok) {
                throw new Error('Failed to process events');
            }

            const data = await response.json();
            updateStatus('Events processed successfully! Check your Telegram.', 'success');
            
            // Auto-close popup after success
            setTimeout(() => window.close(), 3000);

        } catch (error) {
            console.error('Error:', error);
            updateStatus(error.message, 'error');
        } finally {
            isProcessing = false;
            setButtonsState(false);
        }
    }

    // Ask LLM function
    async function askQuestion() {
        if (isProcessing) return;
        
        const question = questionTextarea.value.trim();
        if (!question) {
            updateStatus('Please enter a question', 'error');
            return;
        }

        isProcessing = true;
        setButtonsState(true);
        updateStatus('Processing your question...', 'processing');

        try {
            // First check if server is running
            const healthResponse = await fetch('http://127.0.0.1:8000/health');
            if (!healthResponse.ok) {
                throw new Error('Server is not running');
            }

            // Get the token
            const token = await chrome.identity.getAuthToken({ interactive: true });
            if (!token) {
                throw new Error('Failed to get authentication token');
            }

            // Send question to LLM with user ID
            const response = await fetch('http://127.0.0.1:8000/ask-llm', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    token: token.token,
                    question: question,
                    days: 30,
                    user_id: userId
                })
            });

            if (!response.ok) {
                throw new Error('Failed to process question');
            }

            const data = await response.json();
            
            // Store conversation history
            chrome.storage.local.set({
                conversationHistory: data.conversation_history
            });

            updateStatus('Question answered! Check your Telegram.', 'success');
            questionTextarea.value = '';  // Clear the textarea
            
            // Auto-close popup after success
            setTimeout(() => window.close(), 3000);

        } catch (error) {
            console.error('Error:', error);
            updateStatus(error.message, 'error');
        } finally {
            isProcessing = false;
            setButtonsState(false);
        }
    }

    // Button click handlers
    ['10', '15', '30'].forEach(days => {
        document.getElementById(`days${days}`).addEventListener('click', () => {
            processEvents(parseInt(days));
        });
    });

    // Ask button click handler
    askButton.addEventListener('click', askQuestion);

    // Enter key in textarea
    questionTextarea.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            askQuestion();
        }
    });

    // Drag and drop handlers
    dragZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dragZone.classList.add('dragover');
    });

    dragZone.addEventListener('dragleave', () => {
        dragZone.classList.remove('dragover');
    });

    dragZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dragZone.classList.remove('dragover');
        const files = e.dataTransfer.files;
        handleFiles(files);
    });

    dragZone.addEventListener('click', () => {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.ics,.csv';
        input.onchange = (e) => handleFiles(e.target.files);
        input.click();
    });

    function handleFiles(files) {
        if (files.length > 0) {
            const file = files[0];
            if (file.name.endsWith('.ics') || file.name.endsWith('.csv')) {
                // Here you can add logic to process calendar files
                updateStatus('File upload feature coming soon!', 'processing');
            } else {
                updateStatus('Please upload .ics or .csv files only', 'error');
            }
        }
    }

    // Add clear conversation button
    const clearButton = document.createElement('button');
    clearButton.textContent = 'Clear Conversation';
    clearButton.className = 'clear-button';
    clearButton.addEventListener('click', async () => {
        try {
            await fetch('http://127.0.0.1:8000/clear-conversation', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    user_id: userId
                })
            });
            
            chrome.storage.local.remove('conversationHistory');
            updateStatus('Conversation history cleared', 'success');
        } catch (error) {
            console.error('Error:', error);
            updateStatus('Failed to clear conversation history', 'error');
        }
    });
    
    document.querySelector('.question-section').appendChild(clearButton);
});

// Helper function to make API requests
async function makeRequest(url, method = 'GET', data = null) {
    console.log(`Making ${method} request to ${url}`);
    try {
        const options = {
            method,
            headers: {
                'Content-Type': 'application/json'
            },
            timeout: TIMEOUT
        };

        if (data) {
            options.body = JSON.stringify(data);
            console.log('Request data:', data);
        }

        const response = await fetch(url, options);
        console.log('Response status:', response.status);
        
        if (!response.ok) {
            const errorData = await response.json();
            console.log('Error response:', errorData);
            throw new Error(errorData.message || `HTTP error! status: ${response.status}`);
        }

        const responseData = await response.json();
        console.log('Response data:', responseData);
        return responseData;
    } catch (error) {
        console.error('Request failed:', error);
        throw error;
    }
}

// Function to handle authentication using Chrome's identity API
function handleAuthentication() {
    return new Promise((resolve, reject) => {
        console.log('Starting Chrome identity authentication');
        
        chrome.identity.getAuthToken({ 
            interactive: true 
        }, function(token) {
            if (chrome.runtime.lastError) {
                console.error('Auth error:', chrome.runtime.lastError);
                reject(new Error(chrome.runtime.lastError.message));
                return;
            }

            if (token) {
                console.log('Got auth token:', token.substring(0, 5) + '...');
                resolve(token);
            } else {
                console.error('No token received');
                reject(new Error('Authentication failed'));
            }
        });
    });
}

// Function to remove cached token
function removeCachedToken(token) {
    return new Promise((resolve, reject) => {
        chrome.identity.removeCachedAuthToken({ token: token }, function() {
            if (chrome.runtime.lastError) {
                console.error('Error removing token:', chrome.runtime.lastError);
                reject(chrome.runtime.lastError);
            } else {
                console.log('Token removed successfully');
                resolve();
            }
        });
    });
}

console.log('Event listeners added'); 