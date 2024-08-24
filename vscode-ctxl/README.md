# vscode-ctxl README

Welcome to vscode-ctxl, a Visual Studio Code extension that provides contextual AI assistance powered by Anthropic's Claude model. This tool enhances your coding experience with intelligent, context-aware support integrated directly into your development workflow.

## Features

- **Contextual AI Chat**: Interact with an AI assistant that has access to your current workspace context, including open files and editor contents.
- **Intelligent Code Assistance**: Get help with coding tasks, ask questions, and receive context-aware responses.
- **File Editing**: The AI can propose edits to your files, which you can review and approve through a diff interface.
- **Command Execution**: Execute shell commands directly from the chat interface and view the results.
- **Markdown Rendering**: Chat messages support Markdown formatting for better readability.
- **Workspace Structure Awareness**: The AI has access to your workspace structure, allowing for more contextual assistance.

## Requirements

- Visual Studio Code version 1.60.0 or higher.
- An active internet connection.
- An Anthropic API key (Claude model access required).

## Extension Settings

This extension contributes the following settings:

* `anthropic-api-key`: Set your Anthropic API key for authentication. This is stored securely using VS Code's secret storage.

## Usage

1. Open the Contextual Chat sidebar by clicking on the icon in the Activity Bar or by running the "Open Contextual Chat Interface" command from the Command Palette.
2. Set your Anthropic API key when prompted in the chat interface or through the settings button in the chat view.
3. Start chatting with the AI assistant. You can ask questions, request code help, or instruct the AI to perform tasks.
4. For file edits, the AI will show you a diff of the proposed changes, which you can approve or reject.
5. To execute shell commands, simply ask the AI to do so in your chat message.

## Commands

- `vscode-ctxl.openChatInterface`: Open the Contextual Chat sidebar.
- `vscode-ctxl.setAnthropicApiKey`: Set or update your Anthropic API key.

## Known Issues

- The extension requires an active internet connection to communicate with the Anthropic API.
- Large files or extensive workspace structures may impact performance.
- Shell integration for command execution may not be available in all environments.

## Privacy and Data Usage

This extension sends your current workspace context, including file contents and structure, to Anthropic's API for processing. Please ensure you comply with your organization's data privacy policies when using this extension.

## Release Notes

### 1.0.0

Initial release of vscode-ctxl:
- Integrated Contextual AI Chat interface
- File editing capabilities with diff review
- Command execution feature
- Markdown rendering in chat
- Workspace structure awareness
- Secure API key storage

---

## Following extension guidelines

This extension follows the [Extension Guidelines](https://code.visualstudio.com/api/references/extension-guidelines) provided by Visual Studio Code.

## For more information

* [Visual Studio Code's Markdown Support](http://code.visualstudio.com/docs/languages/markdown)
* [Markdown Syntax Reference](https://help.github.com/articles/markdown-basics/)
* [Anthropic Claude API Documentation](https://docs.anthropic.com/)

**Enjoy using vscode-ctxl!**