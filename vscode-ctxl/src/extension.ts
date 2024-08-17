import * as vscode from 'vscode';
import Anthropic from '@anthropic-ai/sdk';
import { MessageParam, Tool, ToolUseBlock } from '@anthropic-ai/sdk/resources/messages';
import { exec } from 'child_process';
import util from 'util';
const execPromise = util.promisify(exec);

const toolSchemas: Tool[] = [
    {
        name: 'execute_command',
        description: 'Execute a shell command',
        input_schema: {
            type: 'object',
            properties: {
                command: {
                    type: 'string',
                    description: 'The shell command to execute',
                },
                purpose: {
                    type: 'string',
                    description: 'The purpose of the command',
                },
            },
            required: ['command', 'purpose'],
        },
    },
];

class AnthropicChat {
    private client: Anthropic | undefined;
    private webview: vscode.Webview | undefined;
    private messages: MessageParam[] = [];
    private terminal: vscode.Terminal | undefined;
    private readonly terminalName = 'Contextual';

    constructor(private context: vscode.ExtensionContext) {
        this.initializeClient();
    }

    async initializeClient() {
        const apiKey = await this.context.secrets.get('anthropic-api-key');
        if (apiKey) {
            this.client = new Anthropic({ apiKey });
        }
    }

    setWebview(webview: vscode.Webview) {
        this.webview = webview;
    }

    async sendMessage(content: string) {
        if (!this.webview) {
            console.error('Webview is not initialized');
            return;
        }

        if (!this.client) {
            this.webview.postMessage({ type: 'error', content: 'Anthropic API key is not set. Please set it in the settings.' });
            return;
        }

        this.messages.push({ role: 'user', content });
        this.webview.postMessage({ type: 'userMessage', content });

        try {
            await this.streamResponse();
        } catch (error) {
            console.error('Error in sendMessage:', error);
            this.webview.postMessage({ type: 'error', content: 'An error occurred while processing your message.' });
        }
    }

    private async streamResponse() {
        if (!this.client || !this.webview) return;

        const stream = await this.client.messages.stream({
            messages: this.messages,
            model: 'claude-3-5-sonnet-20240620',
            max_tokens: 1024,
            system: "You are an AI assistant capable of using tools to help with tasks.",
            tools: toolSchemas,
        });

        let assistantMessage = '';
        let toolUses: ToolUseBlock[] = [];

        for await (const event of stream) {
            if (event.type === 'content_block_delta' && event.delta.type === 'text_delta') {
                assistantMessage += event.delta.text;
                this.webview.postMessage({ type: 'assistantDelta', content: event.delta.text });
            } else if (event.type === 'content_block_start' && event.content_block.type === 'tool_use') {
                toolUses.push(event.content_block);
            }
        }

        this.webview.postMessage({ type: 'assistantMessageComplete' });

        if (toolUses.length > 0) {
            let assistantContent: (ToolUseBlock | { type: 'text'; text: string })[] = [
                { type: 'text', text: assistantMessage }
            ];
            
            for (const toolUse of toolUses) {
                console.log('\nTool Use:', JSON.stringify(toolUse, null, 2));
                assistantContent.push(toolUse);

                if (toolUse.name === 'execute_command') {
                    const input = toolUse.input as { command: string };
                    const result = await this.executeCommandInTerminal(input.command);
                    console.log(`\nCommand Result:\n${result}`);
                
                    this.webview?.postMessage({ 
                        type: 'toolResult', 
                        content: { toolName: input.command, result: 'Command executed' } 
                    });

                    this.messages.push({
                        role: 'assistant',
                        content: assistantContent,
                    });
                
                    // The full result is still added to this.messages
                    this.messages.push({
                        role: 'user',
                        content: [
                            {
                                type: 'tool_result',
                                tool_use_id: toolUse.id,
                                content: result,
                            },
                        ],
                    });
            
                }
            }
        // Get follow-up response
        await this.streamResponse();
        } else {
            this.messages.push({ role: 'assistant', content: assistantMessage });
        }
    }

    private async waitForShellIntegration(terminal: vscode.Terminal, timeout: number = 5000): Promise<boolean> {
        return new Promise<boolean>((resolve) => {
            if (terminal.shellIntegration) {
                resolve(true);
                return;
            }

            const listener = vscode.window.onDidChangeTerminalShellIntegration((event) => {
                if (event.terminal === terminal) {
                    listener.dispose();
                    resolve(true);
                }
            });

            setTimeout(() => {
                listener.dispose();
                resolve(false);
            }, timeout);
        });
    }

