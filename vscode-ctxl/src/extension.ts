import * as vscode from 'vscode';
import Anthropic from '@anthropic-ai/sdk';
import { MessageParam, Tool, ToolUseBlock } from '@anthropic-ai/sdk/resources/messages';
import { exec } from 'child_process';
import util from 'util';
const execPromise = util.promisify(exec);
import * as path from 'path';
import * as os from 'os';
import * as crypto from 'crypto';
import * as fs from 'fs';
import ignore from 'ignore';

// Define an interface for the chat client
interface ChatClient {
    streamResponse(messages: MessageParam[], systemPrompt: string, tools: Tool[]): Promise<AsyncIterable<any>>;
}

// Implement the interface for direct Anthropic API
class AnthropicDirectClient implements ChatClient {
    private client: Anthropic;

    constructor(apiKey: string) {
        this.client = new Anthropic({ apiKey });
    }

    async streamResponse(messages: MessageParam[], systemPrompt: string, tools: Tool[]): Promise<AsyncIterable<any>> {
        return this.client.messages.stream({
            messages,
            model: 'claude-3-5-sonnet-20240620',
            max_tokens: 8096,
            system: systemPrompt,
            tools,
        });
    }
}

class AnthropicBedrockWrapper implements ChatClient {
    private client: any;

    async initialize() {
        const { AnthropicBedrock } = await import('@anthropic-ai/bedrock-sdk');
        this.client = new AnthropicBedrock();
    }

    async streamResponse(messages: MessageParam[], systemPrompt: string, tools: Tool[]): Promise<AsyncIterable<any>> {
        if (!this.client) {
            await this.initialize();
        }
        return this.client.messages.create({
            model: 'anthropic.claude-3-5-sonnet-20240620-v1:0',
            messages,
            max_tokens: 8096,
            system: systemPrompt,
            tools,
            stream: true,
        });
    }
}

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
    {
        name: 'open_file',
        description: 'Open a file in the VS Code editor. If the file does not exist, it will be created.',
        input_schema: {
            type: 'object',
            properties: {
                filepath: {
                    type: 'string',
                    description: 'The path to the file to be opened',
                },
                purpose: {
                    type: 'string',
                    description: 'The purpose of opening this file',
                },
            },
            required: ['filepath', 'purpose'],
        },
    },
];

class EditorContentProvider {
    private ignoreRules: ReturnType<typeof ignore>;

    constructor() {
        this.ignoreRules = ignore();
        this.initIgnoreRules();
    }

    private async initIgnoreRules() {
        // Add rules from VS Code settings
        const excludeSettings = vscode.workspace.getConfiguration('files').get('exclude') || {};
        const searchExcludeSettings = vscode.workspace.getConfiguration('search').get('exclude') || {};
        Object.keys({...excludeSettings, ...searchExcludeSettings}).forEach(pattern => {
            this.ignoreRules.add(pattern);
        });

        // Add rules from .gitignore if it exists
        if (vscode.workspace.workspaceFolders) {
            const gitignorePath = path.join(vscode.workspace.workspaceFolders[0].uri.fsPath, '.gitignore');
            if (fs.existsSync(gitignorePath)) {
                const gitignoreContent = await fs.promises.readFile(gitignorePath, 'utf8');
                this.ignoreRules.add(gitignoreContent);
            }
        }
    }

    private isIgnored(relativePath: string): boolean {
        return this.ignoreRules.ignores(relativePath);
    }

    async getAllEditorsContentAsXml(): Promise<string> {
        const tabGroups = vscode.window.tabGroups;
        const tabPromises: Promise<{ groupIndex: number; tabData: { path: string; content: string; isActive: boolean; } }[]>[] = [];
    
        tabGroups.all.forEach((group, groupIndex) => {
            const groupPromise = Promise.all(
                group.tabs.flatMap(async (tab): Promise<{ groupIndex: number; tabData: { path: string; content: string; isActive: boolean; } } | null> => {
                    if (tab.input instanceof vscode.TabInputText && tab.input.uri.scheme === 'file') {
                        const tabData = await this.getEditorData(tab.input, tab.isActive);
                        return { groupIndex, tabData };
                    }
                    return null;
                })
            ).then(results => results.filter((result): result is { groupIndex: number; tabData: { path: string; content: string; isActive: boolean; } } => result !== null));
    
            tabPromises.push(groupPromise);
        });
    
        const allTabData = (await Promise.all(tabPromises)).flat();
    
        let xmlContent = '<editor_state>\n';
        xmlContent += await this.getWorkspaceStructure();
        let currentGroupIndex = -1;
    
        allTabData.forEach(({ groupIndex, tabData }) => {
            if (groupIndex !== currentGroupIndex) {
                if (currentGroupIndex !== -1) {
                    xmlContent += '  </tab_group>\n';
                }
                xmlContent += `  <tab_group index="${groupIndex}">\n`;
                currentGroupIndex = groupIndex;
            }
    
            xmlContent += '    <tab>\n';
            xmlContent += `      <path>${tabData.path}</path>\n`;
            xmlContent += `      <content>${tabData.content}</content>\n`;
            xmlContent += `      <is_active>${tabData.isActive}</is_active>\n`;
            xmlContent += '    </tab>\n';
        });
    
        if (currentGroupIndex !== -1) {
            xmlContent += '  </tab_group>\n';
        }
    
        xmlContent += '</editor_state>';
        return xmlContent;
    }

