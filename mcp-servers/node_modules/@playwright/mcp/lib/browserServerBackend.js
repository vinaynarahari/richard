/**
 * Copyright (c) Microsoft Corporation.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
import { fileURLToPath } from 'url';
import { z } from 'zod';
import { Context } from './context.js';
import { logUnhandledError } from './log.js';
import { Response } from './response.js';
import { SessionLog } from './sessionLog.js';
import { filteredTools } from './tools.js';
import { packageJSON } from './package.js';
import { defineTool } from './tools/tool.js';
export class BrowserServerBackend {
    name = 'Playwright';
    version = packageJSON.version;
    _tools;
    _context;
    _sessionLog;
    _config;
    _browserContextFactory;
    constructor(config, factories) {
        this._config = config;
        this._browserContextFactory = factories[0];
        this._tools = filteredTools(config);
        if (factories.length > 1)
            this._tools.push(this._defineContextSwitchTool(factories));
    }
    async initialize(server) {
        const capabilities = server.getClientCapabilities();
        let rootPath;
        if (capabilities.roots && (server.getClientVersion()?.name === 'Visual Studio Code' ||
            server.getClientVersion()?.name === 'Visual Studio Code - Insiders')) {
            const { roots } = await server.listRoots();
            const firstRootUri = roots[0]?.uri;
            const url = firstRootUri ? new URL(firstRootUri) : undefined;
            rootPath = url ? fileURLToPath(url) : undefined;
        }
        this._sessionLog = this._config.saveSession ? await SessionLog.create(this._config, rootPath) : undefined;
        this._context = new Context({
            tools: this._tools,
            config: this._config,
            browserContextFactory: this._browserContextFactory,
            sessionLog: this._sessionLog,
            clientInfo: { ...server.getClientVersion(), rootPath },
        });
    }
    tools() {
        return this._tools.map(tool => tool.schema);
    }
    async callTool(schema, parsedArguments) {
        const context = this._context;
        const response = new Response(context, schema.name, parsedArguments);
        const tool = this._tools.find(tool => tool.schema.name === schema.name);
        context.setRunningTool(true);
        try {
            await tool.handle(context, parsedArguments, response);
            await response.finish();
            this._sessionLog?.logResponse(response);
        }
        catch (error) {
            response.addError(String(error));
        }
        finally {
            context.setRunningTool(false);
        }
        return response.serialize();
    }
    serverClosed() {
        void this._context.dispose().catch(logUnhandledError);
    }
    _defineContextSwitchTool(factories) {
        const self = this;
        return defineTool({
            capability: 'core',
            schema: {
                name: 'browser_connect',
                title: 'Connect to a browser context',
                description: [
                    'Connect to a browser using one of the available methods:',
                    ...factories.map(factory => `- "${factory.name}": ${factory.description}`),
                ].join('\n'),
                inputSchema: z.object({
                    method: z.enum(factories.map(factory => factory.name)).default(factories[0].name).describe('The method to use to connect to the browser'),
                }),
                type: 'readOnly',
            },
            async handle(context, params, response) {
                const factory = factories.find(factory => factory.name === params.method);
                if (!factory) {
                    response.addError('Unknown connection method: ' + params.method);
                    return;
                }
                await self._setContextFactory(factory);
                response.addResult('Successfully changed connection method.');
            }
        });
    }
    async _setContextFactory(newFactory) {
        if (this._context) {
            const options = {
                ...this._context.options,
                browserContextFactory: newFactory,
            };
            await this._context.dispose();
            this._context = new Context(options);
        }
        this._browserContextFactory = newFactory;
    }
}