    private async executeCommandInTerminal(command: string): Promise<string> {
        return new Promise(async (resolve) => {
            this.terminal = vscode.window.terminals.find(t => t.name === this.terminalName);
            if (!this.terminal) {
                this.terminal = vscode.window.createTerminal('Contextual');
                this.terminal.show();
            }

            const shellIntegrationActivated = await this.waitForShellIntegration(this.terminal);

            if (shellIntegrationActivated && this.terminal.shellIntegration) {
                const execution = this.terminal.shellIntegration.executeCommand(command);
                let output = '';
                for await (const data of execution.read()) {
                    output += data;
                }
                resolve(output);
            } else {
                console.log('Shell integration not available, falling back to sendText');
                this.terminal.sendText(command);
                // Note: We can't get the output in this case
                resolve('Command sent, but output not available without shell integration');
            }
        });
    }

    async setApiKey(apiKey: string) {
        await this.context.secrets.store('anthropic-api-key', apiKey);
        await this.initializeClient();
        if (this.webview) {
            this.webview.postMessage({ type: 'apiKeySet' });
        }
    }

    async getApiKey(): Promise<string | undefined> {
        return this.context.secrets.get('anthropic-api-key');
    }
}

class ContextualChatViewProvider implements vscode.WebviewViewProvider {
    constructor(
        private context: vscode.ExtensionContext,
        private anthropicChat: AnthropicChat
    ) {}

    public resolveWebviewView(
        webviewView: vscode.WebviewView,
        context: vscode.WebviewViewResolveContext,
        _token: vscode.CancellationToken
    ) {
        console.log('Resolving WebView...');

        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [this.context.extensionUri]
        };

        try {
            const htmlContent = this.getChatHtml();
            console.log('HTML content generated successfully');
            webviewView.webview.html = htmlContent;
        } catch (error) {
            console.error('Error generating HTML content:', error);
            webviewView.webview.html = `<html><body>Error loading chat interface</body></html>`;
        }

        this.anthropicChat.setWebview(webviewView.webview);

        webviewView.webview.onDidReceiveMessage(
            async message => {
                console.log('Received message from WebView:', message);
                if (message.type === 'userInput') {
                    this.anthropicChat.sendMessage(message.content);
                } else if (message.type === 'setApiKey') {
                    await this.anthropicChat.setApiKey(message.apiKey);
                } else if (message.type === 'getApiKey') {
                    const apiKey = await this.anthropicChat.getApiKey();
                    webviewView.webview.postMessage({ type: 'apiKeyStatus', exists: !!apiKey });
                }
            },
            undefined,
            this.context.subscriptions
        );

        console.log('WebView resolved successfully');
    }