    private async getEditorData(document: vscode.TabInputText, isActive: boolean): Promise<{path: string, content: string, isActive: boolean}> {
        const filePath = document.uri.fsPath;
        let fileContent: string;
        try {
            const contentUint8Array = await vscode.workspace.fs.readFile(document.uri);
            fileContent = Buffer.from(contentUint8Array).toString('utf8');
        } catch (error) {
            console.error(`Error reading file ${filePath}:`, error);
            fileContent = "Error reading file content";
        }
        
        return {
            path: filePath,
            content: fileContent,
            isActive: isActive
        };
    }

    private async getWorkspaceStructure(maxDepth: number = 3): Promise<string> {
        let xmlContent = '<workspace_structure>\n';
    
        if (vscode.workspace.workspaceFolders) {
            for (const folder of vscode.workspace.workspaceFolders) {
                xmlContent += await this.getFolderStructure(folder.uri, 0, maxDepth);
            }
        }
    
        xmlContent += '</workspace_structure>';
        return xmlContent;
    }
    
    private async getFolderStructure(folderUri: vscode.Uri, currentDepth: number, maxDepth: number): Promise<string> {
        if (currentDepth >= maxDepth) {
            return `  <folder path="${folderUri.fsPath}" truncated="true" />\n`;
        }
    
        let xmlContent = `  <folder path="${folderUri.fsPath}">\n`;
        
        try {
            const entries = await vscode.workspace.fs.readDirectory(folderUri);
            for (const [name, type] of entries) {
                // Skip dotfiles and dotfolders
                if (name.startsWith('.')) {
                    continue;
                }

                if (name.startsWith('node_modules')) {
                    continue;
                }
    
                if (type === vscode.FileType.File) {
                    xmlContent += `    <file name="${name}" />\n`;
                } else if (type === vscode.FileType.Directory) {
                    xmlContent += await this.getFolderStructure(vscode.Uri.joinPath(folderUri, name), currentDepth + 1, maxDepth);
                }
            }
        } catch (error) {
            console.error(`Error reading directory ${folderUri.fsPath}:`, error);
            xmlContent += `    <error>Failed to read directory contents</error>\n`;
        }
    
        xmlContent += `  </folder>\n`;
        return xmlContent;
    }
}

class AnthropicChat {
    private client: ChatClient | undefined;
    private webview: vscode.Webview | undefined;
    private messages: MessageParam[] = [];
    private terminal: vscode.Terminal | undefined;
    private readonly terminalName = 'Contextual';
    private editorContentProvider: EditorContentProvider;


    constructor(private context: vscode.ExtensionContext) {
        this.initializeClient();
        this.editorContentProvider = new EditorContentProvider();
    }

