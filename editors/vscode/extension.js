/**
 * Hearthwren VS Code Extension
 * 
 * Thin wrapper around the `hwren` CLI.
 * Strictly respects local-first, resource-disciplined execution.
 */

const vscode = require('vscode');
const { exec } = require('child_process');

let outputChannel;
let statusBarItem;

function getWorkspaceRoot() {
    if (vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders.length > 0) {
        return vscode.workspace.workspaceFolders[0].uri.fsPath;
    }
    return process.cwd();
}

function runHwrenCommand(args, title) {
    const cwd = getWorkspaceRoot();
    outputChannel.show(true);
    outputChannel.appendLine(`\n=== [Hearthwren] ${title} ===`);
    outputChannel.appendLine(`Directory: ${cwd}`);
    outputChannel.appendLine(`Command: hwren ${args}\n`);

    // Use python -m hearthwren.cli fallback to ensure resolution
    const cmd = `python -m hearthwren.cli ${args}`;

    exec(cmd, { cwd }, (error, stdout, stderr) => {
        if (stdout) {
            outputChannel.appendLine(stdout);
        }
        if (stderr) {
            outputChannel.appendLine(`[stderr]:\n${stderr}`);
        }
        if (error) {
            vscode.window.showErrorMessage(`Hearthwren error: ${error.message}`);
        } else {
            vscode.window.showInformationMessage(`Hearthwren: ${title} completed.`);
        }
    });
}

function activate(context) {
    outputChannel = vscode.window.createOutputChannel("Hearthwren");
    context.subscriptions.push(outputChannel);

    // Status bar item
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.command = 'hearthwren.status';
    statusBarItem.text = "$(chip) Hearthwren (8GB CPU)";
    statusBarItem.tooltip = "Click to inspect Hearthwren status and RAM health";
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    // Register commands
    context.subscriptions.push(
        vscode.commands.registerCommand('hearthwren.status', () => {
            runHwrenCommand('status', 'Status & Resource Check');
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('hearthwren.plan', async () => {
            const task = await vscode.window.showInputBox({
                prompt: 'Describe the task to plan (no code will be written)',
                placeHolder: 'e.g. Implement user login with JWT tokens',
            });
            if (task) {
                runHwrenCommand(`plan "${task.replace(/"/g, '\\"')}"`, `Plan: ${task}`);
            }
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('hearthwren.verify', () => {
            runHwrenCommand('verify', 'Project Verification');
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('hearthwren.guide', async () => {
            const question = await vscode.window.showInputBox({
                prompt: 'Ask Hearthwren for architectural guidance',
                placeHolder: 'e.g. How do I configure GitHub Actions for this repository?',
            });
            if (question) {
                runHwrenCommand(`guide "${question.replace(/"/g, '\\"')}"`, `Guide: ${question}`);
            }
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('hearthwren.diff', () => {
            runHwrenCommand('diff', 'Workspace Diff');
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('hearthwren.resume', () => {
            runHwrenCommand('resume', 'Resume Last Task');
        })
    );
}

function deactivate() {
    if (statusBarItem) {
        statusBarItem.dispose();
    }
}

module.exports = {
    activate,
    deactivate,
};