private getChatHtml() {
    return `<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Contextual Chat</title>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/markdown-it/12.3.2/markdown-it.min.js"></script>
        <style>
            body {
                font-family: var(--vscode-font-family, Arial, sans-serif);
                margin: 0;
                padding: 0;
                display: flex;
                flex-direction: column;
                height: 100vh;
                color: var(--vscode-foreground);
                background-color: var(--vscode-editor-background);
            }
            #chat-container {
                display: flex;
                flex-direction: column;
                height: 100vh;
            }
            #chat-history {
                flex-grow: 1;
                overflow-y: auto;
                padding: 20px;
                display: flex;
                flex-direction: column;
            }
            .message {
                max-width: 80%;
                margin-bottom: 10px;
                padding: 8px 12px;
                border-radius: 18px;
                line-height: 1.4;
                word-wrap: break-word;
            }
            .message p {
                margin: 0;
                padding: 0;
            }
            .message > p:only-child {
                margin: 0;
                padding: 0;
            }
            /* For messages with multiple paragraphs, add some spacing between them */
            .message > p + p {
                margin-top: 0.5em;
            }
            .user-message {
                align-self: flex-end;
                background-color: var(--vscode-button-background);
                color: var(--vscode-button-foreground);
            }
            .assistant-message {
                align-self: flex-start;
                background-color: var(--vscode-editor-inactiveSelectionBackground);
                color: var(--vscode-editor-foreground);
            }
            .tool-message {
                align-self: flex-start;
                background-color: var(--vscode-editorInfo-background);
                color: var(--vscode-editorInfo-foreground);
                font-family: var(--vscode-editor-font-family, monospace);
                font-size: 0.9em;
            }
            .message pre {
                background-color: var(--vscode-textCodeBlock-background);
                padding: 10px;
                border-radius: 5px;
                overflow-x: auto;
            }
            .message code {
                font-family: var(--vscode-editor-font-family, monospace);
                font-size: 0.9em;
            }
            #input-area {
                display: flex;
                padding: 10px;
                background-color: var(--vscode-input-background);
                border-top: 1px solid var(--vscode-input-border);
            }
            #chat-input {
                flex-grow: 1;
                padding: 10px;
                border: none;
                border-radius: 20px;
                background-color: var(--vscode-input-background);
                color: var(--vscode-input-foreground);
            }
            #send-button {
                padding: 10px 20px;
                margin-left: 10px;
                background-color: var(--vscode-button-background);
                color: var(--vscode-button-foreground);
                border: none;
                border-radius: 20px;
                cursor: pointer;
            }
            #send-button:hover {
                background-color: var(--vscode-button-hoverBackground);
            }
            #settings-button {
                position: absolute;
                top: 10px;
                right: 10px;
                background: none;
                border: none;
                color: var(--vscode-foreground);
                cursor: pointer;
                font-size: 18px;
            }
            #settings-modal {
                display: none;
                position: fixed;
                z-index: 1;
                left: 0;
                top: 0;
                width: 100%;
                height: 100%;
                background-color: rgba(0,0,0,0.4);
            }
            .modal-content {
                background-color: var(--vscode-editor-background);
                margin: 15% auto;
                padding: 20px;
                border: 1px solid var(--vscode-input-border);
                width: 80%;
                border-radius: 8px;
            }
            .close {
                color: var(--vscode-descriptionForeground);
                float: right;
                font-size: 28px;
                font-weight: bold;
                cursor: pointer;
            }
            .close:hover,
            .close:focus {
                color: var(--vscode-foreground);
                text-decoration: none;
                cursor: pointer;
            }
            #api-key {
                width: 100%;
                padding: 10px;
                margin: 10px 0;
                border-radius: 4px;
                border: 1px solid var(--vscode-input-border);
                background-color: var(--vscode-input-background);
                color: var(--vscode-input-foreground);
            }
            #save-api-key {
                padding: 10px 20px;
                background-color: var(--vscode-button-background);
                color: var(--vscode-button-foreground);
                border: none;
                border-radius: 4px;
                cursor: pointer;
            }
            #save-api-key:hover {
                background-color: var(--vscode-button-hoverBackground);
            }
        </style>
    </head>
    <body>
        <div id="chat-container">
            <button id="settings-button">⚙️</button>
            <div id="chat-history"></div>
            <div id="input-area">
                <input type="text" id="chat-input" placeholder="Type your message here..." autofocus>
                <button id="send-button">Send</button>
            </div>
        </div>
        <div id="settings-modal">
            <div class="modal-content">
                <span class="close">&times;</span>
                <h2>Settings</h2>
                <label for="api-key">Anthropic API Key:</label>
                <input type="password" id="api-key" placeholder="Enter your API key">
                <button id="save-api-key">Save</button>
            </div>
        </div>
        <script>
            const vscode = acquireVsCodeApi();
            const chatHistory = document.getElementById('chat-history');
            const chatInput = document.getElementById('chat-input');
            const sendButton = document.getElementById('send-button');
            const md = window.markdownit();

            let currentAssistantMessage = null;
            let currentAssistantContent = '';

            function sendMessage() {
                const message = chatInput.value.trim();
                if (message) {
                    addMessageToChat('user', message);
                    vscode.postMessage({ type: 'userInput', content: message });
                    chatInput.value = '';
                }
            }

            sendButton.addEventListener('click', sendMessage);
            chatInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    sendMessage();
                }
            });

            function addMessageToChat(role, content) {
                const messageElement = document.createElement('div');
                messageElement.classList.add('message', \`\${role}-message\`);
                
                if (role === 'assistant') {
                    currentAssistantMessage = messageElement;
                    currentAssistantContent = '';
                } else {
                    messageElement.innerHTML = md.render(content);
                }
                
                chatHistory.appendChild(messageElement);
                chatHistory.scrollTop = chatHistory.scrollHeight;
            }

            function updateAssistantMessage() {
                if (currentAssistantMessage) {
                    const renderedContent = md.render(currentAssistantContent);
                    console.log('Rendered HTML:', renderedContent);
                    currentAssistantMessage.innerHTML = renderedContent;
                    chatHistory.scrollTop = chatHistory.scrollHeight;
                }
            }

            window.addEventListener('message', event => {
                const message = event.data;
                switch (message.type) {
                    case 'userMessage':
                        // User messages are now added when sent, so we don't need to add them here
                        break;
                    case 'assistantDelta':
                        if (!currentAssistantMessage) {
                            addMessageToChat('assistant', '');
                        }
                        currentAssistantContent += message.content;
                        updateAssistantMessage();
                        break;
                    case 'assistantMessageComplete':
                        updateAssistantMessage();
                        currentAssistantMessage = null;
                        currentAssistantContent = '';
                        break;
                    case 'error':
                        addMessageToChat('error', message.content);
                        break;
                    case 'toolResult':
                        const toolMessage = \`Command executed: \${message.content.toolName}\`;
                        addMessageToChat('tool', toolMessage);
                        break;
                    case 'apiKeyStatus':
                        apiKeyInput.value = message.exists ? '********' : '';
                        break;
                    case 'apiKeySet':
                        settingsModal.style.display = 'none';
                        vscode.postMessage({ type: 'getApiKey' });
                        break;
                }
            });

            const settingsButton = document.getElementById('settings-button');
            const settingsModal = document.getElementById('settings-modal');
            const closeButton = document.getElementsByClassName('close')[0];
            const apiKeyInput = document.getElementById('api-key');
            const saveApiKeyButton = document.getElementById('save-api-key');

            settingsButton.onclick = () => {
                settingsModal.style.display = 'block';
                vscode.postMessage({ type: 'getApiKey' });
            }

            closeButton.onclick = () => {
                settingsModal.style.display = 'none';
            }

            window.onclick = (event) => {
                if (event.target == settingsModal) {
                    settingsModal.style.display = 'none';
                }
            }

            saveApiKeyButton.onclick = () => {
                const apiKey = apiKeyInput.value.trim();
                if (apiKey) {
                    vscode.postMessage({ type: 'setApiKey', apiKey: apiKey });
                }
            }

            // Initial API key status check
            vscode.postMessage({ type: 'getApiKey' });
        </script>
    </body>
    </html>`;
}
}