    async initializeClient() {
        const clientType = await vscode.workspace.getConfiguration('contextualChat').get('clientType', 'direct');
        if (clientType === 'direct') {
            const apiKey = await this.context.secrets.get('anthropic-api-key');
            if (apiKey) {
                this.client = new AnthropicDirectClient(apiKey);
            }
        } else if (clientType === 'bedrock') {
            this.client = new AnthropicBedrockWrapper();
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

        const editorContentsXml = await this.editorContentProvider.getAllEditorsContentAsXml();
        const contextMessage = `Current open files:\n${editorContentsXml}`;
        const systemPrompt = contextMessage + '\nYou are an AI assistant with access to the following tools: ' + JSON.stringify(toolSchemas, null, 2) + '. You can also view the current open files as well as the active editor. Always use `open_file` to open a file before writing or editing it. Always think step by step in a <thinking>...</thinking> block before doing anything.';

        const stream = await this.client.streamResponse(this.messages, systemPrompt, toolSchemas);

        let assistantMessage = '';
        let currentToolUse: Partial<ToolUseBlock> | null = null;
        let currentInputJson = '';
        let toolUses: ToolUseBlock[] = [];

        for await (const event of stream) {
            console.log('Stream event:', JSON.stringify(event, null, 2));

            if (event.type === 'content_block_delta' && event.delta.type === 'text_delta') {
                assistantMessage += event.delta.text;
                this.webview.postMessage({ type: 'assistantDelta', content: event.delta.text });
            } else if (event.type === 'content_block_start' && event.content_block.type === 'tool_use') {
                currentToolUse = {
                    type: 'tool_use',
                    id: event.content_block.id,
                    name: event.content_block.name,
                    input: {}
                };
                currentInputJson = '';
            } else if (event.type === 'content_block_delta' && event.delta.type === 'input_json_delta') {
                currentInputJson += event.delta.partial_json;
            } else if (event.type === 'content_block_stop' && currentToolUse) {
                try {
                    currentToolUse.input = JSON.parse(currentInputJson);
                    console.log('Complete Tool Use:', JSON.stringify(currentToolUse, null, 2));
                    toolUses.push(currentToolUse as ToolUseBlock);
                } catch (error) {
                    console.error('Error parsing tool input JSON:', error);
                }
                currentToolUse = null;
                currentInputJson = '';
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

                let result: string = await this.handleToolUse(toolUse);

                console.log(`\nTool Result:\n${result}`);
            
                this.webview?.postMessage({ 
                    type: 'toolResult', 
                    content: { toolName: toolUse.name, result: result } 
                });

                this.messages.push({
                    role: 'assistant',
                    content: assistantContent,
                });
            
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

            // Get follow-up response
            await this.streamResponse();
        } else {
            this.messages.push({ role: 'assistant', content: assistantMessage });
        }
    }

    private async handleToolUse(toolUse: ToolUseBlock): Promise<string> {
        console.log('Handling tool use:', JSON.stringify(toolUse, null, 2));
        let result: string;
        if (toolUse.name === 'execute_command') {
            result = await this.executeCommandInTerminal(toolUse);
        } else if (toolUse.name === 'open_file') {
            result = await this.handleOpenFileTool(toolUse);
        } else {
            result = 'Unknown tool';
        }

        console.log(`Tool Result:\n${result}`);
        return result;
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

    private async executeCommandInTerminal(toolUse: ToolUseBlock): Promise<string> {
        const input = toolUse.input as { command: string; purpose: string };
        return new Promise(async (resolve) => {
            this.terminal = vscode.window.terminals.find(t => t.name === this.terminalName);
            if (!this.terminal) {
                this.terminal = vscode.window.createTerminal('Contextual');
                this.terminal.show();
            }

            const shellIntegrationActivated = await this.waitForShellIntegration(this.terminal);

            if (shellIntegrationActivated && this.terminal.shellIntegration) {
                const execution = this.terminal.shellIntegration.executeCommand(input.command);
                let output = '';
                for await (const data of execution.read()) {
                    output += data;
                }
                resolve(output);
            } else {
                console.log('Shell integration not available, falling back to sendText');
                this.terminal.sendText(input.command);
                // Note: We can't get the output in this case
                resolve('Command sent, but output not available without shell integration');
            }
        });
    }

    private async handleOpenFileTool(toolUse: ToolUseBlock): Promise<string> {
        const input = toolUse.input as { filepath: string; purpose: string };
        const filePath = input.filepath;

        try {
            const uri = vscode.Uri.file(filePath);
            let document: vscode.TextDocument;

            try {
                // Try to open the existing document
                document = await vscode.workspace.openTextDocument(uri);
            } catch (error) {
                // If the file doesn't exist, create it
                const fileContent = '';
                const writeData = new Uint8Array(Buffer.from(fileContent));
                await vscode.workspace.fs.writeFile(uri, writeData);
                document = await vscode.workspace.openTextDocument(uri);
            }

            await vscode.window.showTextDocument(document);
            return `File ${filePath} opened successfully.`;
        } catch (error) {
            console.error('Error opening or creating file:', error);
            if (error instanceof Error) {
                return `Error opening or creating file: ${error.message}`;
            } else {
                return `An unexpected error occurred while opening or creating the file: ${String(error)}`;
            }
        }
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

    const setClientTypeCommand = vscode.commands.registerCommand('vscode-ctxl.setClientType', async () => {
        const clientType = await vscode.window.showQuickPick(['direct', 'bedrock'], {
            placeHolder: 'Select Anthropic client type',
        });

        if (clientType) {
            await vscode.workspace.getConfiguration('contextualChat').update('clientType', clientType, true);
            await anthropicChat.initializeClient();
            vscode.window.showInformationMessage(`Anthropic client type set to ${clientType}`);
        }
    });
    context.subscriptions.push(setClientTypeCommand);
    context.subscriptions.push(setApiKeyCommand);

    console.log('Contextual Chat extension activated successfully');
}

export function deactivate() {
    console.log('Deactivating Contextual Chat extension...');
    // Perform any cleanup if necessary
}