export function activate(context: vscode.ExtensionContext) {
    console.log('Activating Contextual Chat extension...');

    // Initialize AnthropicChat
    const anthropicChat = new AnthropicChat(context);

    // Create and register WebView provider
    const provider = new ContextualChatViewProvider(context, anthropicChat);
    const providerRegistration = vscode.window.registerWebviewViewProvider(
        'contextualChatSidebar',
        provider
    );
    context.subscriptions.push(providerRegistration);

    // Register command to open chat interface
    const openChatCommand = vscode.commands.registerCommand('vscode-ctxl.openChatInterface', async () => {
        try {
            await vscode.commands.executeCommand('workbench.view.extension.contextual-chat-view');
        } catch (error) {
            console.error('Failed to open Contextual Chat view:', error);
            vscode.window.showErrorMessage('Failed to open Contextual Chat view');
        }
    });
    context.subscriptions.push(openChatCommand);

    // Register command to set Anthropic API key
    const setApiKeyCommand = vscode.commands.registerCommand('vscode-ctxl.setAnthropicApiKey', async () => {
        const apiKey = await vscode.window.showInputBox({
            prompt: 'Enter your Anthropic API key',
            password: true
        });

        if (apiKey) {
            try {
                await context.secrets.store('anthropic-api-key', apiKey);
                await anthropicChat.initializeClient();
                vscode.window.showInformationMessage('Anthropic API key has been set successfully.');
            } catch (error) {
                console.error('Failed to set Anthropic API key:', error);
                vscode.window.showErrorMessage('Failed to set Anthropic API key');
            }
        }
    });
    context.subscriptions.push(setApiKeyCommand);

    console.log('Contextual Chat extension activated successfully');
}

export function deactivate() {
    console.log('Deactivating Contextual Chat extension...');
    // Perform any cleanup if necessary
}